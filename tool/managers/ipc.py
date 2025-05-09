import asyncio
from functools import wraps
from rival import Connection
from discord import Client, utils, User, Member, Guild
from asyncio import gather
from typing import Optional, Any, Union
from itertools import chain
from .transform import Transformers, asDict
from discord.ext.commands import UserConverter
from inspect import getmembers, iscoroutinefunction, signature
from loguru import logger
import discord

EXCLUDED_METHODS = [
    "get_user_count",
    "get_guild_count",
    "get_role_count",
    "get_channel_count",
    "get_channel",
    "send_message",
]

NON_METHODS = ["roundtrip", "setup"]


class IPC:
    def __init__(self, bot: Client):
        self.bot = bot
        self.transformers = Transformers(self.bot)
        # Use integer division so shards_per_cluster is an int
        self.shards_per_cluster = self.bot.shard_count // 3
        # Divide the shard list into chunks of size equal to round(bot.shard_count/3)
        self.chunks = utils.chunk_list(
            list(range(self.bot.shard_count)), round(self.bot.shard_count / 3)
        )
        shard_ids = list(self.bot.shards.keys())
        self.cluster_id = next(
            (
                i
                for i, chunk in enumerate(self.chunks)
                if any(shard_id in chunk for shard_id in shard_ids)
            ),
            0,
        )
        self.bot.connection = Connection(
            local_name=f"cluster{str(self.cluster_id + 1)}",
            host="127.0.0.1",
            port=13254,
        )
        self.sources = [
            f"cluster{str(i)}" for i, chunk in enumerate(self.chunks, start=1)
        ][:3]
        self.max_retries = 3
        self.retry_delay = 1

    async def wait_for_connection(self):
        """Wait until the IPC connection is ready"""
        if not self.bot.connection.authorized or self.bot.connection.on_hold:
            try:
                await self.bot.connection.wait_until_ready()
            except asyncio.TimeoutError:
                logger.warning("Timeout while waiting for IPC connection to be ready")
                return False
        return True

    def get_coroutine_names_with_kwarg(self, kwarg_name: str):
        # Get all members of this class that are coroutine functions
        members = getmembers(self, predicate=iscoroutinefunction)
        coroutine_names = []
        for name, func in members:
            sig = signature(func)
            if kwarg_name in sig.parameters:
                coroutine_names.append(name)
        return coroutine_names

    async def setup(self):
        for attempt in range(self.max_retries):
            try:
                await self.bot.connection.start()
                coroutine_names = self.get_coroutine_names_with_kwarg("source")
                await gather(
                    *[
                        self.bot.connection.add_route(getattr(self, coroutine))
                        for coroutine in coroutine_names
                    ]
                )
                logger.info("Successfully setup the IPC routes")
                return
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning(
                    f"IPC setup failed (attempt {attempt + 1}/{self.max_retries}): {str(e)}"
                )
                await asyncio.sleep(self.retry_delay * (attempt + 1))

    async def roundtrip(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Send a message to the IPC server and return the response with retry logic"""
        coro = getattr(self, method)

        # Ensure connection is ready
        if not await self.wait_for_connection():
            raise RuntimeError("IPC connection is not ready")

        # Set shorter timeout for certain methods
        timeout = (
            10
            if method
            in [
                "get_guild_count",
                "get_user_count",
                "get_role_count",
                "get_channel_count",
            ]
            else 60
        )

        for attempt in range(self.max_retries):
            try:
                tasks = []
                # Create tasks for other clusters
                for s in self.sources:
                    if s != self.bot.connection.local_name:
                        tasks.append(
                            asyncio.create_task(
                                self.bot.connection.request(
                                    method, s, timeout=timeout, **kwargs
                                )
                            )
                        )
                # Add local execution task
                tasks.append(
                    asyncio.create_task(
                        coro(self.bot.connection.local_name, *args, **kwargs)
                    )
                )

                # Wait for all tasks with timeout
                try:
                    if method == "get_shards":
                        data = await asyncio.gather(*tasks, return_exceptions=True)
                        d = []
                        for i in data:
                            if not isinstance(i, Exception):
                                d.extend(i)
                        return d
                    elif method not in EXCLUDED_METHODS:
                        gathered = await asyncio.gather(*tasks, return_exceptions=True)
                        # Filter out exceptions and chain valid results
                        data = list(
                            chain(
                                *[g for g in gathered if not isinstance(g, Exception)]
                            )
                        )
                    else:
                        data = await asyncio.gather(*tasks, return_exceptions=True)
                        # Filter out exceptions
                        data = [d for d in data if not isinstance(d, Exception)]

                    return data

                except asyncio.TimeoutError:
                    logger.warning(
                        f"Timeout in roundtrip for method {method} (attempt {attempt + 1}/{self.max_retries})"
                    )
                    # Cancel any pending tasks
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    continue

            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning(
                    f"IPC request failed (attempt {attempt + 1}/{self.max_retries}): {str(e)}"
                )
                await asyncio.sleep(self.retry_delay * (attempt + 1))

                # Attempt reconnection if needed
                if not self.bot.connection.authorized:
                    try:
                        await self.bot.connection.start()
                    except Exception as e:
                        logger.error(f"Failed to restart IPC connection: {str(e)}")

        raise TimeoutError(f"All attempts failed for method {method}")

    async def get_shards(self, source: str, *args, **kwargs):
        data = []
        for shard_id, shard in self.bot.shards.items():
            guilds = [g for g in self.bot.guilds if g.shard_id == shard_id]
            users = sum(len(g.members) for g in guilds)
            data.append(
                {
                    "uptime": self.bot.startup_time.timestamp(),
                    "latency": round(shard.latency * 1000),
                    "servers": len(
                        [g for g in self.bot.guilds if g.shard_id == shard_id]
                    ),
                    "users": users,
                    "shard": shard_id,
                }
            )
        return data

    async def get_guild_count(self, source: str):
        return len(self.bot.guilds)

    async def get_user_count(self, source: str):
        return sum(i for i in self.bot.get_all_members())

    async def get_role_count(self, source: str):
        return sum(len(guild.roles) for guild in self.bot.guilds)

    async def get_channel_count(self, source: str):
        return sum(len(guild.channels) for guild in self.bot.guilds)

    async def start_instance(self, source: str, token: str, user_id: int):
        cog = self.bot.get_cog("Instances")
        if cog:
            await cog.start_instance(token, user_id)
            return True
        return False

    async def stop_instance(self, source: str, token: str, user_id: int):
        cog = self.bot.get_cog("Instances")
        if cog:
            await cog.stop_instance(token, user_id)
            return True
        return False

    async def restart_instance(self, source: str, token: str, user_id: int):
        cog = self.bot.get_cog("Instances")
        if cog:
            await cog.restart_instance(token, user_id)
            return True
        return False

    async def get_instance(self, source: str, user_id: int):
        cog = self.bot.get_cog("Instances")
        if cog:
            if user_id in self.bot.instances:
                return True
        return False

    async def get_instance_count(self, source: str):
        if hasattr(self.bot, "instances"):
            return len(self.bot.instances)
        else:
            return 0

    async def ipc_get_user_from_cache(self, source, user: Union[User, int]):
        try:
            u = await UserConverter().convert(self.bot, user)
        except Exception:
            return None
        if u:
            return u._to_minimal_user_json()
        else:
            return None

    async def get_guild(self, source: str, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if guild:
            return self.transformers.transform_guild(guild)
        else:
            return None

    async def leave_guild(self, source: str, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if guild:
            await guild.leave()
            return True
        return False

    async def get_member(self, source: str, guild_id: int, user_id: int):
        guild = self.bot.get_guild(guild_id)
        if guild:
            member = guild.get_member(user_id)
            if member:
                return self.transformers.transform_member(member)
        return None

    async def get_user_mutuals(
        self, source: str, user_id: int, count: Optional[bool] = False
    ):
        user = self.bot.get_user(user_id)
        if not user:
            return 0 if count else []
        if count:
            return len(user.mutual_guilds)
        else:
            return [asDict(guild) for guild in user.mutual_guilds]

    async def get_channel(self, source: str, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel:
            # Return a dictionary mapping a key to the transformed channel
            return {"channel": self.transformers.transform_channel(channel)}
        else:
            return {}

    async def send_message(
        self,
        source: str,
        channel_id: int,
        content: Optional[str] = None,
        embed: Optional[dict] = None,
    ):
        """
        Send a message to one or multiple channels.

        Args:
            source: IPC source identifier
            channel_id: Channel ID or list of channel IDs
            content: Message content
            embed: Embed dictionary

        Returns:
            dict: Mapping of channel IDs to sent message data
        """
        from discord import Embed

        channel_ids = [channel_id] if isinstance(channel_id, int) else channel_id
        embed_obj = Embed.from_dict(embed) if embed else None
        messages = {}

        for cid in channel_ids:
            channel = self.bot.get_channel(cid)
            if channel and channel.permissions_for(channel.guild.me).send_messages:
                try:
                    msg = await channel.send(content=content, embed=embed_obj)
                    messages[str(cid)] = {
                        "id": msg.id,
                        "content": msg.content,
                        "embeds": [e.to_dict() for e in msg.embeds],
                    }
                except Exception as e:
                    logger.error(f"Failed to send message to channel {cid}: {e}")

        return messages
