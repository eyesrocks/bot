from discord.ext.commands import Context, Cog, CommandError, check, group, command, Converter
from discord import Client, Member, User, Guild, Activity
from datetime import datetime, timedelta, timezone
from aiohttp import ClientSession
from dataclasses import dataclass
from typing import Optional, Any, Union
from config import CONFIG_DICT
import humanfriendly
from asyncio import ensure_future
from pydantic import BaseModel
import humanize
from loguru import logger
from tool.greed import Greed

class Instance(Greed):
    def __init__(self, config: dict, *args: Any, **kwargs: Any):
        super().__init__(config, *args, **kwargs)

    async def on_guild_join(self, guild: Guild):
        data = await self.db.fetchrow("""SELECT * FROM instances WHERE bot_id = $1""", self.user.id)
        if data:
            if data.guild_id == guild.id:
                return

        logger.info(f"leaving guild {guild.name} due to it not being whitelisted inside of {data}")
        return await guild.leave()

    async def on_ready(self):
        for guild in self.guilds:
            await self.on_guild_join(guild)
        return await super().on_ready()

    async def setup_hook(self) -> None:
        if data := await self.db.fetchrow("""SELECT status_type, status_text FROM instances WHERE bot_id = $1""", self.user.id):
            await self.change_presence(activity = Activity(name=data.status_text, type=data.status_type, url="https://twitch.tv/clock"))
        return await super().setup_connection(False)

    async def start(self, token: str, reconnect: bool = True) -> None:
        await super().login(token)
        ensure_future(super().connect(reconnect = True))

async def setup_connection(bot: Greed, instance: Instance) -> bool:
    instance.db = bot.db
    instance.redis = bot.redis
    instance.cache = bot.cache
    return True

@dataclass
class TokenResponse:
    token: str
    data: Any

class TokenConverter(Converter):
    async def convert(self, ctx: Context, argument: str):
        async with ClientSession() as session:
            async with session.get(f"https://discord.com/api/v10/users/@me", headers = {"Authorization": f"Bot {argument}"}) as response:
                if response.status != 200:
                    raise CommandError("That is not a valid bot token")
                data = await response.json()
        return TokenResponse(token = argument, data = data)
    

async def get_int(argument: str):
    t = ""
    for s in argument:
        try:
            d = int(s)
            t += f"{d}"
        except Exception:
            pass
    return t


class TimeFrame(Converter):
    async def convert(self, ctx: Context, argument: str):
        if argument in ("indefinite", "infinite", "forever"):
            return None
        try:
            converted = humanfriendly.parse_timespan(argument)
        except Exception:
            converted = humanfriendly.parse_timespan(
                f"{await get_int(argument)} minutes"
            )
        return converted


VARMAP = {
    "status": {
        "aliases": ["stat", "activity", "presence"],
        "value": 1,
    },
    "support": {
        "aliases": ["server", "invite"],
        "value": 2,
    },
}

class VariableResponse(BaseModel):
    variable: int
    name: str

class Variable(Converter):
    async def convert(self, ctx: Context, argument: str):
        arg = argument.lower()
        r = None
        for key, value in VARMAP.items():
            if arg == key.lower():
                r = key
                break
            if arg in value["aliases"]:
                r = key
                break
        if not r:
            raise CommandError("that is not a valid variable")
        return VariableResponse(variable = VARMAP[r]["value"], name = r)

class Value(Converter):
    async def convert(self, ctx: Context, argument: str):
        if ":" in argument:
            key, value = argument.split(":", 1)
            return {"key": key.lower(), "value": value}
        else:
            return {"key": None, "value": argument}


def to_status_type(value: str):
    value = value.lower()
    if value in ("play", "playing"):
        return 0
    elif value in ("streaming", "stream"):
        return 1
    elif value in ("listening", "listen"):
        return 2
    elif value in ("watching", "watch"):
        return 3
    elif value in ("competing", "compete"):
        return 5
    else:
        return 4


