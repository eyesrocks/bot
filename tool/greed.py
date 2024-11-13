#import log

#log.make_dask_sink("rival")

import discord_ios  # type: ignore # noqa: F401
import traceback
import os
import discord
import datetime
import orjson
import aiohttp
from tool.important.levels import Level
import json
from tool.worker import start_dask  # type: ignore
import asyncio  # type: ignore
import tuuid
from tool.views import VoicemasterInterface  # type: ignore
from loguru import logger
from voice import Whisper
from tool.important.services.Webhook import Webhook as Webhooks
# from logging import getLogger
# logger = getLogger(__name__)
from typing import Any, Dict, Optional, Union, Callable
from psutil import Process
from aiohttp import ClientSession
from discord import Color, Message, Guild, AuditLogEntry, TextChannel
from discord.ext import commands
from discord.ext.commands import (
    AutoShardedBot as Bot,
    when_mentioned_or,
    BotMissingPermissions,
)
from tool.aliases import handle_aliases, CommandAlias, fill_commands  # type: ignore
from tool.modlogs import Handler  # type: ignore

# from cogs.tickets import TicketView
from tool.processing import Transformers  # type: ignore # noqa: E402
from tool.managers.ipc import IPC
from cogs.voicemaster import VmButtons
from tool.important import Cache, Context, Database, MyHelpCommand, Red  # type: ignore
from tool.important.subclasses.parser import Script  # type: ignore
from tool.important.subclasses.context import NonRetardedCache  # type: ignore
from tool.important.runner import RebootRunner  # type: ignore
from tool.snipe import Snipe, SnipeError  # type: ignore
from tool.important.subclasses.command import RolePosition  # type: ignore
from tool.views import GiveawayView, PrivacyConfirmation  # type: ignore
from tool.important.subclasses.interaction import GreedInteraction  # type: ignore # noqa: F401
from _types import catch
# from tool import MemberConverter
from rival_tools import ratelimit, lock  # type: ignore
from tool.rival import RivalAPI, get_statistics as get_stats, Statistics  # type: ignore
from tool.paginate import Paginate  # type: ignore
from sys import stdout

discord.Interaction.success = GreedInteraction.success
discord.Interaction.fail = GreedInteraction.fail
discord.Interaction.warning = GreedInteraction.warning
discord.Interaction.normal = GreedInteraction.normal
discord.Interaction.voice_client = GreedInteraction.voice_client
# discord.message.Message.edit = edit
get_changes = Union[
    Guild,
    AuditLogEntry,
]
loguru = False

if loguru:
    logger.remove()
    logger.add(
        stdout,
        level="INFO",
        colorize=True,
        enqueue=True,
        backtrace=True,
        format="<cyan>[</cyan><blue>{time:YYYY-MM-DD HH:MM:SS}</blue><cyan>]</cyan> (<magenta>greed:{function}</magenta>) <yellow>@</yellow> <fg #BBAAEE>{message}</fg #BBAAEE>",
    )


class iteration(object):
    def __init__(self, data: Any):
        self.data = data
        self.index = -1

    def __iter__(self):
        return self

    def __next__(self):
        self.index += 1
        if self.index > len(self.data) - 1:
            self.index = 0
        return self.data[self.index]


log = logger
user_pass = "http://envjafpk:bltpo5w914k6@"
ips = [
    "38.154.227.167:5868",
    "185.199.229.156:7492",
    "185.199.228.220:7300",
    "185.199.231.45:8382",
]
for i in ips:
    ips[ips.index(i)] = f"{user_pass}{i}"


