from __future__ import annotations
from asyncio import ensure_future, sleep
import json
from base64 import b64decode
from datetime import datetime, timedelta
from typing import Any, List, Union, Optional, Dict, Set
from discord.ext import tasks
from discord import Guild, Message, Member
import discord
import humanize
from contextlib import suppress
import orjson
import asyncio
import humanfriendly
from boltons.cacheutils import LRI
from discord.ext import commands
import contextlib
import unicodedata
from rival_tools import ratelimit  # type: ignore
from tool import expressions
from collections import defaultdict
import aiohttp
import io
from contextlib import suppress
import re  # type: ignore
from loguru import logger
from cashews import cache
import time
import asyncpg
from functools import lru_cache
from tenacity import retry, stop_after_attempt, wait_exponential
from dataclasses import dataclass
from contextlib import asynccontextmanager

cache.setup("mem://")

# Cache configuration
CACHE_TTL = 300  # 5 minutes
BATCH_SIZE = 100
MAX_RETRIES = 3

@dataclass
class GuildConfig:
    """Cached guild configuration"""
    filter_events: Set[str]
    autoroles: List[int]
    settings: Dict[str, Any]
    last_updated: float

def get_humanized_time(seconds: Union[float, int]):
    return humanize.naturaldelta(int(seconds))

url_regex = re.compile(
    r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+",
    re.I,
)

SPECIAL_ = re.compile(r"[@_!#$%^&*()<>?/\|}{~:]")


def clean_content(m: Message):
    content = SPECIAL_.sub("", m.content)
    return content


EMOJI_REGEX = re.compile(
    r"<(?P<animated>a?):(?P<name>[a-zA-Z0-9_]{2,32}):(?P<id>[0-9]{18,22})>"
)
# from loguru import logger
LIST = []


def get_emoji(emoji: Any):
    emoji = b64decode(emoji).decode()
    logger.info(emoji)
    return emoji


def format_int(n: int) -> str:
    m = humanize.intword(n)
    m = (
        m.replace(" million", "m")
        .replace(" billion", "b")
        .replace(" trillion", "t")
        .replace(" thousand", "k")
        .replace(" hundred", "")
    )
    return m


def is_unicode(emoji: str) -> bool:
    with contextlib.suppress(Exception):
        unicodedata.name(emoji)
        return True

    return False


def find_emojis(text: str) -> List[str]:
    """
    Find emojis in the given text.

    Parameters:
        text (str): The text to search for emojis.

    Returns:
        List[str]: A list of emojis found in the text.
    """

    return expressions.custom_emoji.findall(text) + expressions.unicode_emoji.findall(
        text
    )


def find_invites(text: str) -> List[str]:
    """
    Finds all Discord invite links in the given text.

    Parameters:
        text (str): A string representing the text to search for invite links.

    Return:
        List[str]: A list of Discord invite links found in the text.
    """

    return expressions.discord_invite.findall(text)


TUPLE = ()
DICT = {}

PREV, NEXT, KEY, VALUE = range(4)  # names for the link fields
DEFAULT_MAX_SIZE = 128


