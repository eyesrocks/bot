import traceback, os, datetime, discord, orjson, aiohttp, json, asyncio, tuuid, time, redis, discord_ios
from tool.important.subclasses.context import NonRetardedCache, MSG, reskin
from tool.rival import RivalAPI, get_statistics as get_stats, Statistics
from tool.important import Cache, Context, Database, MyHelpCommand, Red
from tool.important.subclasses.interaction import GreedInteraction
from typing import Any, Dict, Optional, Union, Callable, Sequence
from tool.important.services.Webhook import Webhook as Webhooks
from tool.important.subclasses.parser import Script
from discord.http import handle_message_parameters
from discord.types.snowflake import SnowflakeList
from tool.important.runner import RebootRunner
from tool.worker import start_dask, offloaded
from tool.views import VoicemasterInterface
from tool.processing import Transformers
from rival_tools import ratelimit, lock
from tool.important.levels import Level
from cogs.voicemaster import VmButtons
from tool.aliases import fill_commands
from tool.views import GiveawayView
from tool.paginate import Paginate
from tool.managers.ipc import IPC
from discord.utils import MISSING
from aiohttp import ClientSession
from tool.modlogs import Handler
from contextlib import suppress
from tool.snipe import Snipe
from .emotes import EMOJIS
from psutil import Process
from loguru import logger
from cashews import cache
from pathlib import Path
from sys import stdout
from discord import (
    Message,
    Guild,
    AuditLogEntry,
    TextChannel,
    Embed,
    File,
    GuildSticker,
    StickerItem,
    AllowedMentions,
    MessageReference,
    PartialMessage,
    Interaction,
    AllowedMentions,
    Activity,
    CustomActivity
)
from discord.ui import View
from discord.ext import commands
from discord.ext.commands import (
    AutoShardedBot as Bot,
    when_mentioned_or,
    BotMissingPermissions,
    BucketType,
    CommandOnCooldown,
    CooldownMapping,
    BucketType,
)
# from cogs.tickets import TicketView
# from tool import MemberConverter
Interaction.success = GreedInteraction.success
Interaction.fail = GreedInteraction.fail
Interaction.warning = GreedInteraction.warning
Interaction.normal = GreedInteraction.normal
Interaction.voice_client = GreedInteraction.voice_client
Message.edit = MSG.edit

get_changes = Union[
    Guild,
    AuditLogEntry,
]
@offloaded
def read_file(filepath: str, mode: str = "rb"):
    with open(filepath, mode) as file:
        data = file.read()
    return data


loguru = False
cache.setup("mem://")

if loguru:
    logger.remove()
    logger.add(
        stdout,
        level="INFO",
        colorize=True,
        enqueue=True,
        backtrace=True,
        format="(<magenta>greed:{function}</magenta>) <yellow>@</yellow> <fg #BBAAEE>{message}</fg #BBAAEE>",
    )
