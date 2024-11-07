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
    "get_channel_count"   
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
        await self.bot.connection.start()
        coroutine_names = self.get_coroutine_names_with_kwarg("source")
        await gather(*[self.bot.connection.add_route(getattr(self, coroutine)) for coroutine in coroutine_names])
        logger.info(f"successfully setup the IPC routes")

        



    async def roundtrip(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Send a message to the IPC server and return the response"""
        coro = getattr(self, method)
        tasks = [self.bot.connection.request(method, s, *args, **kwargs) for s in self.sources if s != self.bot.connection.local_name]
        tasks.append(coro(self.bot.connection.local_name, *args, **kwargs))
        if method not in EXCLUDED_METHODS:
            data = chain(await gather(*tasks))
        else:
            return await gather(*tasks)

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

    