def default_lock_cache(max_size: int = 5000) -> dict[Any, asyncio.Lock]:
    return LRI(max_size=max_size, on_miss=lambda x: asyncio.Lock())  # type: ignore


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.locks = defaultdict(asyncio.Lock)
        self.no_snipe = []
        self.watched_users = []
        self.cooldowns = {}
        self.channel_id = 1334073848118771723
        self.last_active_voter = None
        self.cooldown_messages = {}
        self.bot.loop.create_task(self.create_countertables())
        self.maintenance = True
        self.bot.loop.create_task(self.setup_db())
        self.voicemaster_clear.start()
        self.sent_notifications = {}  # Store guild notification statuses
        self.guild_remove_time = {}   # Store timestamp of when the bot was removed
        self.system_sticker = None
        self.last_posted = None
        self.bot.audit_cache = {}
        self.guild_config_cache: Dict[int, GuildConfig] = {}
        self.connection_pool = None
        self.batch_queue = defaultdict(list)
        self.processing_locks = defaultdict(asyncio.Lock)
        self.DICT = {}

        # Start background tasks
        self.batch_processor.start()
        self.cache_cleanup.start()

    async def setup_db(self):
        """Sets up the database tables if they don't exist."""
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS labs (
                user_id BIGINT PRIMARY KEY,
                level INT DEFAULT 1,
                ampoules INT DEFAULT 1,
                earnings BIGINT DEFAULT 0,
                storage BIGINT DEFAULT 164571
            )
        """)

    async def setup_db_pool(self):
        """Initialize database connection pool"""
        if not self.connection_pool:
            self.connection_pool = await asyncpg.create_pool(
                min_size=5,
                max_size=20,
                command_timeout=60
            )

    @tasks.loop(minutes=5)
    async def cache_cleanup(self):
        """Clean expired cache entries"""
        current_time = time.time()
        expired = [
            guild_id for guild_id, config in self.guild_config_cache.items()
            if current_time - config.last_updated > CACHE_TTL
        ]
        for guild_id in expired:
            self.guild_config_cache.pop(guild_id, None)

    @tasks.loop(seconds=1)
    async def batch_processor(self):
        """Process batched operations"""
        for queue_name, queue in self.batch_queue.items():
            if len(queue) >= BATCH_SIZE:
                async with self.processing_locks[queue_name]:
                    batch = queue[:BATCH_SIZE]
                    self.batch_queue[queue_name] = queue[BATCH_SIZE:]
                    await self.process_batch(queue_name, batch)

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential())
    async def process_batch(self, queue_name: str, batch: list):
        """Process a batch of operations with retry logic"""
        if queue_name == "messages":
            await self.process_message_batch(batch)
        elif queue_name == "members":
            await self.process_member_batch(batch)

    @asynccontextmanager
    async def get_guild_config(self, guild_id: int):
        """Get cached guild configuration with automatic updates"""
        config = self.guild_config_cache.get(guild_id)
        if not config or time.time() - config.last_updated > CACHE_TTL:
            async with self.processing_locks[f"guild_config:{guild_id}"]:
                config = await self.fetch_guild_config(guild_id)
                self.guild_config_cache[guild_id] = config
        yield config

    async def fetch_guild_config(self, guild_id: int) -> GuildConfig:
        """Fetch and cache guild configuration from database"""
        async with self.bot.pool.acquire() as conn:
            # Fetch all guild settings in parallel
            filter_events, autoroles, settings = await asyncio.gather(
                conn.fetch("SELECT event FROM filter_event WHERE guild_id = $1", guild_id),
                conn.fetch("SELECT role_id FROM autorole WHERE guild_id = $1", guild_id),
                conn.fetchrow("SELECT * FROM guild_settings WHERE guild_id = $1", guild_id)
            )
        
        return GuildConfig(
            filter_events={event['event'] for event in filter_events},
            autoroles=[role['role_id'] for role in autoroles],
            settings=dict(settings) if settings else {},
            last_updated=time.time()
        )

    def cog_unload(self):
        self.voicemaster_clear.cancel()
        self.bot.levels.remove_listener(self.on_level_up, "on_text_level_up")
        self.batch_processor.cancel()
        self.cache_cleanup.cancel()

    # async def do_command_storage(self):
    #    output = ""
    #     for name, cog in sorted(self.bot.cogs.items(), key=lambda cog: cog[0].lower()):
    #          if name.lower() in ("jishaku", "Develoepr"):
    #               continue
    #
    #        _commands = list()
    #         for command in cog.walk_commands():
    #              if command.hidden:
    #                   continue
    #
    #         usage = " " + command.usage if command.usage else ""
    #          aliases = (
    #               "(" + ", ".join(command.aliases) +
    #                ")" if command.aliases else ""
    #             )
    #              if isinstance(command, commands.Group) and not command.root_parent:
    #                   _commands.append(
    #                        f"| +-- {command.name}{aliases}: {
    #                            command.brief or 'No description'}"
    #                  )
    #             elif not isinstance(command, commands.Group) and command.root_parent:
    #                _commands.append(
    #                   f"| |   +-- {command.qualified_name}{aliases}{
    #                      usage}: {command.brief or 'No description'}"
    #             )
    #        elif isinstance(command, commands.Group) and command.root_parent:
    #           _commands.append(
    #              f"| |   +-- {command.qualified_name}{
    #                 aliases}: {command.brief or 'No description'}"
    #        )
    #   else:
    #      _commands.append(
    #         f"| +-- {command.qualified_name}{aliases}{
    #            usage}: {command.brief or 'No description'}"
    #   )

    #            if _commands:
    #               output += f"+-- {name}\n" + "\n".join(_commands) + "\n"
    #
    #       return await self.bot.redis.set("commands", orjson.dumps(output))

    async def add_entry(self, audit: discord.AuditLogEntry):
        from collections import deque

        if audit.guild.id not in self.bot.audit_cache:
            self.bot.audit_cache[audit.guild.id] = deque(maxlen=10)
        if len(self.bot.audit_cache[audit.guild.id]) == 10:
            self.bot.audit_cache[audit.guild.id].pop()
        self.bot.audit_cache[audit.guild.id].insert(0, audit)

    # def random_pfp(self, message: discord.Message):
    #     return random.choice(message.attachments)

    # def random_avatar(self):
    #     choice = random.choice(self.bot.users)
    #     return choice.display_avatar.url


    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Listener that checks for offensive words and updates the count.
        """
        if message.author.bot:  # Don't process messages from bots
            return

        # List of offensive words to check for (you can customize this list)
        offensive_words = [r'\bnigga\b', r'\bniggas\b']  # Replace with your own list
        hard_r_word = r'\bnigger\b'

        # Check for any offensive word in the message
        if re.search(hard_r_word, message.content, re.IGNORECASE):
            await self.increment_offensive_word_count(message.author.id, 'hard_r')
        
        for word in offensive_words:
            if re.search(word, message.content, re.IGNORECASE):
                await self.increment_offensive_word_count(message.author.id, 'general')
                break




    @commands.Cog.listener("on_message")
    async def imageonly(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        if not message.channel.permissions_for(message.guild.me).manage_messages:
            return

        if await self.bot.db.fetchval(
            "SELECT * FROM imageonly WHERE channel_id = $1", message.channel.id
        ):
            if message.content and not message.attachments or message.embeds:
                with suppress(discord.Forbidden, discord.HTTPException):
                    await message.delete()




    @commands.Cog.listener("on_audit_log_entry_create")
    async def moderation_logs(self, entry: discord.AuditLogEntry):
        if not entry.guild.me.guild_permissions.view_audit_log:
            return
        return await self.bot.modlogs.do_log(entry)

    @commands.Cog.listener("on_text_level_up")
    async def on_level_up(self, guild: Guild, member: Member, level: int):
        async def do_roles():
            data = await self.bot.db.fetchval("""SELECT roles FROM text_level_settings WHERE guild_id = $1""", member.guild.id)
            if not data:
                return
            data = json.loads(data)
            for entry in data:
                role_level, role_id = entry
                role = guild.get_role(role_id)
                if not role:
                    continue
                if level >= role_level:
                    if role not in member.roles:
                        await member.add_roles(role, reason = "level roles")

        async def do_message():
            data = await self.bot.db.fetchval("""SELECT award_message FROM text_level_settings WHERE guild_id = $1""", guild.id)

            if not data:
                return

            data = json.loads(data)
            channel_id = data.get("channel_id")
            message = data.get("message")

            if not channel_id:
                return
            channel = guild.get_channel(channel_id)
            if not channel:
                return

            if message is None:
                message = f"Congratulations {member.mention}, you have reached level {level}!"

            message = message.replace("{level}", str(level))
            return await self.bot.send_embed(channel, message, user = member)

        await do_roles()
        await do_message()

#    @commands.Cog.listener("on_command_completion")
    async def command_moderation_logs(self, ctx: commands.Context):
        try:
            return await self.bot.modlogs.do_log(ctx)
        except Exception:
            logger.info(
                f"The below exception was raised in {ctx.command.qualified_name}"
            )

    #            raise e

    # @asyncretry(max_tries = 5, pause = 1)
    async def get_pfps(self):
        ts = datetime.now() - timedelta(days=6)
        ts = int(ts.timestamp())
        data = await self.bot.db.fetch(
            "SELECT * FROM avatars WHERE time > $1 ORDER BY RANDOM() LIMIT 10", ts
        )
        pfps = [u["avatar"] for u in data]
        if pfps != self.last_posted:
            self.last_posted = pfps
        else:
            raise TypeError()
        return pfps

    async def get_image(self, url: str) -> discord.File:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.read()
        return discord.File(
            fp=io.BytesIO(data), filename=url.split("/")[-1].split("?")[0]
        )


    # @tasks.loop(minutes=4)
    # async def do_pfp_loop(self):
    #     pfps = await self.get_pfps()
    #     embeds = [Embed(title="new pfp", url=p).set_image(url=p) for p in pfps]
    #     logger.info("sending avatars now")
    #     for guild_id, channel_id in await self.bot.db.fetch(
    #         """SELECT guild_id,channel_id FROM pfps"""
    #     ):
    #         if guild := self.bot.get_guild(int(guild_id)):
    #             if channel := guild.get_channel(int(channel_id)):
    #                 try:
    #                     await channel.send(embeds=embeds)
    #                 except Exception as e:
    #                     logger.info(f"autopfp loop raised an exception: {e}")
    #                     pass

    @commands.Cog.listener("on_member_update")
    async def booster_lost(self, before, after):
        if (
            before.guild.premium_subscriber_role in before.roles
            and before.guild.premium_subscriber_role not in after.roles
        ):
            await self.bot.db.execute(
                """INSERT INTO boosters_lost (user_id,guild_id,ts) VALUES($1,$2,$3) ON CONFLICT(user_id,guild_id) DO UPDATE SET ts = excluded.ts""",
                before.id,
                before.guild.id,
                datetime.now(),
            )

    @commands.Cog.listener("on_user_update")
    async def namehistory_event(self, before, after):
        async with self.bot.redis.lock(f"namehistory:{before.id}"):
            if before.name != after.name and before.name is not None:
                name = before.name
                nt = "username"
            elif before.global_name != after.global_name and before.global_name is not None:
                name = before.global_name
                nt = "globalname"
            elif before.display_name != after.display_name and before.display_name is not None:
                name = before.display_name
                nt = "display"
            else:
                return
                
            cache_key = f"namehistory:{before.id}:{nt}:{name}"
            if await self.bot.redis.get(cache_key):
                return
                
            await self.bot.db.execute(
                """INSERT INTO names (user_id, type, username, ts) VALUES($1,$2,$3,$4) ON CONFLICT(user_id,username,ts) DO NOTHING""",
                before.id,
                nt,
                name,
                datetime.now(),
            )
            
            await self.bot.redis.set(cache_key, "1", ex=60)

    @commands.Cog.listener("on_audit_log_entry_create")
    async def audit_log_cache(self, entry: discord.AuditLogEntry):
        return await self.add_entry(entry)

    async def forcenick_check(
        self, guild: discord.Guild, member: discord.Member
    ) -> bool:
        if guild.me.guild_permissions.administrator is False:
            return False
        if self.bot.is_touchable(member) is False:
            return False
            #        if logs := self.bot.audit_cache.get(guild.id):
            #            if [
            #                l
            #                for l in logs  # noqa: E741
            #                if l.action == discord.AuditLogAction.member_update
            #                and (l.target.id == member.id or l.user.id == member.id)
            #                and l.user.bot is not True
            #                and l.user.id != self.bot.user.id
            #            ]:
            #                return True
            return False
        return True

    async def check_rolee(self, guild: discord.Guild, role: discord.Role):
        if role.position >= guild.me.top_role.position:
            return False
        return True

    @commands.Cog.listener("on_raw_reaction_add")
    async def reaction_role_add(self, reaction: discord.RawReactionActionEvent):
        emoji = str(reaction.emoji)
        if roles := await self.bot.db.fetch(
            """SELECT role_id FROM reactionrole WHERE guild_id = $1 AND message_id = $2 AND emoji = $3""",
            reaction.guild_id,
            reaction.message_id,
            emoji,
        ):
            guild = self.bot.get_guild(reaction.guild_id)
            if guild.me.guild_permissions.administrator is False:
                return
        else:
            return

        @ratelimit("rr:{reaction.guild_id}", 3, 5, True)
        async def do(
            reaction: discord.RawReactionActionEvent, roles: Any, guild: Guild
        ):
            for r in roles:
                if role := guild.get_role(r.role_id):
                    if await self.check_rolee(guild, role) is not True:
                        return logger.info("failed rr checks")
                    if member := guild.get_member(reaction.user_id):
                        if await self.bot.glory_cache.ratelimited("rr", 1, 4) != 0:
                            await asyncio.sleep(5)
                        if role in member.roles:
                            return
                        try:
                            await member.add_roles(role)
                        except Exception:
                            await member.add_roles(role)

        return await do(reaction, roles, guild)

    @commands.Cog.listener("on_raw_reaction_remove")
    async def reaction_role_remove(self, reaction: discord.RawReactionActionEvent):
        emoji = str(reaction.emoji)
        if roles := await self.bot.db.fetch(
            """SELECT role_id FROM reactionrole WHERE guild_id = $1 AND message_id = $2 AND emoji = $3""",
            reaction.guild_id,
            reaction.message_id,
            emoji,
        ):
            guild = self.bot.get_guild(reaction.guild_id)
            if guild.me.guild_permissions.administrator is False:
                return logger.info("failed rr perm checks")
        else:
            return

        @ratelimit("rr:{reaction.guild_id}", 3, 5, True)
        async def do(
            reaction: discord.RawReactionActionEvent, roles: Any, guild: Guild
        ):
            if member := guild.get_member(reaction.user_id):
                if len(member.roles) > 0:
                    member_roles = [r.id for r in member.roles]
                    for role in roles:
                        if r := guild.get_role(role.role_id):
                            if await self.check_rolee(guild, r) is not True:
                                return logger.info("failed rr checks")
                        else:
                            return logger.info("no role lol")
                        if role.role_id in member_roles:
                            if await self.bot.glory_cache.ratelimited("rr", 1, 4) != 0:
                                await asyncio.sleep(5)
                            try:
                                await member.remove_roles(guild.get_role(role.role_id))
                            except Exception:
                                await member.remove_roles(
                                    guild.get_role(role.role_id), reason="RR"
                                )

        return await do(reaction, roles, guild)

    @commands.Cog.listener("on_member_update")
    @ratelimit("fn:{before.guild.id}", 3, 5, True)
    async def forcenick_event(self, before: discord.Member, after: discord.Member):
        if before.nick == after.nick:
            return

        if not (data := self.bot.cache.forcenick.get(before.guild.id)):
            return

        if not data.get(before.id):
            return
        if after.guild.me.top_role < after.top_role:
            return

        if await self.forcenick_check(after.guild, after) is True:
            if has_data := self.bot.cache.forcenick.get(before.guild.id):
                if name := has_data.get(before.id):
                    try:
                        if after.nick != name:
                            await after.edit(nick=name[:32])
                    except discord.Forbidden:
                        self.bot.cache.forcenick[before.guild.id].pop(before.id, None)
        else:
            if before.nick and before.nick != after.nick and before.nick is not None:
                return await self.bot.db.execute(
                    """INSERT INTO names (user_id,type,username,ts) VALUES($1,$2,$3,$4) ON CONFLICT(user_id,username,ts) DO NOTHING""",
                    before.id,
                    "nickname",
                    before.nick,
                    datetime.now(),
                )

    async def get_event_types(self, message: discord.Message):
        p = []
        _types = ["spoilers", "images", "emojis", "stickers"]
        for t in _types:
            if yes := self.bot.cache.autoreacts[message.guild.id].get(t):  # type: ignore  # noqa: F841
                p.append(t)
        return p

    async def do_autoresponse(self, trigger: str, message: discord.Message):
        if await self.bot.glory_cache.ratelimited(f"ar:{message.guild.id}:{trigger}", 1, 1) == 0:
            if (
                await self.bot.glory_cache.ratelimited(
                    f"ar:{message.guild.id}:{trigger}", 2, 4
                )
                != 0
            ):
                return
            response = self.bot.cache.autoresponders[message.guild.id][trigger]
            if response.lower().startswith(
                "{embed}"
            ):  # if any(var in response.lower() for var in variables):
                # Do something if any of the variables are found in the message content
                return await self.bot.send_embed(
                    message.channel, response, user=message.author, guild=message.guild
                )
            else:
                return await message.channel.send(response)

    async def check_message(self, message: discord.Message):
        if await self.bot.glory_cache.ratelimited(f"check_msg:{message.guild.id}", 1, 1) == 0:
            if data := self.bot.cache.autoresponders.get(message.guild.id):
                for trigger, response in data.items():  # type: ignore
                    if trigger.endswith("*"):
                        if trigger.strip("*").lower() in message.content.lower():
                            await self.do_autoresponse(trigger, message)
                    else:
                        trigger = trigger.strip()
                        content = message.content
                        if (
                            content.lower().startswith(f"{trigger.lower()} ")
                            or content.lower() == trigger.lower()
                        ):
                            return await self.do_autoresponse(trigger, message)
                        if (
                            f"{trigger.lower()} " in content.lower()
                            or f" {trigger.lower()}" in content.lower()
                        ):
                            return await self.do_autoresponse(trigger, message)
                        if (
                            trigger.lower() in content.lower().split()
                            or f"{trigger.lower()} " in content.lower()
                            or content.lower().startswith(f"{trigger.lower()} ")
                            or content.lower().endswith(f" {trigger.lower()}")
                        ):
                            await self.do_autoresponse(trigger, message)

    @commands.Cog.listener("on_message")
    async def autoresponder_event(self, message: discord.Message):
        if message.guild is None:
            return
        if message.author.bot:
            return
        try:
            if message.channel.permissions_for(message.guild.me).send_messages is False:
                return
        except discord.errors.ClientException:
            pass
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        await self.check_message(message)

    async def do_afk(
        self, message: discord.Message, context: commands.Context, afk_data: Any
    ):
        if await self.bot.glory_cache.ratelimited(f"afk:{message.author.id}", 1, 1) == 0:
            author_afk_since: datetime = afk_data["date"]
            welcome_message = (f":wave_tone3: {message.author.mention}: **Welcome back**, "
                            f"you went away {discord.utils.format_dt(author_afk_since, style='R')}")
            embed = discord.Embed(description=welcome_message, color=0x9eafbf)
            await context.send(embed=embed)

            if message.author.id in self.bot.afks:
                self.bot.afks.pop(message.author.id)
            else:
                logger.error(f"{message.author.id} not found in AFK list.")


    async def revert_slowmode(self, channel: discord.TextChannel):
        await asyncio.sleep(300)
        await channel.edit(slowmode_delay=0, reason="Auto Mod Auto Slow Mode")
        return True

    async def reset_filter(self, guild: Guild):
        tables = [
            """DELETE FROM filter_event WHERE guild_id = $1""",
            """DELETE FROM filter_setup WHERE guild_id = $1""",
        ]
        return await asyncio.gather(
            *[self.bot.db.execute(table, guild.id) for table in tables]
        )

    #    @ratelimit("to:{message.guild.id}", 1, 5, True)
    async def do_timeout(
        self, message: discord.Message, reason: str, context: commands.Context
    ):
        if self.bot.check_bot_hierarchy(message.guild) is False:
            await self.reset_filter(message.guild)
            return False
        if await self.bot.glory_cache.ratelimited(f"timeout-attempt-{message.guild.id}", 1, 10) != 0:
            return
        if await self.bot.glory_cache.ratelimited(f"timeout-attempt-{message.author.id}-{message.guild.id}", 1, 10) != 0: 
            return
        async def check():
            if message.author.top_role >= message.guild.me.top_role:
                if self.maintenance is True:
                    if message.author.name == "aiohttp":
                        logger.info(
                            "top role issue lol, {message.author.top_role.position} - {message.guild.me.top_role.position}"
                        )
                return False
            whitelist = self.bot.cache.filter_whitelist.get(context.guild.id, LIST)
            return all(
                (
                    message.author.id
                    not in (message.guild.owner_id, message.guild.me.id),
                    not message.author.guild_permissions.administrator,
                    (
                        (
                            message.author.top_role.position
                            <= message.guild.me.top_role.position
                        )
                        if message.author.top_role
                        else True
                    ),
                )
            )

        if message.guild.me.guild_permissions.moderate_members is True:
            async with self.locks[f"am-{message.author.id}-{message.guild.id}"]:
                if timeframe := await self.bot.db.fetchval(
                    """SELECT timeframe FROM automod_timeout WHERE guild_id = $1""",
                    message.guild.id,
                ):
                    try:
                        converted = humanfriendly.parse_timespan(timeframe)
                    except Exception:
                        converted = 20
                else:
                    converted = 20
                if await check():
                    if (
                        await self.bot.glory_cache.ratelimited(
                            f"amti-{message.author.id}", 1, converted
                        )
                        is not True
                    ):
                        try:
                            await message.delete()
                        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                            pass
                            
                        if not message.author.is_timed_out():
                            try:
                                await message.author.timeout(
                                    datetime.now().astimezone()
                                    + timedelta(seconds=converted),
                                    reason=reason,
                                )
                                await context.normal(
                                    f"has been **timed out** for `{get_humanized_time(converted)}`. **Reason:** {reason}",
                                    delete_after=5,
                                )
                            except OverflowError:
                                await context.normal(
                                    f"Unable to timeout user - duration of {get_humanized_time(converted)} is too long",
                                    delete_after=5,
                                )

                else:
                    if self.maintenance is True:
                        if message.author.name == "aiohttp":
                            logger.info("failed checks")
            return True
        return False

    async def add_reaction(
        self, message: discord.Message, reactions: list | str | bytes
    ):
        if message.author.name == "aiohttp":
            logger.info(reactions)
            # else:
        # if isinstance(reactions, list):
        # reactions = [(b64decode(reaction.encode()).decode() if len(tuple(reaction)) > 1 else reaction) for reaction in reaction]
        if isinstance(reactions, list):
            pass
        else:
            reactions = [reactions]
            # reactions = [(b64decode(reaction.encode()).decode() if len(tuple(reaction)) > 1 else reaction) for reaction in reactions]
        for reaction in reactions:
            try:
                await message.add_reaction(reaction)
            except Exception:
                pass
        return

    # def uwu_catgirl_mode(self, text: str):
    #     # Define emotive faces and replacements
    #     emotive_faces = ["(・`ω´・)", ";;w;;", "owo", "UwU", ">w<", "^w^"]
    #     replacements = {
    #         "r": "w",
    #         "l": "w",
    #         "R": "W",
    #         "L": "W",
    #         "o": "owo",
    #         "O": "OwO",
    #         "no": "nu",
    #         "has": "haz",
    #         "you": "yu",
    #         "y": "yw",
    #         "the": "da",
    #     }

    #     # Replace characters and apply random emotive faces
    #     for key, value in replacements.items():
    #         text = text.replace(key, value)

    #     text += " " + random.choice(emotive_faces)
    #     return text

    @commands.Cog.listener("on_message")
    async def system_messages_event(self, message: discord.Message) -> None:
        await self.bot.wait_until_ready()

        if message.author.bot or not message.guild:
            return

        try:
            if isinstance(message.channel, discord.Thread):
                if not message.channel.parent:
                    return
                permissions = message.channel.parent.permissions_for(message.guild.me)
            else:
                permissions = message.channel.permissions_for(message.guild.me)

            if not all([
                permissions.send_messages,
                permissions.moderate_members,
                permissions.manage_messages,
            ]):
                return
        except discord.ClientException:
            return

        if message.is_system and message.type == discord.MessageType.new_member:
            row = await self.bot.db.fetchrow(
                "SELECT * FROM system_messages WHERE guild_id = $1",
                message.guild.id,
            )

            if row:
                if self.system_sticker is None:
                    try:
                        self.system_sticker = await self.bot.fetch_sticker(749054660769218631)
                    except discord.NotFound:
                        return logger.error("System sticker not found.")
                        
                await message.reply(stickers=[self.system_sticker])

    def debug(self, m: discord.Message, msg: str):
        if self.maintenance is True:
            if m.author.name == "aiohttp":
                logger.info(msg)
        return

    async def get_whitelist(self, message: discord.Message):
        checks = [r.id for r in message.author.roles]
        checks.append(message.author.id)
        checks.append(message.channel.id)
        
        # Use proper ANY syntax for arrays and include all relevant IDs
        data = await self.bot.db.fetch(
            """SELECT user_id, events FROM filter_whitelist 
            WHERE guild_id = $1 
            AND user_id = ANY($2)""",
            message.guild.id,
            checks,
        )
        return data or None

    async def check_event_whitelist(self, message: discord.Message, event: str) -> bool:
        if data := await self.get_whitelist(message):
            for d in data:
                # Handle potential whitespace in stored events
                events = [e.strip().lower() for e in d['events'].split(",")]
                if event.lower() in events or "all" in events:
                    logger.debug(f"Whitelist triggered for {message.author} in {message.guild} - Event: {event}")
                    return True
        return False




    @commands.Cog.listener('on_guild_join')
    async def on_guild_join(self, guild: discord.Guild):
        notification_channel = self.bot.get_channel(1326366925877674024)
        if notification_channel is None:
            logger.info("Notification channel not found.")
            return

        # Check if the notification for this guild has already been sent
        if guild.id in self.sent_notifications and self.sent_notifications[guild.id]:
            logger.info(f"Notification for {guild.name} has already been sent.")
            return
        
        # Select the first text channel with proper permissions
        invite_channel = None
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).create_instant_invite:
                invite_channel = channel
                break

        if not invite_channel:
            logger.info(f"No suitable channel in {guild.name} to create an invite.")
            return

        # Create the invite link
        try:
            invite = await invite_channel.create_invite(unique=True)
        except discord.Forbidden:
            logger.info(f"Insufficient permissions to create invite for {guild.name}.")
            return
        except discord.HTTPException as e:
            logger.info(f"Error creating invite for {guild.name}: {e}")
            return

        # Create an embed for the server notification
        embed = discord.Embed(
            color=self.bot.color,
            description=f"wsp **{guild.name}** has more than **1000** members (**{guild.member_count}**) and has been networked with [Greed](https://discord.gg/greedbot).",
        )
        embed.set_footer(text="/greedbot")

        if guild.member_count > 1000:
            # Send a notification to the specified channel
            try:
                message = await notification_channel.send(f"Join our networks - *{guild.id}*\n{invite}")
                self.sent_notifications[guild.id] = message  # Save the sent message reference
            except discord.HTTPException as e:
                logger.info(f"Failed to send message to notification channel: {e}")

            # DM the guild owner
            owner = guild.owner
            if owner:
                try:
                    dm_channel = await owner.create_dm()
                    await dm_channel.send(embed=embed)
                except discord.Forbidden:
                    logger.info(f"Unable to send DM to the owner of {guild.name}.")
                except discord.HTTPException as e:
                    logger.info(f"Error sending DM to owner of {guild.name}: {e}")

        logger.info(f"Processed guild join for {guild.name} ({guild.id}).")

    @commands.Cog.listener('on_guild_remove')
    async def on_guild_remove(self, guild: discord.Guild):
        # When the bot is removed from a guild, record the time

        # Start a task to check if the bot has been away for 5 minutes
        await asyncio.sleep(300)  # Wait for 5 minutes
        if guild.id not in self.guild_remove_time:
            return  # Bot has been re-added, so no need to delete

        # If the bot hasn't rejoined, proceed to delete the notification message
        if self.sent_notifications.get(guild.id):
            try:
                message = self.sent_notifications[guild.id]
                await message.delete()
                logger.info(f"Deleted the notification message for {guild.name} ({guild.id}).")
            except discord.NotFound:
                logger.info(f"Message not found for deletion in {guild.name} ({guild.id}).")
            except discord.HTTPException as e:
                logger.error(f"Error deleting the message: {e}")
            finally:
                # Cleanup
                del self.sent_notifications[guild.id]
                del self.guild_remove_time[guild.id]


    @commands.Cog.listener("on_message_edit")
    async def filter_response_edit(
        self, before: discord.Message, after: discord.Message
    ):
        # Ignore edits from bots
        if before.author.bot:
            return
        # Ignore edits in DMs
        if before.guild is None:
            return
        # Check if the edited message is a valid command
        ctx = await self.bot.get_context(after)
        if ctx.valid:
            return
        # Process the edited message through the filter
        return await self.on_message_filter(after)

    @commands.Cog.listener("on_message")
    async def on_message_filter(self, message: discord.Message) -> None:
        await self.bot.wait_until_ready()
        # Ignore messages from bots or in DMs
        if message.author.bot or not message.guild:
            return
        # Check if the bot has necessary permissions
        if not message.channel.permissions_for(message.guild.me).send_messages:
            return self.debug(message, "no send_messages perms")
        if not message.guild.me.guild_permissions.moderate_members:
            return self.debug(message, "no moderate_members perms")
        if not message.guild.me.guild_permissions.manage_messages:
            return self.debug(message, "no manage_messages perms")

        context = await self.bot.get_context(message)

        # Fetch filter events and AFK data concurrently
        db_fetch = self.bot.db.fetch(
            "SELECT event FROM filter_event WHERE guild_id = $1",
            context.guild.id
        )
        afk_fetch = asyncio.create_task(
            asyncio.to_thread(lambda: self.bot.afks.get(message.author.id))
        )

        filter_events, afk_data = await asyncio.gather(
            db_fetch,
            afk_fetch,
            return_exceptions=True
        )

        # Process filter events
        filter_events = tuple(record.event for record in filter_events) if isinstance(filter_events, list) else ()

        # Handle AFK logic
        if isinstance(afk_data, dict):
            if not context.valid or context.command.qualified_name.lower() != "afk":
                await self.do_afk(message, context, afk_data)

        # Handle AFK mentions
        if message.mentions:
            mention_tasks = []
            for user in message.mentions:
                if user_afk := self.bot.afks.get(user.id):
                    if not await self.bot.glory_cache.ratelimited(
                        f"rl:afk_mention_message:{message.channel.id}", 2, 5
                    ):
                        mention_tasks.append(self.handle_afk_mention(context, message, user, user_afk))

            if mention_tasks:
                await asyncio.gather(*mention_tasks, return_exceptions=True)

        block_command_execution = False

        # Fetch automod timeout settings
        timeframe = await self.bot.db.fetchval(
            """SELECT timeframe FROM automod_timeout WHERE guild_id = $1""",
            message.guild.id,
        )
        converted = 5  # Default timeout duration
        if timeframe:
            try:
                converted = humanfriendly.parse_timespan(timeframe)
            except Exception:
                pass

        async def check():
            """Check if the user is subject to moderation."""
            return all(
                (
                    message.author.id not in (message.guild.owner_id, message.guild.me.id),
                    not message.author.guild_permissions.administrator,
                    (
                        message.author.top_role.position <= message.guild.me.top_role.position
                        if message.author.top_role
                        else True
                    ),
                )
            )

        async def apply_punishment(reason: str):
            """Apply the appropriate punishment based on guild settings."""
            try:
                await message.delete()
            except Exception:
                pass

            punishment = await self.bot.db.fetchval(
                "SELECT punishment FROM filter_setup WHERE guild_id = $1",
                message.guild.id
            )
            if punishment == "timeout":
                await self.do_timeout(message, reason, context)
            elif punishment == "kick":
                if message.guild.me.guild_permissions.kick_members:
                    await message.author.kick(reason=reason)
                else:
                    self.debug(message, "Missing kick permissions")
            elif punishment == "ban":
                if message.guild.me.guild_permissions.ban_members:
                    await message.author.ban(reason=reason)
                else:
                    self.debug(message, "Missing ban permissions")

        # Before processing any filters, check for whitelist first
        if await self.check_event_whitelist(message, "all"):
            return

        # Then in each filter section, check specific event whitelist:
        if (
            "keywords" in filter_events
            and not await self.check_event_whitelist(message, "keywords")
            and not block_command_execution
        ):
            for keyword in self.bot.cache.filter.get(context.guild.id, []):
                if keyword.lower().endswith("*"):
                    keyword_base = keyword.replace("*", "").lower()
                    if keyword_base in message.content.lower():
                        await apply_punishment("muted by the chat filter")
                        break
                else:
                    content_words = set(message.content.lower().split())
                    if keyword.lower() in content_words:
                        await apply_punishment("muted by the chat filter")
                        break

        # Spoiler filter
        if (
            "spoilers" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, self.DICT)
            .get("spoilers", self.DICT)
            .get("is_enabled", False)
            and not block_command_execution
        ):
            if not await self.check_event_whitelist(message, "spoilers"):
                if message.content.count("||") >= (
                    self.bot.cache.filter_event[context.guild.id]["spoilers"]["threshold"] * 2
                ):
                    await apply_punishment("Muted by spoiler filter")
                    block_command_execution = True

        # Headers filter
        if (
            "headers" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, self.DICT)
            .get("headers", self.DICT)
            .get("is_enabled", False)
            and not block_command_execution
        ):
            if not await self.check_event_whitelist(message, "headers"):
                for m in message.content.split("\n"):
                    if m.startswith("# "):
                        if len(m.split(" ")) >= self.bot.cache.filter_event[context.guild.id]["headers"]["threshold"]:
                            await apply_punishment("Muted by the header filter")
                            block_command_execution = True

        # Images filter
        if (
            "images" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, self.DICT)
            .get("images", self.DICT)
            .get("is_enabled", False)
            and not block_command_execution
        ):
            if not await self.check_event_whitelist(message, "images"):
                if len(message.attachments) > 0:
                    threshold = self.bot.cache.filter_event[context.guild.id]["images"]["threshold"]
                    for attachment in message.attachments:
                        if await self.bot.glory_cache.ratelimited(
                            f"ai-{message.guild.id}-{message.author.id}", threshold, 10
                        ):
                            await apply_punishment("Muted by my image filter")
                            block_command_execution = True

        # Links filter
        if (
            "links" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, self.DICT)
            .get("links", self.DICT)
            .get("is_enabled", False)
            and not block_command_execution
        ):
            if not await self.check_event_whitelist(message, "links"):
                matches = url_regex.findall(message.content)
                if len(matches) > 0:
                    for m in matches:
                        if "tenor.com" not in m:
                            reason = "muted by the link filter"
                            await apply_punishment(reason)
                            block_command_execution = True

        # Spam filter
        if (
            "spam" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, self.DICT)
            .get("spam", self.DICT)
            .get("is_enabled", False)
            and not block_command_execution
        ):
            if await self.bot.glory_cache.ratelimited(f"amtis-{message.guild.id}", 20, 10):
                if await check():
                    if not await self.check_event_whitelist(message, "spam"):
                        if await self.bot.glory_cache.ratelimited(f"amasm-{message.channel.id}", 1, 300) == 0:
                            await message.channel.edit(
                                slowmode_delay=5, reason="Auto Mod Auto Slow Mode"
                            )
                            await message.channel.send(
                                embed=discord.Embed(
                                    description=f"Set the channel to **slow mode due to excessive spam**, it will be disabled in <t:{int(datetime.now().timestamp())+500}:R>"
                                )
                            )
                            ensure_future(self.revert_slowmode(message.channel))
            if await self.bot.glory_cache.ratelimited(
                f"rl:message_spam{message.author.id}-{message.guild.id}",
                self.bot.cache.filter_event[context.guild.id]["spam"]["threshold"] - 1,
                5,
            ) != 0:
                if await self.bot.glory_cache.ratelimited(
                    f"spam:message{message.author.id}:{message.guild.id}", 1, 4
                ):
                    if await check():
                        if not await self.check_event_whitelist(message, "spam"):
                            if message.guild.me.guild_permissions.moderate_members:
                                await message.author.timeout(
                                    datetime.now().astimezone() + timedelta(seconds=converted)
                                )
                else:
                    if not await self.check_event_whitelist(message, "spam"):
                        if await check():
                            reason = "flooding chat"
                            await apply_punishment(reason)
                            block_command_execution = True
                if not await self.check_event_whitelist(message, "spam"):
                    if await check():
                        if message.guild.me.guild_permissions.manage_messages:
                            try:
                                await message.channel.purge(
                                    limit=10,
                                    check=lambda m: m.author.id == message.author.id,
                                    bulk=True,
                                    reason="Auto-moderation: Spam filter"
                                )
                            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                                pass
                            finally:
                                block_command_execution = True

        # Emojis filter
        if (
            "emojis" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, self.DICT)
            .get("emojis", self.DICT)
            .get("is_enabled", False)
            and not block_command_execution
        ):
            if len(find_emojis(message.content)) >= self.bot.cache.filter_event[context.guild.id]["emojis"]["threshold"]:
                if not await self.check_event_whitelist(message, "emojis"):
                    reason = "muted by the emoji filter"
                    await apply_punishment(reason)
                    block_command_execution = True

        # Invites filter
        if (
            "invites" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, self.DICT)
            .get("invites", self.DICT)
            .get("is_enabled", False)
            and not block_command_execution
        ):
            if not await self.check_event_whitelist(message, "invites"):
                if len(message.invites) > 0:
                    reason = "muted by the invite filter"
                    await apply_punishment(reason)
                    block_command_execution = True

        # Caps filter
        if (
            "caps" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, self.DICT)
            .get("caps", self.DICT)
            .get("is_enabled", False)
            and not block_command_execution
        ):
            if not await self.check_event_whitelist(message, "caps"):
                if len(tuple(c for c in message.content if c.isupper())) >= self.bot.cache.filter_event[context.guild.id]["caps"]["threshold"]:
                    reason = "muted by the cap filter"
                    await apply_punishment(reason)
                    block_command_execution = True

        # Mass mention filter
        if (
            "massmention" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, self.DICT)
            .get("massmention", self.DICT)
            .get("is_enabled", False)
            and not block_command_execution
        ):
            if not await self.check_event_whitelist(message, "massmention"):
                if len(message.mentions) >= self.bot.cache.filter_event[context.guild.id]["massmention"]["threshold"]:
                    reason = "muted by the mention filter"
                    await apply_punishment(reason)
                    block_command_execution = True

        if block_command_execution:
            return

        # Autoreact logic
        if self.bot.cache.autoreacts.get(message.guild.id):
            async def do_autoreact():
                try:
                    keywords_covered = []
                    for keyword, reactions in self.bot.cache.autoreacts[message.guild.id].items():
                        if keyword not in ["spoilers", "images", "emojis", "stickers"]:
                            if keyword in message.content:
                                if await self.bot.glory_cache.ratelimited(f"autoreact:{message.guild.id}:{keyword}", 1, 2):
                                    continue

                                await asyncio.gather(
                                    *[self.add_reaction(message, reaction) for reaction in reactions]
                                )
                                keywords_covered.append(keyword)
                except Exception as e:
                    self.bot.logger.error(f"Autoreact error: {e}")

            with suppress(discord.errors.HTTPException):
                asyncio.create_task(do_autoreact())

            tasks = []
            if await self.get_event_types(message):
                async def do_autoreact_event(_type: str):
                    _ = f"rl:autoreact:{message.guild.id}:{_type}"
                    if await self.bot.glory_cache.ratelimited(_, 5, 30):
                        return
                    reactions = self.bot.cache.autoreacts[message.guild.id].get(_type)
                    if reactions:
                        await self.add_reaction(message, reactions)

                events = await self.get_event_types(message)

                if "images" in events and any(
                    attachment.content_type.startswith(("image/", "video/"))
                    for attachment in message.attachments
                ):
                    await do_autoreact_event("images")

                for event_type in ["spoilers", "emojis", "stickers"]:
                    if event_type in events:
                        condition = False
                        if event_type == "spoilers" and message.content.count("||") > 2:
                            condition = True
                        elif event_type == "emojis" and find_emojis(message.content):
                            condition = True
                        elif event_type == "stickers" and message.stickers:
                            condition = True

                        if condition:
                            tasks.append(do_autoreact_event(event_type))

            try:
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                pass

        if not block_command_execution:
            return

    async def handle_afk_mention(self, ctx, message, user, user_afk):
        if await self.bot.glory_cache.ratelimited(f"afk_mention:{user.id}", 1, 5) == 0:
            embed = discord.Embed(
                description=f"{message.author.mention}: {user.mention} is AFK: **{user_afk['status']} ** - {humanize.naturaltime(datetime.now() - user_afk['date'])}",
                color=0x9eafbf,
            )
            await ctx.send(embed=embed)

    async def create_countertables(self):
        """Ensure the necessary tables exist in the database."""
        await self.bot.db.execute(
            """
            CREATE TABLE IF NOT EXISTS counter_channels (
                channel_id BIGINT PRIMARY KEY,
                current_count INTEGER NOT NULL
            )
            """
        )

    @commands.Cog.listener("on_member_join")
    async def on_member_join(self, member: discord.Member):
        if not member.guild.me.guild_permissions.manage_roles:
            return

        await asyncio.gather(
            self.autorole_give(member),
            self.jail_check(member),
            self.pingonjoin_listener(member),
            return_exceptions=True
        )

    async def check_roles(self, member: discord.Member) -> bool:
        if len(member.roles) > 0:
            roles = [
                r
                for r in member.roles
                if r
                not in (member.guild.premium_subscriber_role, member.guild.default_role)
            ]
            if len(roles) > 0:
                return True
        return False

    def check_role(self, role: discord.Role) -> bool:
        if prem_role := role.guild.premium_subscriber_role:
            if role.id != prem_role.id:
                pass
            else:
                return False
        if default := role.guild.default_role:
            if role.id != default.id:
                pass
            else:
                return False
        return True







    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        if len(member.roles) > 0 and await self.check_roles(member) is not False:
            await self.bot.redis.set(
                f"r-{member.guild.id}-{member.id}",
                orjson.dumps(
                    [r.id for r in member.roles if self.check_role(r) is not False]
                ),
                ex=9000,
            )

    @commands.Cog.listener("on_member_update")
    async def booster_role_event(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return
            
        if not after.guild.me.guild_permissions.manage_roles:
            return

        # Handle boosting role add
        if before.premium_since is None and after.premium_since is not None:
            if data := await self.bot.db.fetchrow(
                "SELECT * FROM guild.boost WHERE guild_id = $1", before.guild.id
            ):
                channel = before.guild.get_channel(data.channel_id)
                if isinstance(channel, discord.TextChannel):
                    if channel.permissions_for(after.guild.me).send_messages:
                        await self.bot.send_embed(channel, data.message, user=after)
                        
            if data := await self.bot.db.fetch(
                """SELECT role_id FROM premiumrole WHERE guild_id = $1""",
                after.guild.id,
            ):
                for role_id in data:
                    if role := after.guild.get_role(role_id):
                        if role not in after.roles and role.position < after.guild.me.top_role.position:
                            with suppress(discord.Forbidden):
                                await after.add_roles(role, reason="Booster Role")

        # Handle boosting role remove                
        elif before.premium_since is not None and after.premium_since is None:
            if data := await self.bot.db.fetch(
                """SELECT role_id FROM premiumrole WHERE guild_id = $1""",
                after.guild.id,
            ):
                for role_id in data:
                    if role := after.guild.get_role(role_id):
                        if role in after.roles and role.position < after.guild.me.top_role.position:
                            with suppress(discord.Forbidden):
                                await after.remove_roles(role, reason="Booster Role")


    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages in enabled counter channels."""
        if message.author.bot:
            return

        row = await self.bot.db.fetchrow(
            "SELECT current_count FROM counter_channels WHERE channel_id = $1", message.channel.id
        )

        if not row:
            return

        current_count = row["current_count"]
        try:
            # Ensure the message content matches the expected count
            if int(message.content) == current_count + 1:
                new_count = current_count + 1

                # Update the database
                await self.bot.db.execute(
                    "UPDATE counter_channels SET current_count = $1 WHERE channel_id = $2", 
                    new_count, message.channel.id
                )

                # React to the message with a green check mark
                await message.add_reaction("✅")

                # Send a milestone message for every hundredth count
                if new_count % 100 == 0:
                    embed = discord.Embed(
                        title="🎉 Milestone Reached!",
                        description=f"You've reached {new_count}! Say {new_count + 1} to continue.",
                        color=discord.Color.green(),
                    )
                    await message.channel.send(embed=embed)

                # Reset and purge messages when count reaches 1000
                if new_count == 1000:
                    await message.channel.send("Counter reset to 1. Deleting previous messages...")
                    await message.channel.purge()
                    await self.bot.db.execute(
                        "UPDATE counter_channels SET current_count = 1 WHERE channel_id = $1", 
                        message.channel.id
                    )
                    first_message = await message.channel.send("1")
                    await first_message.add_reaction("✅")
            else:
                # Delete messages with incorrect or out-of-sequence numbers
                await message.delete()
        except ValueError:
            # Delete non-numeric messages
            await message.delete()


    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):  # type: ignore
        if after.bot:
            return

        if (
            after.top_role.position < after.guild.me.top_role.position
            and after.id != after.guild.owner_id
        ):
            if after.guild.id in self.bot.cache.filter:
                if (
                    "nicknames" in self.bot.cache.filter_event.get(after.guild.id, DICT)
                    and self.bot.cache.filter_event[after.guild.id].get(
                        "links", {"is_enabled": False}
                    )["is_enabled"]
                    is True
                ):
                    if after.nick in self.bot.cache.filter[after.guild.id]:
                        await after.edit(
                            nick=None,
                            reason=f"{self.bot.user.name.title()} Moderation: Nickname contains a filtered word",
                        )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.id in (self.bot.user.id, 123):
            return
            
        if not message.guild:
            return
            
        if not message.channel.permissions_for(message.guild.me).view_channel:
            return
            
        await self.bot.snipes.add_entry("snipe", message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content == after.content or before.author.id == self.bot.user.id:
            return
            
        if not before.guild:
            return
            
        if not before.channel.permissions_for(before.guild.me).view_channel:
            return
            
        await self.bot.snipes.add_entry("editsnipe", before)

    @commands.Cog.listener()
    async def on_reaction_remove(
        self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]
    ):
        if not reaction.message.guild:
            return
            
        if not reaction.message.channel.permissions_for(reaction.message.guild.me).view_channel:
            return
            
        await self.bot.snipes.add_entry("rs", (reaction, user))

    @commands.Cog.listener("on_member_join")
    async def autorole_give(self, member: discord.Member):
        if await self.bot.glory_cache.ratelimited(f"autorole:{member.guild.id}", 5, 10) == 0:
            if not member.guild.me.guild_permissions.manage_roles:
                return
                
            if data := self.bot.cache.autorole.get(member.guild.id):
                roles = []
                for role_id in data:
                    if role := member.guild.get_role(role_id):
                        if role.position < member.guild.me.top_role.position:
                            roles.append(role)
                
                if roles and await self.bot.glory_cache.ratelimited("ar", 4, 6) is not True:
                    await asyncio.sleep(4)
                    with suppress(discord.Forbidden, discord.HTTPException):
                        await member.add_roles(*roles, reason="Auto Role")

    @tasks.loop(minutes=5)
    async def voicemaster_clear(self):
        """Clean up empty voice master channels periodically."""
        try:
            if await self.bot.glory_cache.ratelimited("voicemaster_clear", 1, 10):
                return

            rows = await self.bot.db.fetch(
                """SELECT guild_id, channel_id FROM voicemaster_data"""
            )

            # Process channels in smaller batches
            for batch in [rows[i:i + 10] for i in range(0, len(rows), 10)]:
                delete_tasks = []
                
                for row in batch:
                    if guild := self.bot.get_guild(row['guild_id']):
                        if channel := guild.get_channel(row['channel_id']):
                            active_members = [m for m in channel.members if not m.bot]
                            if not active_members:
                                delete_tasks.append(self._delete_channel(channel, row['channel_id']))
                
                if delete_tasks:
                    await asyncio.gather(*delete_tasks, return_exceptions=True)
                
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error in voicemaster_clear: {str(e)}")

    async def _delete_channel(self, channel: discord.VoiceChannel, channel_id: int):
        with suppress(discord.NotFound, discord.Forbidden, commands.BotMissingPermissions):
            await channel.delete(reason="Voice master cleanup - channel empty")
        
        await self.bot.db.execute(
            """DELETE FROM voicemaster_data WHERE channel_id = $1""",
            channel_id
        )
        
        logger.debug(f"Cleaned up empty voice channel {channel_id}")
        
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        return await self.voicemaster_event(member, before, after)

    @ratelimit("voicemaster_guild:{member.guild.id}", 3, 5, False)
    async def create_and_move(
        self,
        member: discord.Member,
        after: discord.VoiceState,
        status: Optional[str] = None,
    ):
        guild_rl = await self.bot.glory_cache.ratelimited(f"voicemaster_guild:{member.guild.id}", 5, 10)
        user_rl = await self.bot.glory_cache.ratelimited(f"voicemaster_move:{member.id}", 5, 10)
        
        if guild_rl > 0:
            await asyncio.sleep(guild_rl)
            return None
            
        if user_rl > 0:
            await asyncio.sleep(user_rl)
            return None
            
        try:
            overwrites = {
                member: discord.PermissionOverwrite(connect=True, view_channel=True)
            }
            channel = await member.guild.create_voice_channel(
                name=f"{member.name}'s channel",
                user_limit=0,
                category=after.channel.category,
                overwrites=overwrites,
            )
            if status:
                await channel.edit(status=status)
            await asyncio.sleep(0.3)
            try:
                await member.move_to(channel)
            except Exception:
                with suppress(discord.errors.NotFound):
                    await channel.delete()
                return None
            return channel
        except Exception:
            return None

    async def voicemaster_event(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if await self.bot.glory_cache.ratelimited(f"vm_event:{member.guild.id}", 20, 5) == 0:
            if self.bot.is_ready() and not (
                before.channel
                and after.channel
                and before.channel.id == after.channel.id
            ):
                if data := await self.bot.db.fetchrow(
                    """
                    SELECT voicechannel_id, category_id
                    FROM voicemaster
                    WHERE guild_id = $1
                    """,
                    member.guild.id,
                ):
                    join_chanel = data["voicechannel_id"]
                    data["category_id"]  # type: ignore
                    if after.channel and after.channel.id == join_chanel:
                        if await self.bot.glory_cache.ratelimited(
                            f"rl:voicemaster_channel_create:{member.guild.id}", 15, 30
                        ):
                            if (
                                before.channel
                                and before.channel != join_chanel
                                and len(before.channel.members) == 0
                                and await self.bot.db.fetchrow(
                                    "SELECT * FROM voicemaster_data WHERE channel_id = $1",
                                    before.channel.id,
                                )
                            ):
                                await self.bot.db.execute(
                                    """
                                    DELETE FROM voicemaster_data
                                    WHERE channel_id = $1
                                    """,
                                    before.channel.id,
                                )
                                with suppress(discord.errors.NotFound):
                                    await before.channel.delete()

                        else:
                            status = None
                            if stat := await self.bot.db.fetchrow(
                                """SELECT status FROM vm_status WHERE user_id = $1""",
                                member.id,
                            ):
                                status = stat["status"]
                            channel = await self.create_and_move(member, after, status)
                            if channel is not None:
                                await self.bot.db.execute(
                                    """
                                    INSERT INTO voicemaster_data
                                    (channel_id, guild_id, owner_id)
                                    VALUES ($1, $2, $3)
                                    """,
                                    channel.id,
                                    channel.guild.id,
                                    member.id,
                                )

                            if (
                                before.channel
                                and before.channel != join_chanel
                                and len(before.channel.members) == 0
                                and await self.bot.db.fetchrow(
                                    "SELECT * FROM voicemaster_data WHERE channel_id = $1",
                                    before.channel.id,
                                )
                            ):
                                await self.bot.db.execute(
                                    """
                                    DELETE FROM voicemaster_data
                                    WHERE channel_id = $1
                                    """,
                                    before.channel.id,
                                )
                                with suppress(discord.errors.NotFound):
                                    await before.channel.delete()

                    elif before and before.channel:
                        voice = await self.bot.db.fetchval(
                            """
                            SELECT channel_id
                            FROM voicemaster_data
                            WHERE channel_id = $1
                            """,
                            before.channel.id,
                        )
                        if len(before.channel.members) == 0 and voice:
                            if before.channel.id == voice:
                                await self.bot.db.execute(
                                    """
                                    DELETE FROM voicemaster_data
                                    WHERE channel_id = $1
                                    """,
                                    before.channel.id,
                                )
                                with suppress(discord.errors.NotFound):
                                    await before.channel.delete()
                            elif before.channel.id == data:
                                await asyncio.sleep(5)
                                voice = await self.bot.db.fetchval(
                                    """
                                    SELECT channel_id
                                    FROM voicemaster_data
                                    WHERE owner_id = $1
                                    """,
                                    member.id,
                                )
                                if before.channel.id == voice:
                                    await self.bot.db.execute(
                                        """
                                        DELETE FROM voicemaster_data
                                        WHERE owner_id = $1
                                        """,
                                        member.id,
                                    )
                                    with suppress(discord.errors.NotFound):
                                        await before.channel.delete()

    @commands.Cog.listener("on_member_join")
    @ratelimit("pingonjoin:{guild.id}", 2, 3, False)
    async def pingonjoin_listener(self, member: discord.Member):
        """Groups multiple joins together and pings them in a single message."""
        if not member.guild.me.guild_permissions.send_messages:
            return

        if await self.bot.glory_cache.ratelimited(f"poj:{member.guild.id}", 1, 1) != 0:
            return

        try:
            async with self.locks[f"pingonjoin:{member.guild.id}"]:
                cache_key = f"pingonjoin:{member.guild.id}"
                config = await cache.get(cache_key)
                if not config:
                    config = await self.bot.db.fetchrow(
                        "SELECT channel_id, threshold, message FROM pingonjoin WHERE guild_id = $1",
                        member.guild.id
                    )
                    if config:
                        config = dict(config)
                        await cache.set(cache_key, config)

                if not config:
                    return
                    
                channel = member.guild.get_channel(config["channel_id"])
                if not channel:
                    return logger.error(f"Channel {config['channel_id']} not found in guild {member.guild.id}")
                    
                    
                delay = min(max(config.get("threshold", 3) + 1, 2), 10)
                message_template = config.get("message") or "{user.mention}"
                members = [member]
                
                deadline = asyncio.get_event_loop().time() + delay
                remaining_time = delay

                while len(members) < 5 and remaining_time > 0:
                    try:
                        new_member = await asyncio.wait_for(
                            self.bot.wait_for(
                                "member_join",
                                check=lambda m: m.guild.id == member.guild.id
                            ),
                            timeout=remaining_time
                        )
                        members.append(new_member)
                        remaining_time = deadline - asyncio.get_event_loop().time()
                    except asyncio.TimeoutError:
                        break
                    except asyncio.TimeoutError:
                        break
                    await asyncio.sleep(0)  # Yield control periodically

                # Process mentions in chunks to avoid blocking
                mentions = []
                for i in range(0, len(members), 5):
                    chunk = members[i:i+5]
                    mentions.extend(m.mention for m in chunk)
                    await asyncio.sleep(0)
                    
                final_message = message_template.replace("{user.mention}", ", ".join(mentions))
                
                with suppress(discord.Forbidden, discord.HTTPException):
                    msg = await channel.send(final_message, allowed_mentions=discord.AllowedMentions(users = True))
                    await msg.delete(delay=delay + 1)

        except Exception as e:
            logger.error(f"Error in pingonjoin_listener for {member.guild.id}: {e}")





    @commands.Cog.listener("on_member_join")
    async def jail_check(self, member: discord.Member):
        if await self.bot.glory_cache.ratelimited(f"jail_check:{member.guild.id}", 1, 1) == 0:
            """Check and apply jail role if member was previously jailed"""
            try:
                # Check if member was previously jailed
                jailed = await self.bot.db.fetchrow(
                    "SELECT * FROM jailed WHERE guild_id = $1 AND user_id = $2",
                    member.guild.id, 
                    member.id
                )

                if not jailed:
                    return

                jail_role = discord.utils.get(member.guild.roles, name="jailed")
                if not jail_role:
                    return
                    
                removable_roles = [
                    role for role in member.roles 
                    if role != member.guild.default_role
                    and role.position < member.guild.me.top_role.position
                ]
                
                if removable_roles:
                    with suppress(discord.Forbidden, discord.HTTPException):
                        await member.remove_roles(*removable_roles, reason="Member was previously jailed")
                    
                with suppress(discord.Forbidden, discord.HTTPException):
                    await member.add_roles(jail_role, reason="Member was previously jailed")
                    
            except Exception as e:
                logger.error(f"Error in jail_check for {member}: {str(e)}")


async def setup(bot):
    await bot.add_cog(Events(bot))
