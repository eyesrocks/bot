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

EXCLUDED_METHODS = [
    "get_user_count",
    "get_guild_count",
    "get_role_count",
    "get_channel_count",
    "get_channel",
]

NON_METHODS = ["roundtrip", "setup"]
class IPC:
    def __init__(self, bot: Client):
        self.bot = bot
        self.transformers = Transformers(self.bot)
        self.shards_per_cluster = self.bot.shard_count / 3
        self.chunks = utils.chunk_list([i for i in range(self.bot.shard_count)], round(self.bot.shard_count / 3))
        self.cluster_id = self.chunks.index([k for k, v in self.bot.shards.items()])
        self.bot.connection = Connection(local_name = f"cluster{str(self.cluster_id + 1)}", host = "127.0.0.1", port = 13254)
        self.sources = [f"cluster{str(i)}" for i, chunk in enumerate(self.chunks, start = 1)]
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
        # Get all members of the class
        members = getmembers(self, predicate=iscoroutinefunction)
        # Extract the names of coroutine methods that have the specific keyword argument
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
                await gather(*[self.bot.connection.add_route(getattr(self, coroutine)) for coroutine in coroutine_names])
                logger.info("Successfully setup the IPC routes")
                return
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning(f"IPC setup failed (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                await asyncio.sleep(self.retry_delay * (attempt + 1))

    async def roundtrip(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Send a message to the IPC server and return the response with retry logic"""
        coro = getattr(self, method)
        
        # Try to ensure connection is ready
        if not await self.wait_for_connection():
            raise RuntimeError("IPC connection is not ready")

        for attempt in range(self.max_retries):
            try:
                tasks = [
                    self.bot.connection.request(method, s, *args, **kwargs) 
                    for s in self.sources if s != self.bot.connection.local_name
                ]
                tasks.append(coro(self.bot.connection.local_name, *args, **kwargs))

                if method == "get_shards":
                    data = await gather(*tasks)
                    d = []
                    for i in data:
                        d.extend(i)
                    return d
                elif method not in EXCLUDED_METHODS:
                    data = chain(await gather(*tasks))
                else:
                    return await gather(*tasks)
                
                return data

            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                
                logger.warning(f"IPC request failed (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                await asyncio.sleep(self.retry_delay * (attempt + 1))
                
                # Try to reconnect if needed
                if not self.bot.connection.authorized:
                    try:
                        await self.bot.connection.start()
                    except Exception as e:
                        logger.error(f"Failed to restart IPC connection: {str(e)}")

    async def get_shards(self, source: str, *args, **kwargs):
        data = []
        for shard_id, shard in self.bot.shards.items():
            guilds = [g for g in self.bot.guilds if g.shard_id == shard_id]
            users = sum([len(g.members) for g in guilds])
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
    
    async def ipc_get_user_from_cache(
        self, source, user: Union[User, int]
    ):
        try:
            u = await UserConverter().convert(self.bot, user)
        except:
            return None
        if u:
            return u._to_minimal_user_json()
        else:
            return None
        
    async def get_guild(self, source: str, guild_id: int):
        if guild := self.bot.get_guild(guild_id):
            return self.transformers.transform_guild(guild)
        else:
            return None
        
    async def leave_guild(self, source: str, guild_id: int):
        if guild := self.bot.get_guild(guild_id):
            await guild.leave()
            return True
        return False
        
    async def get_member(self, source: str, guild_id: int, user_id: int):
        if guild := self.bot.get_guild(guild_id):
            if member := guild.get_member(user_id):
                return self.transformers.transform_member(member)
        return None
    
    async def get_user_mutuals(self, source: str, user_id: int, count: Optional[bool] = False):
        if not (user := self.bot.get_user(user_id)):
            if count:
                return 0
            else:
                return []
        if count:
            return len(user.mutual_guilds)
        else:
            return [asDict(guild) for guild in user.mutual_guilds]


    async def get_channel(self, source: str, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel:
            return self.transformers.transform_channel(channel)
        else:
            return None