else:
    logger.add(
        stdout,
        level="INFO",
        colorize=True,
        enqueue=True,
        backtrace=True,
        format="(<magenta>greed:{function}</magenta>) <yellow>@</yellow> <fg #BBAAEE>{message}</fg #BBAAEE>",
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


class RatelimitType:
    GUILD = "guild"
    USER = "user"
    CHANNEL = "channel"
    GLOBAL = "global"


class RatelimitManager:
    def __init__(self, bot):
        self.bot = bot
        self.redis = None

        self.limits = {
            RatelimitType.GUILD: (10, 10),
            RatelimitType.USER: (3, 5),
            RatelimitType.CHANNEL: (10, 5),
            RatelimitType.GLOBAL: (300, 60),
        }

    async def check_ratelimit(self, type: str, id: int) -> tuple[bool, float]:
        """Check if an entity is ratelimited
        Returns (is_ratelimited, retry_after)
        """
        limit, window = self.limits[type]
        key = f"ratelimit:{type}:{id}"

        current = await self.redis.zcount(key, min=time.time() - window, max="+inf")

        if current >= limit:
            scores = await self.redis.zrange(key, -limit, -limit, withscores=True)
            if scores:
                retry_after = scores[0][1] + window - time.time()
                if retry_after > 0:
                    return True, retry_after

        await self.redis.zadd(key, {str(time.time()): time.time()})
        await self.redis.expire(key, window)

        return False, 0

    async def check_all(
        self, guild_id: int, channel_id: int, user_id: int
    ) -> tuple[bool, float]:
        """Check all applicable ratelimits for a command"""
        checks = [
            (RatelimitType.GUILD, guild_id),
            (RatelimitType.CHANNEL, channel_id),
            (RatelimitType.USER, user_id),
            (RatelimitType.GLOBAL, 0),
        ]

        for type, id in checks:
            is_limited, retry_after = await self.check_ratelimit(type, id)
            if is_limited:
                return True, retry_after

        return False, 0

    async def adjust_limits(self):
        """Automatically adjust ratelimits based on usage patterns"""
        while True:
            try:
                global_usage = await self.redis.zcard(
                    f"ratelimit:{RatelimitType.GLOBAL}:0"
                )

                if global_usage > self.limits[RatelimitType.GLOBAL][0] * 0.9:
                    self.limits[RatelimitType.GLOBAL] = (
                        int(self.limits[RatelimitType.GLOBAL][0] * 1.2),
                        self.limits[RatelimitType.GLOBAL][1],
                    )

            except Exception as e:
                logger.error(f"Error in ratelimit adjustment: {e}")

            await asyncio.sleep(60)

    async def setup(self):
        """Initialize redis connection and start background tasks"""
        self.redis = self.bot.redis
        self.bot.loop.create_task(self.adjust_limits())


class Greed(Bot):
    def __init__(self, config: Dict[str, Any], *args, **kwargs) -> None:
        super().__init__(
            command_prefix=self.get_prefix,
            allowed_mentions=AllowedMentions(
                users=True, roles=False, everyone=False
            ),
            activity=Activity(
                type=CustomActivity,
                name=" ",
                state="🔗 /greedbot",
            ),
            strip_after_prefix=True,
            intents=config["intents"],
            case_insensitive=True,
            owner_ids=config["owners"],
            anti_cloudflare_ban=True,
            chunk_guilds_at_startup=False,
            enable_debug_events=False,
            auto_update=True,
            delay_ready=True,
            help_command=MyHelpCommand(),
            #            proxy=f"{user_pass}{ips[1]}",
            *args,
            **kwargs,
        )
        self.proxies = ips
        self.lim = [977036206179233862]
        self.dev = [744806691396124673, 863914425445908490, 352190010998390796]
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
        self.color = 0x2F4672
        self.afks = {}
        self.command_dict = None
        self._closing_task = None
        self.transformers = Transformers(self)
        self.process = Process(os.getpid())
        self.support_server = "https://discord.gg/greedbot"
        self.author_only_message = "**only the `author` can use this**"
        self.cache = NonRetardedCache(self)
        self.http.iterate_local_addresses = False
        self.loaded = False
        self.guilds_maxed = True
        self.to_send = []
        self.authentication = [
            self.config["token"],
            "MTE0OTUzNTgzNDc1Njg3NDI1MA.GSOfph.hblFTcu2t1qmcPB61TnnB_eIIu2hNXRWk6QnSo",
        ]
        self.command_count = len(
            [
                cmd
                for cmd in list(self.walk_commands())
                if cmd.cog_name not in ("Jishaku", "events", "Owner")
            ]
        )
        self._cd = CooldownMapping.from_cooldown(
            3.0, 6.0, BucketType.user
        )
        self.__cd = CooldownMapping.from_cooldown(
            1.0, 3.0, BucketType.user
        )
        self.eros = "52ab341c-58c0-42f2-83ba-bde19f15facc"
        self.check(self.command_check)
        self.ratelimits = RatelimitManager(self)

    async def send_raw(
        self,
        channel_id: int,
        content: Optional[str] = None,
        *,
        tts: bool = False,
        embed: Optional[Embed] = None,
        embeds: Optional[Sequence[Embed]] = None,
        file: Optional[File] = None,
        files: Optional[Sequence[File]] = None,
        stickers: Optional[Sequence[Union[GuildSticker, StickerItem]]] = None,
        delete_after: Optional[float] = None,
        nonce: Optional[Union[str, int]] = None,
        allowed_mentions: Optional[AllowedMentions] = None,
        reference: Optional[Union[Message, MessageReference, PartialMessage]] = None,
        mention_author: Optional[bool] = None,
        view: Optional[View] = None,
        suppress_embeds: bool = False,
        silent: bool = False,
        **kwargs,
    ) -> Message:
        """|coro|

        Sends a message to the destination with the content given.

        The content must be a type that can convert to a string through ``str(content)``.
        If the content is set to ``None`` (the default), then the ``embed`` parameter must
        be provided.

        To upload a single file, the ``file`` parameter should be used with a
        single :class:`~discord.File` object. To upload multiple files, the ``files``
        parameter should be used with a :class:`list` of :class:`~discord.File` objects.
        **Specifying both parameters will lead to an exception**.

        To upload a single embed, the ``embed`` parameter should be used with a
        single :class:`~discord.Embed` object. To upload multiple embeds, the ``embeds``
        parameter should be used with a :class:`list` of :class:`~discord.Embed` objects.
        **Specifying both parameters will lead to an exception**.

        .. versionchanged:: 2.0
            This function will now raise :exc:`TypeError` or
            :exc:`ValueError` instead of ``InvalidArgument``.

        Parameters
        ------------
        content: Optional[:class:`str`]
            The content of the message to send.
        tts: :class:`bool`
            Indicates if the message should be sent using text-to-speech.
        embed: :class:`~discord.Embed`
            The rich embed for the content.
        embeds: List[:class:`~discord.Embed`]
            A list of embeds to upload. Must be a maximum of 10.

            .. versionadded:: 2.0
        file: :class:`~discord.File`
            The file to upload.
        files: List[:class:`~discord.File`]
            A list of files to upload. Must be a maximum of 10.
        nonce: :class:`int`
            The nonce to use for sending this message. If the message was successfully sent,
            then the message will have a nonce with this value.
        delete_after: :class:`float`
            If provided, the number of seconds to wait in the background
            before deleting the message we just sent. If the deletion fails,
            then it is silently ignored.
        allowed_mentions: :class:`~discord.AllowedMentions`
            Controls the mentions being processed in this message. If this is
            passed, then the object is merged with :attr:`~discord.Client.allowed_mentions`.
            The merging behaviour only overrides attributes that have been explicitly passed
            to the object, otherwise it uses the attributes set in :attr:`~discord.Client.allowed_mentions`.
            If no object is passed at all then the defaults given by :attr:`~discord.Client.allowed_mentions`
            are used instead.

            .. versionadded:: 1.4

        reference: Union[:class:`~discord.Message`, :class:`~discord.MessageReference`, :class:`~discord.PartialMessage`]
            A reference to the :class:`~discord.Message` to which you are replying, this can be created using
            :meth:`~discord.Message.to_reference` or passed directly as a :class:`~discord.Message`. You can control
            whether this mentions the author of the referenced message using the :attr:`~discord.AllowedMentions.replied_user`
            attribute of ``allowed_mentions`` or by setting ``mention_author``.

            .. versionadded:: 1.6

        mention_author: Optional[:class:`bool`]
            If set, overrides the :attr:`~discord.AllowedMentions.replied_user` attribute of ``allowed_mentions``.

            .. versionadded:: 1.6
        view: :class:`discord.ui.View`
            A Discord UI View to add to the message.

            .. versionadded:: 2.0
        stickers: Sequence[Union[:class:`~discord.GuildSticker`, :class:`~discord.StickerItem`]]
            A list of stickers to upload. Must be a maximum of 3.

            .. versionadded:: 2.0
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message. This sends the message without any embeds if set to ``True``.

            .. versionadded:: 2.0
        silent: :class:`bool`
            Whether to suppress push and desktop notifications for the message. This will increment the mention counter
            in the UI, but will not actually send a notification.

            .. versionadded:: 2.2

        Raises
        --------
        ~discord.HTTPException
            Sending the message failed.
        ~discord.Forbidden
            You do not have the proper permissions to send the message.
        ValueError
            The ``files`` or ``embeds`` list is not of the appropriate size.
        TypeError
            You specified both ``file`` and ``files``,
            or you specified both ``embed`` and ``embeds``,
            or the ``reference`` object is not a :class:`~discord.Message`,
            :class:`~discord.MessageReference` or :class:`~discord.PartialMessage`.

        Returns
        ---------
        :class:`~discord.Message`
            The message that was sent.
        """

        state = self._connection
        content = str(content) if content is not None else None
        previous_allowed_mention = state.allowed_mentions

        if stickers is not None:
            sticker_ids: SnowflakeList = [sticker.id for sticker in stickers]
        else:
            sticker_ids = MISSING

        if reference is not None:
            try:
                reference_dict = reference.to_message_reference_dict()
            except AttributeError:
                raise TypeError(
                    "reference parameter must be Message, MessageReference, or PartialMessage"
                ) from None
        else:
            reference_dict = MISSING

        if view and not hasattr(view, "__discord_ui_view__"):
            raise TypeError(
                f"view parameter must be View not {view.__class__.__name__}"
            )

        if suppress_embeds or silent:
            from discord.message import MessageFlags  # circular import

            flags = MessageFlags._from_value(0)
            flags.suppress_embeds = suppress_embeds
            flags.suppress_notifications = silent
        else:
            flags = MISSING

        with handle_message_parameters(
            content=content,
            tts=tts,
            file=file if file is not None else MISSING,
            files=files if files is not None else MISSING,
            embed=embed if embed is not None else MISSING,
            embeds=embeds if embeds is not None else MISSING,
            nonce=nonce,
            allowed_mentions=allowed_mentions,
            message_reference=reference_dict,
            previous_allowed_mentions=previous_allowed_mention,
            mention_author=mention_author,
            stickers=sticker_ids,
            view=view,
            flags=flags,
        ) as params:
            data = await state.http.send_message(channel_id, params=params, **kwargs)

        channel = self.get_channel(channel_id)
        ret = state.create_message(channel=channel, data=data)
        if view and not view.is_finished():
            state.store_view(view, ret.id)

        if delete_after is not None:
            await ret.delete(delay=delete_after)
        return ret

    async def on_rival_information(self, data: Any, id: str):
        method = data["method"]
        logger.info(f"received information with the method {method}")
        if method == "send_message":
            embed = data["kwargs"].get("embed")
            content = data["kwargs"].get("content")
            channel_id = data["kwargs"]["channel_id"]
            if channel := self.get_channel(int(channel_id)):
                kwargs = {}
                if embed:
                    embed = discord.Embed.from_dict(embed)
                    kwargs["embed"] = embed
                if content:
                    kwargs["content"] = content
                await channel.send(**kwargs)
        elif method == "username_change":
            self.dispatch("username_change", data["username"])
        elif method == "vanity_change":
            self.dispatch("vanity_change", data["vanity"])
        elif method == "handle_guild_join_notification":
            try:
                channel = self.get_channel(1326366925877674024)
                if not channel:
                    logger.error("Notification channel not found")
                    return False

                try:
                    await channel.send(
                        f"Join our networks - {data.get('guild_name', 'Unknown')}\n"
                        f"Join link: {data.get('invite', 'No invite available')}"
                    )
                except Exception as e:
                    logger.error(f"Failed to send channel notification: {e}")
                    return False

                try:
                    owner_id = data.get("owner_id")
                    if owner_id:
                        owner = await self.fetch_user(owner_id)
                        if owner:
                            await owner.send(
                                f"Thank you for adding me to {data.get('guild_name')}! "
                                f"Feel free to join our support server: {self.support_server}"
                            )
                except discord.Forbidden:
                    logger.warning(f"Could not DM owner {data.get('owner_id')}")
                except Exception as e:
                    logger.error(f"Error in owner notification: {e}")

                return True

            except Exception as e:
                logger.error(f"Error handling notification: {e}", exc_info=True)
                return False

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
        return "%d%s" % (
            n,
            "tsnrhtdd"[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10 :: 4],
        )

    def handle_ready(self):
        self.connected.set()

    def get_command_dict(self) -> list:
        if self.command_dict:
            return self.command_dict

        def get_command_invocations(command, prefix=""):
            invocations = []

            base_command = prefix + command.name
            invocations.append(base_command)

            for alias in command.aliases:
                invocations.append(prefix + alias)

            if isinstance(command, commands.Group):
                for subcommand in command.commands:
                    sub_invocations = get_command_invocations(
                        subcommand, prefix=base_command + " "
                    )
                    for alias in command.aliases:
                        sub_invocations.extend(
                            get_command_invocations(
                                subcommand, prefix=prefix + alias + " "
                            )
                        )
                        invocations.extend(sub_invocations)

            return invocations

        self.command_dict = []
        for command in self.walk_commands():
            for invocation in get_command_invocations(command):
                self.command_dict.append(invocation)
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
            kwargs["name"] = f"{self.user.name} Webhook"
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
                    wh.append(
                        [chl.id, chl.name, (await chl.create_webhook(**kwargs)).url]
                    )
                return json.dumps(wh)

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
        return len(self.guilds)

    async def user_count(self) -> int:
        return sum(i for i in self.get_all_members())

    async def role_count(self) -> int:
        if self.user.name != "greed":
            return sum(len(guild.roles) for guild in self.guilds)
        return sum(await self.ipc.roundtrip("get_role_count"))

    async def channel_count(self) -> int:
        if self.user.name != "greed":
            return sum(len(guild.channels) for guild in self.guilds)
        return sum(await self.ipc.roundtrip("get_channel_count"))

    async def get_channels(self, channel_id: int) -> list[discord.TextChannel]:
        """Get channels from all clusters via IPC and return valid TextChannel objects"""
        if not isinstance(channel_id, int):
            raise TypeError(f"channel_id must be int, not {type(channel_id)}")

        channels = []
        try:
            responses = await self.ipc.roundtrip("get_channel", channel_id=channel_id)

            # Log the raw responses for debugging
            logger.debug(f"Got channel responses: {responses}")

            if not responses:
                logger.debug(f"No responses for channel {channel_id}")
                return channels

            for channel_data in responses:
                try:
                    if not channel_data:
                        logger.debug(f"Empty channel data in response")
                        continue

                    if isinstance(channel_data, dict):
                        guild_id = channel_data.get("guild_id")
                        guild = self.get_guild(guild_id)

                        if not guild:
                            logger.debug(f"Could not find guild {guild_id}")
                            continue

                        channel = guild.get_channel(channel_data.get("id"))
                        if isinstance(channel, discord.TextChannel):
                            channels.append(channel)
                        else:
                            logger.debug(
                                f"Channel {channel_data.get('id')} is not TextChannel: {type(channel)}"
                            )

                    elif isinstance(channel_data, discord.TextChannel):
                        channels.append(channel_data)
                    else:
                        logger.debug(
                            f"Unexpected channel data type: {type(channel_data)}"
                        )

                except Exception as e:
                    logger.error(f"Error processing channel data {channel_data}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to get channels from IPC: {e}")
            raise  # Re-raise to handle at higher level

        return channels

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
                name=f"{self.user.name}'s default prefix is set to `,`",
                value=f"> To change the prefix use `,prefix (prefix)`\n> Ensure the bot's role is within the guild's top 5 roles for {self.user.name} to function correctly",
                inline=False,
            )
            .add_field(
                name="Commands to help you get started:",
                value="> **,setup** - Creates a jail and log channel along with the jail role \n> **,voicemaster setup** - Creates join to create voice channels\n> **,filter setup** - Initializes a setup for automod to moderate\n> **,antinuke setup** - Creates the antinuke setup to keep your server safe",
                inline=False,
            )
            .set_author(
                name=f"{self.user.name} is now in your server!",
                icon_url=self.user.avatar.url,
            )
        )

    async def command_check(self, ctx):
        if not ctx.guild or not ctx.channel:
            return False

        if await self.is_owner(ctx.author):
            return True

        try:
            missing_perms = [
                perm
                for perm in ["send_messages", "embed_links", "attach_files"]
                if not getattr(ctx.channel.permissions_for(ctx.me), perm)
            ]
            if missing_perms:
                raise BotMissingPermissions(missing_perms)
        except Exception:
            return False

        # Check blacklist before hitting rate limits
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

        # Now check rate limits
        try:
            is_limited, retry_after = await self.ratelimits.check_all(
                ctx.guild.id, ctx.channel.id, ctx.author.id
            )
            if is_limited:
                if retry_after > 1:
                    if await self.glory_cache.ratelimited(
                        "ratelimit_check", 1, retry_after
                    ):
                        await ctx.warning(
                            f"You're being ratelimited! Please wait {retry_after:.1f} seconds."
                        )
                        raise CommandOnCooldown(
                            None, retry_after, BucketType.default
                        )
        except redis.RedisError as e:
            logger.error(f"Redis error in ratelimit check: {e}")
            # Fallback to basic cooldown if Redis fails
            bucket = self._cd.get_bucket(ctx.message)
            retry_after = bucket.update_rate_limit()
            if retry_after:
                raise CommandOnCooldown(
                    None, retry_after, BucketType.default
                )

        # Check command restrictions last since they require DB query
        restrictions = await self.db.fetch(
            """SELECT role_id FROM command_restriction WHERE guild_id = $1 AND command_name = $2""",
            ctx.guild.id,
            ctx.command.qualified_name,
        )
        if restrictions:
            roles = [ctx.guild.get_role(role_id[0]) for role_id in restrictions]
            if any(role in ctx.author.roles for role in roles if role):
                mention = ", ".join(role.mention for role in roles if role)
                await ctx.fail(
                    f"You have one of the following roles {mention} and cannot use this command"
                )
                return False

        # Load commands if needed
        if not hasattr(self, "command_list"):
            await fill_commands(ctx)

        return True

    async def get_statistics(self, force: bool = False) -> Statistics:
        try:
            if not hasattr(self, "stats") or force:
                self.stats = await asyncio.wait_for(
                    get_stats(self), timeout=5.0  # 5 second timeout
                )
            stats = self.stats.copy()
            stats["uptime"] = str(discord.utils.format_dt(self.startup_time, style="R"))
            return Statistics(**stats)

        except asyncio.TimeoutError:
            logger.error("Timeout getting statistics")
            raise
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            raise

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
            embed.set_footer(text=f"Page 1/1 ({plural(rows).do_plural(type.title())})")
            return await ctx.send(embed=embed)

    async def __load(self, cog: Union[str, Path]):
        try:
            if isinstance(cog, Path):
                # Get relative path from cogs/ and convert to module path
                rel_path = cog.relative_to("cogs")
                # Remove .py extension and convert path separators to dots
                module_path = f"cogs.{str(rel_path.with_suffix('')).replace('/', '.')}"
                # If it's a submodule like cogs.economy.shop, change to cogs.economy
                if module_path.count(".") > 1:
                    module_path = ".".join(module_path.split(".")[:2])
            else:
                module_path = cog

            await self.load_extension(module_path)
            logger.info(f"[ Loaded ] {module_path}")
        except commands.errors.ExtensionAlreadyLoaded:
            pass
        except Exception as e:
            tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.info(f"Failed to load {cog} due to exception: {tb}")

    async def load_cogs(self):
        if self.loaded is not False:
            return

        cogs_path = Path("cogs/")
        cogs = []

        for path in cogs_path.rglob("*.py"):
            if self.user.name != "greed" and "instances" in str(path):
                continue
            cogs.append(path)

        await asyncio.gather(*[self.__load(c) for c in cogs])
        self.loaded = True

    async def go(self, *args, **kwargs) -> None:
        self.http.proxy = ""
        await super().start(self.config["token"], *args, **kwargs)

    def run(self, *args, **kwargs) -> None:
        super().run(self.config["token"], *args, **kwargs)

    async def request_invite(self, user_id: int):
        return
        link = f"https://discord.com/oauth2/authorize?client_id={user_id}&permissions=0&scope=applications.commands%20bot"
        session = ClientSession()
        webhook = discord.Webhook.from_url(
            session=session,
            url="https://discord.com/api/webhooks/1312506540271472731/aHazRNKWx4w12CZI5zN_v5EwrOfmlZs7KZ1pSzqYMtIwCWjYV_q2G_FwABhQ2tgHCKEf",
        )
        await webhook.send(
            embed=discord.Embed(
                title="Instance Requesting Invite",
                description=f"Invite it [HERE]({link})",
            )
        )

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
        if self.user.name == "greed":
            if not self.loaded:
                self.ipc = IPC(self)
                await self.ipc.setup()
        else:
            if not self.get_guild(1361040232035909704):
                await self.request_invite(self.user.id)
        if not self.loaded:
            await self.levels.setup(self)
            self.runner = RebootRunner(self, "cogs")
            await self.load_cogs()
            await self.runner.start()
            self.loaded = True
        # await self.check_guilds()
        await self.load_extension("tool.important.subclasses.web")
        log.info("Loaded all cogs")

    async def load_cog(self, cog: str):
        try:
            await self.load_extension(f"cogs.{cog}")
        except Exception:
            traceback.logger.info_exc()

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
        self.dask = await start_dask("eyes", "127.0.0.1:8787")
        await self.setup_emojis()

    async def setup_hook(self) -> None:
        return await self.setup_connection()

    async def setup_connection(self, connect: Optional[bool] = True) -> None:
        asyncio.ensure_future(self.setup_dask())
        if connect:
            self.redis = Red(host="localhost", port=6379, db=0, decode_responses=True)
            await self.redis.from_url("redis://localhost:6379")
            self.db: Database = Database()
            await self.db.connect()
            self.loop.create_task(self.cache.setup_cache())
            await self.ratelimits.setup()  # Initialize redis after connection
        self.session = ClientSession()
        self._connection.db = self.db
        self._connection.botstate = self
        self.levels = Level(0.5, self)
        self.add_view(VmButtons(self))
        self.add_view(VoicemasterInterface(self))
        self.add_view(GiveawayView())
        #        self.add_view(TicketView(self, True))
        os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
        os.environ["JISHAKU_RETAIN"] = "True"
        await self.load_extension("jishaku")

    async def create_embed(self, code: str, **kwargs):
        builder = Script(code, **kwargs)
        await builder.compile()
        return builder

    def build_error(self, message: str) -> dict:
        return {
            "embed": discord.Embed(
                color=0xFFA500,
                description=f"{EMOJIS['icons_warning']} {message}",
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
        if not message.guild:
            return

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
        if not message.guild:
            return
        if message.author.bot:
            return
        if message.channel.permissions_for(message.guild.me).send_messages is False:
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
                f"<:info:1336901763235581992> **Greed prefix** is  `{server_prefix or ','}`\n-# <:line:1336409552786161724> selfprefix is set to **{user_prefix}**"
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

        if len(channels) < 5:
            try:
                return await guild.owner.send(
                    embed=discord.Embed(
                        description="> Left due to the guild not having over **25 members**",
                        color=self.color,
                    )
                )
            except Exception:
                return None

        try:
            return await channels[0].send(
                embed=discord.Embed(
                    description="> Left due to the guild not having over **2 members**",
                    color=self.color,
                )
            )
        except Exception:
            return None

    @cache(key="emojis", ttl="300")
    async def get_emojis(self):
        return await self.fetch_application_emojis()

    async def create_emoji(self, name: str, data: bytes):
        app_emojis = await self.get_emojis()
        for emoji in app_emojis:
            if emoji.name == name:
                EMOJIS[name] = str(emoji)
                return emoji
        try:
            emoji = await self.create_application_emoji(name=name, image=data)
            EMOJIS[name] = str(emoji)
            return emoji
        except discord.HTTPException as e:
            logger.error(f"Failed to create emoji {name}: {e}")
            return None

    async def setup_emojis(self):
        for key, value in EMOJIS.items():
            if value == "":
                try:
                    for ext in (".png", ".gif"):
                        path = f"assets/{key}{ext}"
                        if os.path.exists(path):
                            file_data = await read_file(path)
                            await self.create_emoji(key, file_data)
                            break
                    else:
                        logger.error(f"Warning: No emoji file found for {key}")
                except Exception as e:
                    logger.error(f"Error setting up emoji {key}: {e}")

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
            return await guild.leave()
        if guild == self.get_guild(1361040232035909704):
            return

        if len(guild.members) < 25:
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
                description=f"{EMOJIS['icons_warning']} {ctx.author.mention}: Error occurred while performing command **{ctx.command.qualified_name}**. Use the given error code to report it to the developers in the [support server]({self.support_server})",
                color=0xFFA500,
            ),
        )

    async def hierarchy(
        self,
        ctx: Context,
        member: Union[discord.Member, discord.User],
        allow_self: bool = False,
    ) -> bool:

        bot_member = ctx.guild.me
        author = ctx.author

        if isinstance(member, discord.User):
            return True

        if (
            isinstance(member, discord.Member)
            and bot_member.top_role <= member.top_role
        ):
            await ctx.warning(
                f"I don't have high enough roles to perform this action on {member.mention}"
            )
            return False

        if author.id == member.id:
            if not allow_self:
                await ctx.warning("You cannot use this command on yourself")
                return False
            return True

        if author.id == ctx.guild.owner_id:
            return True

        if member.id == ctx.guild.owner_id:
            await ctx.warning("You cannot use this command on the server owner")
            return False

        # Check if author is a ClientUser (bot) or doesn't have roles
        if isinstance(author, discord.ClientUser) or not hasattr(author, "top_role"):
            return True

        if author.top_role.is_default():
            await ctx.warning("You need roles with permissions to use this command")
            return False

        if author.top_role <= member.top_role:
            if author.top_role == member.top_role:
                await ctx.warning(
                    "You cannot target users with the same top role as you"
                )
            else:
                await ctx.warning("You cannot target users with higher roles than you")
            return False

        return True

    async def check_guild_ratelimit(self, guild_id: int) -> tuple[bool, float]:
        """
        Check if a guild is being ratelimited due to command spam.
        Returns (is_ratelimited, retry_after)
        """
        # Get recent command usage in this guild
        key = f"guild_commands:{guild_id}"

        # Get command usage in last 10 seconds
        current = await self.redis.zcount(key, min=time.time() - 10, max="+inf")

        # If more than 50 commands in 10 seconds across all users
        if current >= 50:
            # Get earliest command timestamp that puts us over limit
            scores = await self.redis.zrange(key, -50, -50, withscores=True)
            if scores:
                retry_after = scores[0][1] + 10 - time.time()
                if retry_after > 0:
                    return True, retry_after

        # Add this command execution
        await self.redis.zadd(key, {str(time.time()): time.time()})
        # Expire after 10 seconds
        await self.redis.expire(key, 10)

        return False, 0

    async def check_guild_count(self) -> int:
        """Get total guild count across all clusters"""
        try:
            counts = await self.ipc.roundtrip("get_guild_count")
            if not counts:
                logger.warning("Received no guild counts from clusters")
                return 0

            # Filter out None values and log them
            valid_counts = []
            for i, count in enumerate(counts):
                if count is None:
                    logger.warning(f"Cluster {i} returned None for guild count")
                else:
                    valid_counts.append(count)

            return sum(valid_counts)

        except Exception as e:
            logger.error(f"Failed to get guild counts: {e}")
            return 0