class ActivityConverter(Converter):
    async def convert(self, ctx: Context, argument: str):
        if ":" in argument:
            status_type, text = argument.split(":", 1)
            status_type = to_status_type(status_type.lower())
        else:
            status_type = 4
            text = argument
        return {"type": status_type, "text": text}

class Instances(Cog):
    def __init__(self, bot: Client):
        self.bot = bot
        self.bot.instances = {}

    async def change_instance_presence(self, source: str, user_id: int, status_type: int, status_text: str):
        if user_id not in self.bot.instances:
            return
        bot = self.bot.instances[user_id]
        await bot.change_presence(activity=Activity(name=status_text, type=status_type, url="https://twitch.tv/clock"))
        return True

    async def cog_load(self):
        try:
            await self.bot.connection.add_route(self.change_instance_presence)
        except Exception:
            pass
        if self.bot.connection.local_name != "cluster1":
            return
        async def check(row):
            user_data = await self.bot.db.fetchrow("""SELECT expiration FROM instance_whitelist WHERE user_id = $1""", row.user_id)
            if not user_data:
                return
            if user_data.get("expiration"):
                if row.expiration < datetime.now(timezone.utc):
                    if row.user_id not in self.bot.instances:
                        for source in self.bot.ipc.sources:
                            if source != self.bot.connection.local_name:
                                if await self.bot.connection.request("get_instance", source = source, user_id = row.user_id) != False:
                                    return
                        await self.start_instance(row.token, row.user_id)
            else:
                if row.user_id not in self.bot.instances:
                    for source in self.bot.ipc.sources:
                        if source != self.bot.connection.local_name:
                            if await self.bot.connection.request("get_instance", source = source, user_id = row.user_id) != False:
                                return
                    await self.start_instance(row.token, row.user_id)

        for row in await self.bot.db.fetch("""SELECT * FROM instances"""):
            try:
                await check(row)
            except Exception:
                pass

    async def cog_unload(self):
       for s in self.bot.instances.values():
           try:
               await s.close()
           except Exception:
               pass

    async def cog_check(self, ctx: Context):
        if ctx.author.id in self.bot.owner_ids:
            return True
        if not (row := await self.bot.db.fetchrow("""SELECT * FROM instance_whitelist WHERE user_id = $1""", ctx.author.id, cached = False)):
            raise CommandError("you haven't purchased an instance")
        if row.expiration:
            if row.expiration < datetime.now(timezone.utc):
                raise CommandError("your instance has expired")
        return True
    
    async def start_instance(self, token: str, user_id: int):
        config = CONFIG_DICT.copy()
        config["token"] = token
        bot = Instance(config, local_address = "23.160.168.126")
        await setup_connection(self.bot, bot)
        await bot.start(token = config["token"], reconnect = True)
        self.bot.instances[user_id] = bot
        return True
    
    async def stop_instance(self, token: str, user_id: int):
        if user_id in self.bot.instances:
            await self.bot.instances[user_id].close()
            self.bot.instances.pop(user_id)
        return True
    
    async def restart_instance(self, token: str, user_id: int):
        if user_id in self.bot.instances:
            await self.stop_instance(token, user_id)
            await self.start_instance(token, user_id)
        return True

    async def change_pres(self, ctx: Context, status_type: int, status_text: str):
        try:
            await self.change_instance_presence("yes", ctx.author.id, status_type, status_text)
        except Exception: pass
        for s in self.bot.ipc.sources:
            if s != self.bot.connection.local_name:
                await self.bot.connection.request("change_instance_presence", source = s, user_id = ctx.author.id, status_type = status_type, status_text = status_text)
        return True
    
    @group(name = "instance", brief = "manage your instance of greed", invoke_without_command = True)
    async def instance(self, ctx: Context):
        return await ctx.send_help(ctx.command)
    