class Greed(Bot):
    def __init__(self, config: Dict[str, Any], *args, **kwargs) -> None:
        super().__init__(
            command_prefix=self.get_prefix,
            allowed_mentions=discord.AllowedMentions(
                users=True, roles=False, everyone=False
            ),
            strip_after_prefix=True,
            intents=config["intents"],
            case_insensitive=True,
            owner_ids=config["owners"],
            anti_cloudflare_ban=True,
            enable_debug_events=True,
            delay_ready=True,
            help_command=MyHelpCommand(),
            #            proxy=f"{user_pass}{ips[1]}",
            *args,
            **kwargs,
        )
        self.proxies = ips
        self.modlogs = Handler(self)
        self.config = config
        self.webhook = Webhooks(self)
        self.paginators = Paginate(self)
        self.domain = self.config["domain"]
        self.startup_time = datetime.datetime.now()
        self.http.proxy = ""
        self.glory_cache = Cache(self)
        self.rival = RivalAPI(self)
        self.snipes = Snipe(self)
        self.avatar_limit = 50
        self.color = 0x456BB2
        self.afks = {}
        self.command_dict = None
        self.transformers = Transformers(self)
        self.process = Process(os.getpid())
        self.domain = "https://greed.my"
        self.support_server = "https://discord.gg/pomice"
        self.author_only_message = "**only the `author` can use this**"
        self.cache = NonRetardedCache(self)
        self.http.iterate_local_addresses = False
        self.loaded = False
        self.guilds_maxed = True
        self.to_send = []
        self.authentication = [
            self.config["token"],
            "MTE4ODg1OTEwNzcwMTE2NjE2MQ.G22nb2.219btG_P7Y5MN0JlyU7OJHvIkdQ8dM9N6ybIJA",
        ]
        self.command_count = len(
            [
                cmd
                for cmd in list(self.walk_commands())
                if cmd.cog_name not in ("Jishaku", "events", "Owner")
            ]
        )
        self._cd = commands.CooldownMapping.from_cooldown(
            5.0, 10.0, commands.BucketType.user
        )
        self.__cd = commands.CooldownMapping.from_cooldown(
            1.0, 3.0, commands.BucketType.user
        )
        self.eros = "52ab341c-58c0-42f2-83ba-bde19f15facc"
        self.check(self.command_check)
        self.before_invoke(self.before_all_commands)



    def get_timestamp(self, dt: Optional[datetime.datetime] = None, style: str = "R"):
        if dt is None:
            dt = datetime.datetime.now()
        return discord.utils.format_dt(dt, style=style)

    async def execute_function(self, func: Callable, *args, **kwargs) -> Optional[Any]:
        with logger.catch(reraise=True):
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

    @staticmethod
    def ordinal(n: int) -> str:
        """Convert an integer into its ordinal representation, e.g., 1 -> 1st"""
        n = int(n)
        return "%d%s" % (n, "tsnrhtdd"[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10::4])

    def handle_ready(self):
        self.connected.set()

    def get_command_dict(self) -> list:
        if self.command_dict:
            return self.command_dict
        def get_command_invocations(command, prefix=''):
            invocations = []

            base_command = prefix + command.name
            invocations.append(base_command)

            for alias in command.aliases:
                invocations.append(prefix + alias)

            if isinstance(command, commands.Group):
                for subcommand in command.commands:
                    sub_invocations = get_command_invocations(subcommand, prefix=base_command + ' ')
                    for alias in command.aliases:
                        sub_invocations.extend(get_command_invocations(subcommand, prefix=prefix + alias + ' '))
                        invocations.extend(sub_invocations)

            return invocations
        self.command_dict = []
        for command in self.walk_commands():
            for invocation in get_command_invocations(command): self.command_dict.append(invocation)
        return self.command_dict

    async def get_reference(self, message: discord.Message):
        if message.reference:
            if msg := message.reference.cached_message:
                return msg
            else:
                g = self.get_guild(message.reference.guild_id)
                if not g:
                    return None
                c = g.get_channel(message.reference.channel_id)
                if not c:
                    return None
                return await c.fetch_message(message.reference.message_id)
        return None

    async def do_webhooks(
        self, channel: TextChannel, webhooks: Optional[str] = None, **kwargs
    ):
        if not kwargs.get("name"):
            kwargs["name"] = "greed"
        async with aiohttp.ClientSession() as session:
            if webhooks:
                wh = json.loads(webhooks)
                for w in wh:
                    try:
                        _ = discord.Webhook.from_url(w[2], session=session)
                        await _.edit(**kwargs)
                    except Exception:
                        try:
                            sh = (
                                await channel.guild.get_channel(w[0]).create_webhook(
                                    **kwargs
                                )
                            ).url
                            wh[wh.index(w)] = [w[0], w[1], sh]
                        except Exception:
                            wh.remove(w)
                return json.dumps(wh)
            else:
                wh = []
                for chl in channel.guild.text_channels:
                    wh.append([chl.id, chl.name, (await chl.create_webhook(**kwargs)).url])
                return json.dumps(wh)

    async def before_all_commands(self, ctx: Context):
        ctx.timer = datetime.datetime.now().timestamp()
        if ctx.command is not None:
#            if not await self.db.fetchrow("""SELECT * FROM reskin.server WHERE guild_id = $1""", ctx.guild.id):
            if "purge" not in ctx.command.qualified_name:
                if (
                    ctx.channel.permissions_for(ctx.guild.me).send_messages
                    and ctx.channel.permissions_for(ctx.guild.me).embed_links
                    and ctx.channel.permissions_for(ctx.guild.me).attach_files
                ):
                    try:
                        await ctx.typing()
                    except Exception:
                        pass

    async def get_image(self, ctx: Context, *args):
        if len(ctx.message.attachments) > 0:
            return ctx.message.attachments[0].url
        elif ctx.message.reference:
            if msg := await self.get_message(
                ctx.channel, ctx.message.reference.message_id
            ):
                if len(msg.attachments) > 0:
                    return msg.attachments[0].url
                else:
                    logger.info(
                        f"there are no attachments for {msg} : {msg.attachments}"
                    )
            else:
                logger.info("could not get message")
        else:
            for i in args:
                if i.startswith("http"):
                    return i
        return None

    async def on_command_completion(self, ctx: Context):
        await self.db.execute(
            """
            INSERT INTO command_usage (guild_id, user_id, command_name, command_type)
                VALUES ($1,$2,$3,$4)
            ON CONFLICT (guild_id, user_id, command_name) DO UPDATE SET
    uses = command_usage.uses + 1;
            """,
            ctx.guild.id,
            ctx.author.id,
            ctx.command.qualified_name,
            "internal",
        )
        logger.info(f"{ctx.guild.id} > {ctx.author.name}: {ctx.message.content}")

    def is_touchable(self, obj: Union[discord.Role, discord.Member]) -> bool:
        def touchable(role: discord.Role) -> bool:
            guild = role.guild
            list(guild.roles)
            if role >= guild.me.top_role:
                return False
            return True

        if isinstance(obj, discord.Member):
            return touchable(obj.top_role)
        else:
            return touchable(obj)

    async def get_message(self, channel: discord.TextChannel, message_id: int):
        logger.info(f"getting message {message_id} in {channel.name}")
        if message := discord.utils.get(self.cached_messages, id=message_id):
            logger.info(f"getting it returned type {type(message)}")
            return message
        else:
            if m := await channel.fetch_message(message_id):
                logger.info(f"fetched message {m.id} in {channel.name}")
                return m
        return None

    def check_bot_hierarchy(self, guild: discord.Guild) -> bool:
        roles = sorted(guild.roles, key=lambda x: x.position, reverse=True)
        roles = roles[:5]
        if guild.me.top_role not in roles:
            del roles
            return False
        return True


    async def guild_count(self) -> int:
        return sum(i for i in await self.ipc.roundtrip("get_guild_count"))

    async def user_count(self) -> int:
        return sum(i for i in await self.ipc.roundtrip("get_user_count"))

    async def role_count(self) -> int:
        return sum(i for i in await self.ipc.roundtrip("get_role_count"))

    async def channel_count(self) -> int:
        return sum(i for i in await self.ipc.roundtrip("get_channel_count"))

    @property
    def invite_url(self, client_id: Optional[int] = None) -> str:
        if self.user.id == 1188859107701166161 and self.guilds_maxed is True:
            if len(self.guilds) <= 99:
                return discord.utils.oauth_url(
                    self.bot2.user.id,
                    scopes=["bot", "applications.commands"],
                    permissions=discord.Permissions(8),
                )
        return discord.utils.oauth_url(
            client_id or self.user.id,
            scopes=["bot", "applications.commands"],
            permissions=discord.Permissions(8),
        )

    async def limit_avatarhistory(self, user_id: int):
        data = await self.db.fetch(
            """SELECT * FROM avatars WHERE user_id = $1 ORDER BY time ASC""", user_id
        )
        if len(data) > self.avatar_limit:
            avatars_to_delete = [
                d["avatar"] for d in data[: len(data) - self.avatar_limit]
            ]
            await self.db.execute(
                """DELETE FROM avatars WHERE avatar = ANY($1::text[])""",
                avatars_to_delete,
            )
        return True

    async def get_changes(self, before: get_changes, after: get_changes):
        return

    async def process_commands(self, message: Message):
        if not message.guild:
            return

        # check = await self.db.fetchrow(
        #     """
        #     SELECT * FROM blacklisted
        #     WHERE (object_id = $1 AND object_type = $2)
        #     OR (object_id = $3 AND object_type = $4)
        # """,
        #     message.author.id,
        #     "user_id",
        #     message.guild.id,
        #     "guild_id",
        # )
        # if check:
        #     return
        if not self.is_ready():
            return

        return await super().process_commands(message)

    async def log_command(self, ctx: Context):
        log.info(
            f"{ctx.author} ({ctx.author.id}) executed {ctx.command} in {ctx.guild} ({ctx.guild.id})."
        )

    async def join_message(self, guild: discord.Guild):
        channels = [
            channel
            for channel in guild.text_channels
            if channel.permissions_for(guild.me).send_messages is True
        ]
        return await channels[0].send(
            embed=discord.Embed(
                title="Need Help?",
                url=self.domain,
                description=f"Join our [support server]({self.support_server}) for help",
                color=self.color,
            )
            .add_field(
                name="Greed's default prefix is set to `,`",
                value="> To change the prefix use `,prefix (prefix)`\n> Ensure the bot's role is within the guild's top 5 roles for Greed to function correctly",
                inline=False,
            )
            .add_field(
                name="Commands to help you get started:",
                value="> **,setup** - Creates a jail and log channel along with the jail role \n> **,voicemaster setup** - Creates join to create voice channels\n> **,filter setup** - Initializes a setup for automod to moderate\n> **,antinuke setup** - Creates the antinuke setup to keep your server safe",
                inline=False,
            )
            .set_author(
                name="Greed",
                icon_url=self.user.avatar.url,  # Assuming self.user is your bot user object
            )
        )

    async def command_check(self, ctx):
        if not hasattr(self, "command_list"):
            await fill_commands(ctx)
        if await ctx.bot.is_owner(ctx.author):
            return True

        if not ctx.channel or not ctx.guild:
            return False

        missing_perms = [
            perm for perm in ["send_messages", "embed_links", "attach_files"]
            if not getattr(ctx.channel.permissions_for(ctx.me), perm)
        ]
        if missing_perms:
            raise BotMissingPermissions(missing_perms)

        check = await self.db.fetchrow(
            """
            SELECT * FROM blacklisted
            WHERE (object_id = $1 AND object_type = $2)
            OR (object_id = $3 AND object_type = $4)
            """,
            ctx.author.id,
            "user_id",
            ctx.guild.id,
            "guild_id",
        )
        if check:
            return False

        restrictions = await self.db.fetch(
            """SELECT role_id FROM command_restriction WHERE guild_id = $1 AND command_name = $2""",
            ctx.guild.id,
            ctx.command.qualified_name,
        )
        if restrictions:
            roles = [ctx.guild.get_role(role_id) for role_id in restrictions]
            if any(role in ctx.author.roles for role in roles):
                mention = ", ".join(role.mention for role in roles if role)
                await ctx.fail(f"you have one of the following roles {mention} and cannot use this command")
                return False

        retry_after = None
        if ctx.command.qualified_name == "reset":
            if retry_after := await ctx.bot.glory_cache.ratelimited(
                f"rl:user_commands{ctx.author.id}", 2, 4
            ):
                if retry_after:
                    raise commands.CommandOnCooldown(None, retry_after, None)
            return True

        if not await self.db.fetchval(
            """SELECT state FROM terms_agreement WHERE user_id = $1""", ctx.author.id
        ):
            message = await ctx.normal(
                f"Greed bot will store your data. **By continuing to use our services**, you agree to our **[policy]({self.domain}/terms)**"
            )
            view = PrivacyConfirmation(bot=self, message=message, invoker=ctx.author)
            await message.edit(view=view)
            await view.wait()

            state = view.value if view.value is not None else False
            await self.db.execute(
                """INSERT INTO terms_agreement (user_id, state) VALUES ($1, $2) ON CONFLICT DO NOTHING;""",
                ctx.author.id,
                state,
            )
            if not state:
                await message.edit(
                    embed=discord.Embed(
                        description=f"> {ctx.author.mention} has **declined our privacy policy** and as a result you have been **blacklisted from using any greed command or feature**. Feel free to accept our [**policy**](https://greed.bot/terms) using `{ctx.prefix}reset`",
                        color=self.color,
                    )
                )
                return False
            await message.delete()

        data = await self.db.fetchrow(
            """SELECT command, channels FROM disabled_commands WHERE guild_id = $1 AND command = $2""",
            ctx.guild.id,
            ctx.command.qualified_name.lower(),
        )
        if data:
            channels = json.loads(data["channels"])
            if not channels or ctx.channel.id in channels:
                raise discord.ext.commands.errors.CommandError(
                    f"`{ctx.command.qualified_name.lower()}` has been **disabled by moderators**"
                )

        if str(ctx.invoked_with).lower() == "help":
            if retry_after := await ctx.bot.glory_cache.ratelimited(
                f"rl:user_commands{ctx.author.id}", 5, 5
            ):
                raise commands.CommandOnCooldown(None, retry_after, None)
        else:
            cooldown_args = ctx.command.cooldown_args or {}
            bucket_type = cooldown_args.get("type", "user")
            limit, interval = cooldown_args.get("limit", (3, 5))

            key = (
                f"rl:user_commands:{ctx.guild.id}:{ctx.command.qualified_name}"
                if bucket_type.lower() == "guild"
                else f"rl:user_commands:{ctx.author.id}:{ctx.command.qualified_name}"
            )
            retry_after = await ctx.bot.glory_cache.ratelimited(key, limit, interval)
            if retry_after:
                raise commands.CommandOnCooldown(None, retry_after, None)

        return True

    async def get_statistics(self, force: bool = False) -> Statistics:
        if not hasattr(self, "stats"):
            self.stats = await get_stats(self)
        if force is True:
            self.stats = await get_stats(self)
        stats = self.stats.copy()
        stats["uptime"] = str(discord.utils.format_dt(self.startup_time, style="R"))
        _ = Statistics(**stats)
        del stats
        return _

    async def paginate(
        self, ctx: Context, embed: discord.Embed, rows: list, per_page: int = 10
    ):
        from cogs.music import chunk_list

        embeds = []
        if len(rows) > per_page:
            chunks = chunk_list(rows, per_page)
            for chunk in chunks:
                rows = [f"{c}\n" for c in chunk]
                embed = embed.copy()
                embed.description = "".join(r for r in rows)
                embeds.append(embed)
            try:
                del chunks
            except Exception:
                pass
            return await ctx.alternative_paginate(embeds)
        else:
            embed.description = "".join(f"{r}\n" for r in rows)
            return await ctx.send(embed=embed)

    async def dummy_paginator(
        self,
        ctx: Context,
        embed: discord.Embed,
        rows: list,
        per_page: int = 10,
        type: str = "entry",
    ):
        from tool.music import chunk_list, plural  # type: ignore

        embeds = []
        embeds = []
        if len(rows) > per_page:
            chunks = chunk_list(rows, per_page)
            for i, chunk in enumerate(chunks, start=1):
                rows = [f"{c}\n" for c in chunk]
                embed = embed.copy()
                embed.description = "".join(r for r in rows)
                embed.set_footer(
                    text=f"Page {i}/{len(chunks)} ({plural(rows).do_plural(type.title())})"
                )
                embeds.append(embed)
            try:
                del chunks
            except Exception:
                pass
            return await ctx.alternative_paginate(embeds)
        else:
            embed.description = "".join(f"{r}\n" for r in rows)
            # t = plural(len(rows)):type.title()
            embed.set_footer(text=f"Page 1/1 ({plural(rows).do_plural(type.title())})")
            return await ctx.send(embed=embed)

    async def __load(self, cog: str):
        try:
            await self.load_extension(cog)
            logger.info(f"[ Loaded ] {cog}")
        except commands.errors.ExtensionAlreadyLoaded:
            pass
        except Exception as e:
            tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.info(f"Failed to load {cog} due to exception: {tb}")

    async def load_cogs(self):
        if self.loaded is not False:
            return
        from pathlib import Path

        cogs = [
            f'cogs.{str(c).split("/")[-1].split(".")[0]}'
            for c in Path("cogs/").glob("*.py")
        ]
        await asyncio.gather(*[self.__load(c) for c in cogs])
        self.loaded = True

    async def go(self, *args, **kwargs) -> None:
        self.http.proxy = ""
        await super().start(self.config["token"], *args, **kwargs)
        
    def run(self, *args, **kwargs) -> None:
        super().run(self.config["token"], *args, **kwargs)

    async def on_ready(self) -> None:
        log.info(f"Logged in as {self.user} ({self.user.id})")
        # self.browser = Browser(
        #     executable_path="/usr/bin/google-chrome",
        #     args=(
        #         "--ignore-certificate-errors",
        #         "--disable-extensions",
        #         "--no-sandbox",
        #         "--headless",
        #     ),
        # )

        # await self.browser.__aenter__()
        self.ipc = IPC(self)
        await self.ipc.setup()
        await self.levels.setup(self)
        await self.load_cogs()
        self.runner = RebootRunner(self, "cogs")
        await self.load_cogs()
        await self.runner.start()
        #await self.check_guilds()
        log.info("Loaded all cogs")

    async def load_cog(self, cog: str):
        try:
            await self.load_extension(f"cogs.{cog}")
        except Exception:
            traceback.print_exc()

    @lock("fetch_message:{channel.id}")
    @ratelimit("rl:fetch_message:{channel.id}", 2, 5, True)
    async def fetch_message(
        self, channel: discord.TextChannel, id: int
    ) -> Optional[discord.Message]:
        if message := discord.utils.get(self.cached_messages, id=id):
            return message
        message = await channel.fetch_message(id)
        if message not in self._connection._messages:
            self._connection._messages.append(message)
        return message

    async def setup_dask(self):
        self.dask = await start_dask(self, "127.0.0.1:8787")

    async def setup_hook(self) -> None:
        asyncio.ensure_future(self.setup_dask())
        self.redis = Red(host="localhost", port=6379, db=0, decode_responses=True)
        await self.redis.from_url("redis://localhost:6379")
        self.session = ClientSession()
        self.db: Database = Database()
        await self.db.connect()
        self._connection.db = self.db
        self._connection.botstate = self
        self.loop.create_task(self.cache.setup_cache())
        self.levels = Level(0.5, self)
    #    await self.levels.setup(self)
        self.add_view(VmButtons(self))
        self.add_view(VoicemasterInterface(self))
        self.add_view(GiveawayView())
        #        self.add_view(TicketView(self, True))
        os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
        os.environ["JISHAKU_RETAIN"] = "True"
        await self.load_extension("jishaku")
        await self.load_extension("tool.important.subclasses.web")

    async def create_embed(self, code: str, **kwargs):
        builder = Script(code, **kwargs)
        await builder.compile()
        return builder

    def build_error(self, message: str) -> dict:
        return {
            "embed": discord.Embed(
                color=0xFFA500,
                description=f"<:warns:1302330367323148399> {message}",
            )
        }

    async def send_embed(self, destination: discord.TextChannel, code: str, **kwargs):
        view = kwargs.pop("view", None)
        builder = await self.create_embed(code, **kwargs)
        try:
            return await builder.send(destination, view=view)
        except discord.HTTPException as exc:
            if exc.code == 50006:
                return await destination.send(
                    **self.build_error(
                        "Something went wrong while parsing this embed script."
                    )
                )
            raise
    async def get_prefix(self, message: Message):

        user_prefix = await self.db.fetchval(
            """SELECT prefix
            FROM selfprefix
            WHERE user_id = $1""",
            message.author.id,
        )

        server_prefix = await self.db.fetchval(
            """SELECT prefix
            FROM prefixes
            WHERE guild_id = $1""",
            message.guild.id,
        )


        default_prefix = ","

        if user_prefix and message.content.strip().startswith(user_prefix):
            return when_mentioned_or(user_prefix)(self, message)
        return when_mentioned_or(server_prefix or default_prefix)(self, message)


    async def get_context(self, message, *, cls=Context):
        return await super().get_context(message, cls=cls)

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content == after.content:
            return
        if not after.edited_at:
            return
        #        if after.edited_at - after.created_at > timedelta(minutes=1):
        #           return
        if not before.author.bot:
            await self.on_message(after)

    #            self.dispatch('message',after)
    #        await self.process_commands(after)

    # async def dump_commandsXD(self):
    #     commands = {}
    #     def get_usage(command):
    #         if not command.clean_params:
    #             return "None"
    #         return ", ".join(m for m in [str(c) for c in command.clean_params.keys()])

    #     def get_aliases(command):
    #         if len(command.aliases) == 0:
    #             return ["None"]
    #         return command.aliases

    #     def get_category(command):
    #         if "settings" not in command.qualified_name:
    #             return command.cog_name
    #         else:
    #             return "settings"

    #     excluded = ["owner", "errors", "jishaku"]
    #     for command in self.walk_commands():
    #         if cog := command.cog_name:
    #             if cog.lower() in excluded:
    #                 continue
    #             if command.hidden or not command.brief:
    #                 continue
    #             if not commands.get(command.cog_name):
    #                 commands[command.cog_name] = []
    #             if not command.permissions:
    #                 permissions = ["send_messages"]
    #             else:
    #                 permissions = command.permissions
    #             commands[command.cog_name].append(
    #                 {
    #                     "name": command.qualified_name,
    #                     "help": command.brief or "",
    #                     "brief": [permissions.replace("_", " ").title()]
    #                     if not isinstance(permissions, list)
    #                     else [_.replace("_", " ").title() for _ in permissions],
    #                     "usage": get_usage(command),
    #                     "example": command.example or ""
    #                 }
    #             )
    #     with open(
    #         "/root/commands.json", "wb"
    #     ) as file:
    #         file.write(orjson.dumps(commands))

    async def on_message(self, message: discord.Message) -> None:
        if not self.is_ready():
            return
        if message.author.bot:
            return
        if message.channel.permissions_for(message.guild.me).send_messages is False:
            return
        if not message.guild:
            return
        self.dispatch("on_valid_message", message)
        if message.mentions_bot(strict=True):
            if await self.glory_cache.ratelimited("prefix_pull", 1, 5) != 0:
                return
            server_prefix = await self.db.fetchval(
                """
                SELECT prefix
                FROM prefixes
                WHERE guild_id = $1""",
                message.guild.id,
            )
            user_prefix = await self.db.fetchval(
                """
                SELECT prefix
                FROM selfprefix
                WHERE user_id = $1""",
                message.author.id,
            )
            ctx = await self.get_context(message)
            if vanity := ctx.channel.guild.vanity_url:
                invite_link = vanity
            else:
                if check := await self.db.fetchval(
                    """SELECT invite FROM guild_invites WHERE guild_id = $1""",
                    ctx.guild.id,
                ):
                    invite_link = check
                else:
                    invite_link = await ctx.channel.create_invite()
                    await self.db.execute(
                        """INSERT INTO guild_invites (guild_id,invite) VALUES($1,$2) ON CONFLICT(guild_id) DO UPDATE SET invite = excluded.invite""",
                        ctx.guild.id,
                        f"https://discord.gg/{invite_link.code}",
                    )
            return await ctx.normal(
                f"[**Guild Prefix**]({invite_link}) is set to ``{server_prefix or ','}``\nYour **Selfprefix** is set to `{user_prefix}`"
            )
        await self.process_commands(message)

    async def avatar_to_file(self, user: discord.User, url: str) -> str:
        return f"{user.id}.{url.split('.')[-1].split('?')[0]}"

    async def leave_message(self, guild: discord.Guild) -> Optional[discord.Message]:
        channels = [
            channel
            for channel in guild.text_channels
            if channel.permissions_for(guild.me).send_messages is True
        ]

        if len(channels) == 0:
            try:
                return await guild.owner.send(embed = discord.Embed(
                    description=f"> Left due to the guild not having over **30 members**",
                    color=self.color,
                ))
            except Exception:
                return
        try:
            return await channels[0].send(
                embed=discord.Embed(
                    description=f"> Left due to the guild not having over **30 members**",
                    color=self.color,
                )
            )
        except Exception:
            return

    async def on_guild_join(self, guild: discord.Guild):
        await self.wait_until_ready()
        await guild.chunk(cache=True)
        check = await self.db.fetchrow(
            """
            SELECT * FROM blacklisted
            WHERE (object_id = $1 AND object_type = $2)
            OR (object_id = $3 AND object_type = $4)
        """,
            guild.owner.id,
            "user_id",
            guild.id,
            "guild_id",
        )
        if check:
            await guild.leave()
            return
        if len(guild.members) < 30:
            # if len(guild.members) < 75:
            #     if owner := guild.owner:
            #         try:
            #             await owner.send(
            #                 embed=discord.Embed(
            #                     description="> I have left your guild due to you not having **75 members**",
            #                     color=self.bot.color,
            #                 )
            #             )
            #         except Exception:
            #             pass
            #         return await guild.leave()
            await self.leave_message(guild)
            return await guild.leave()
        await self.join_message(guild)
    async def send_exception(self, ctx: Context, exception: Exception):
        code = tuuid.tuuid()
        await self.db.execute(
            """INSERT INTO traceback (command, error_code, error_message, guild_id, channel_id, user_id, content) VALUES($1, $2, $3, $4, $5, $6, $7)""",
            ctx.command.qualified_name,
            code,
            str(exception),
            ctx.guild.id,
            ctx.channel.id,
            ctx.author.id,
            ctx.message.content,
        )
        return await ctx.send(
            content=f"`{code}`",
            embed=discord.Embed(
                description=f"<:warns:1302330367323148399> {ctx.author.mention}: Error occurred while performing command **{ctx.command.qualified_name}**. Use the given error code to report it to the developers in the [support server]({self.support_server})",
                color=0xFFA500,
            ),
        )

    async def on_xdcommand_error(self, ctx: Context, exception: Exception) -> None:
        bucket = self._cd.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()
        if await self.glory_cache.ratelimited(
            f"rl:error_message:{ctx.author.id}", 1, 5
        ):
            return
        if retry_after:
            return

        error = getattr(exception, "original", exception)
        ignored = [
            commands.CommandNotFound,
        ]
        if type(exception) in ignored:
            return

        if isinstance(exception, commands.CommandOnCooldown):
            if await self.glory_cache.ratelimited(
                f"rl:cooldown_message{ctx.author.id}", 1, exception.retry_after
            ):
                return

            return await ctx.fail(
                f"Command is on a ``{exception.retry_after:.2f}s`` **cooldown**"
            )
        if isinstance(exception, commands.MissingPermissions):
            if ctx.author.id in self.owner_ids:
                return await ctx.reinvoke()
            return await ctx.fail(
                f"Must have **{', '.join(exception.missing_permissions)}** permissions"
            )
        if isinstance(exception, commands.MissingRequiredArgument):
            return await ctx.fail(f"Provide a **{exception.param.name}**")
        if isinstance(exception, commands.BadArgument):
            error = exception
            tb = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
            logger.info(tb)
            exception = (
                str(exception)
                .replace("Member", "**Member**")
                .replace("User", "**User**")
            )
            return await ctx.warning(f"{exception}")
        if isinstance(exception, commands.BadUnionArgument):
            return await ctx.warning(f"{exception}")
        if isinstance(exception, commands.MemberNotFound):
            return await ctx.warning("That Member **not** found")
        if isinstance(exception, commands.UserNotFound):
            return await ctx.warning("That User **not** found")
        if isinstance(exception, commands.RoleNotFound):
            return await ctx.warning("That Role was **not** found")
        if isinstance(exception, commands.ChannelNotFound):
            return await ctx.warning("That Channel was **not** found")
        if isinstance(exception, commands.EmojiNotFound):
            return await ctx.warning("That **Emoji** was not found")
        if isinstance(exception, discord.ext.commands.errors.CommandError):
            return await ctx.warning(str(exception))
        if isinstance(exception, commands.CommandNotFound):
            await self.paginators.check(ctx)
            aliases = [
                CommandAlias(command=command_name, alias=alias)
                for command_name, alias in await self.db.fetch(
                    "SELECT command_name, alias FROM aliases WHERE guild_id = $1",
                    ctx.guild.id,
                )
            ]
            return await handle_aliases(ctx, aliases)
        if isinstance(exception, discord.ext.commands.errors.CheckFailure):
            return
        exc = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        if isinstance(exception, SnipeError):
            return await ctx.warning(str(exception))
        log.error(
            f'{type(error).__name__:25} > {ctx.guild} | {ctx.author} "{ctx.message.content}" \n {error} \n {exc}'
        )
        if isinstance(exception, RolePosition):
            return await ctx.warning(str(exception))
        if hasattr(exception, "message"):
            return await ctx.warning(exception.message.split(":")[-1])
        if "Missing Permissions" in str(exception):
            return await ctx.warning(
                "Due to hierarchy position I could not edit that object"
            )
        return await self.send_exception(
            ctx, exception
        )  # await ctx.warning(str(exception))

    async def hierarchy(
        self,
        ctx: Context,
        member: discord.Member,
        author: bool = False,
    ):
        if isinstance(member, discord.User):
            return True

        elif ctx.guild.me.top_role <= member.top_role:
            await ctx.warning(f"The role of {member.mention} is **higher than greeds**")
            return False
        elif ctx.author.id == member.id and not author:
            await ctx.warning("You **can not execute** that command on **yourself**")
            return False
        elif ctx.author.id == member.id and author:
            return True
        elif ctx.author.id == ctx.guild.owner_id:
            return True
        elif member.id == ctx.guild.owner_id:
            await ctx.warning(
                "**Can not execute** that command on the **server owner**"
            )
            return False
        elif ctx.author.top_role.is_default():
            await ctx.warning("You are **missing permissions to use this command**")
            return False
        elif ctx.author.top_role == member.top_role:
            await ctx.warning("You have the **same role** as that user")
            return False
        elif ctx.author.top_role < member.top_role:
            await ctx.warning("You **do not** have a role **higher** than that user")
            return False
        else:
            return True

    async def dump_command_page(self):
        def get_usage(command):
            if not command.clean_params:
                return "None"
            return ", ".join(m for m in [str(c) for c in command.clean_params.keys()])

        def get_aliases(command):
            if len(command.aliases) == 0:
                return ["None"]
            return command.aliases

        def get_category(command):
            if "settings" not in command.qualified_name:
                return command.cog_name
            else:
                return "settings"

        commands = list()
        excluded = ["owner", "errors", "webserver", "jishaku"]
        for command in self.walk_commands():
            if cog := command.cog_name:
                if cog.lower() in excluded:
                    continue
                if command.hidden or not command.brief:
                    continue
                if not command.permissions:
                    permissions = ["send_messages"]
                else:
                    permissions = command.permissions
                commands.append(
                    {
                        "name": command.qualified_name,
                        "help": command.brief or "",
                        "brief": [permissions.replace("_", " ").title()]
                        if not isinstance(permissions, list)
                        else [_.replace("_", " ").title() for _ in permissions],
                        "usage": get_usage(command),
                        "description": "",
                        "aliases": get_aliases(command),
                        "category": get_category(command).title(),
                    }
                )
        with open(
            "/root/greed.web/src/app/(routes)/commands/commands.json", "wb"
        ) as file:
            file.write(orjson.dumps(commands))
        proc = await asyncio.create_subprocess_shell(
            "cd ~/greed.web ; npm run build ; pm2 restart website",
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