#    @name(name = "edit", brief = "edit a variable regarding your instance of greed", example = ",instance edit status streaming:whats up")
    async def instance_edit(self, ctx: Context, variable: Variable, *, value: Value):
        return

    @instance.command(name="status", brief = "edit the status of your instance", example = ",instance status streaming:whats up my ninja fortnite ballsers")
    async def instance_status(self, ctx: Context, *, status: ActivityConverter):
        await self.bot.db.execute("""UPDATE instances SET status_type = $1, status_text = $2 WHERE user_id = $3""", status['type'], status['text'], ctx.author.id)
        await self.change_pres(ctx, status['type'], status['text'])
        return await ctx.success("successfully changed your instance's status")

    @instance.command(name = "create", brief = "create your instance of greed", example = ",instance create Mz.dasdssa 373747373")
    async def instance_create(self, ctx: Context, token: TokenConverter, guild_id: int):
        await self.bot.db.execute("""INSERT INTO instances (user_id, token, bot_id, guild_id) VALUES($1, $2, $3, $4) ON CONFLICT(user_id) DO UPDATE SET token = excluded.token, bot_id = excluded.bot_id, guild_id = excluded.guild_id""", ctx.author.id, token.token, int(token.data["id"]), guild_id)
        try:
            await self.start_instance(token.token, ctx.author.id)
        except Exception as e:
            return await ctx.fail(f"an error occurred {str(e)}")
        return await ctx.success(f"successfully created your instance under **{token.data['username']}#{token.data['discriminator']}**, you can restart it using `{ctx.prefix}instance restart`")

    @instance.command(name = "restart", brief = "restart your instance of greed")
    async def instance_restart(self, ctx: Context):
        if not (instance := await self.bot.db.fetchrow("""SELECT token, bot_id FROM instances WHERE user_id = $1""", ctx.author.id)):
            raise CommandError(f"you have not created your instance using `{ctx.prefix}instance create`")
        for source in self.bot.ipc.sources:
            if source != self.bot.connection.local_name:
                if await self.bot.connection.request("get_instance", source = source, user_id = ctx.author.id) != False:
                    await self.bot.connection.request("restart_instance", source = source, token = instance.token, user_id = ctx.author.id)
                    return await ctx.success(f"restarting your instance now..")
        if ctx.author.id in self.bot.instances:
            ensure_future(self.restart_instance(instance.token, ctx.author.id))
            return await ctx.success("restarting your instance now..")
        else:
            ensure_future(self.start_instance(instance.token, ctx.author.id))
            return await ctx.success("starting your instance now..")
        
    @instance.command(name = "whitelist", brief = "whitelist a user to use instances", example = ",instance whitelist @aiohttp 3d")
    async def instance_whitelist(self, ctx: Context, user: Union[Member, User], timeframe: TimeFrame):
        if ctx.author.id not in self.bot.owner_ids:
            return
        if timeframe:
            delta = timedelta(seconds = timeframe)
            exp88iration = datetime.now() + delta
        else:
            expiration = None
        await self.bot.db.execute("""INSERT INTO instance_whitelist (user_id, expiration) VALUES($1, $2) ON CONFLICT(user_id) DO UPDATE SET expiration = excluded.expiration""", user.id, expiration)
        return await ctx.success(f"successfully whitelisted {user.mention} {'**indefinitely**' if not expiration else f'for **{humanize.naturaldelta(delta)}**'}")
        
    @instance.command(name = "unwhitelist", brief = "unwhitelist a user from using instances", example = ",instance unwhitelist @aiohttp")
    async def instance_unwhitelist(self, ctx: Context, user: Union[Member, User]):
        if ctx.author.id not in self.bot.owner_ids:
            return
        await self.bot.db.execute("""DELETE FROM instance_whitelist WHERE user_id = $1""", user.id)
        row = await self.bot.db.fetchrow("""SELECT token FROM instances WHERE user_id = $1""", user.id)
        await self.bot.db.execute("""DELETE FROM instances WHERE user_id = $1""", user.id)
        for source in self.bot.ipc.sources:
            if source != self.bot.connection.local_name:
                if await self.bot.connection.request("get_instance", source = source, user_id = ctx.author.id) != False:
                    await self.bot.connection.request("stop_instance", source = source, token = row.token, user_id = user.id)
        if row:
            await self.stop_instance(row.token, user.id)
        return await ctx.success(f"successfully ended {user.mention}'s instance")
    


    
async def setup(bot: Client):
    await bot.add_cog(Instances(bot))
