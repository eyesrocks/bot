from __future__ import annotations
from asyncio import ensure_future, gather, sleep
import json
from base64 import b64decode
from datetime import datetime, timedelta
from typing import Any, List, Union, Optional
from discord.ext import tasks
from discord import Guild, Message, Embed, Member
import random
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
from rival_tools import ratelimit, timeit  # type: ignore
from tool import expressions
from collections import defaultdict
import aiohttp
import io
from contextlib import suppress
import re  # type: ignore
from loguru import logger
from cashews import cache

cache.setup("mem://")



def get_humanized_time(seconds: Union[float, int]):
    return humanize.naturaldelta(int(seconds))

url_regex = re.compile(
    r"\b((https?|http?|ftp):\/\/)?(www\.)?([a-zA-Z0-9-]+(\.[a-zA-Z]{2,})+)(\/[^\s]*)?\b",
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
        self.maintenance = True
        self.voicemaster_clear.start()
        self.system_sticker = None
        self.last_posted = None
        #self.bot.levels.add_listener(self.on_level_up, "on_text_level_up")
        self.bot.audit_cache = {}

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

    def random_pfp(self, message: discord.Message):
        return random.choice(message.attachments)

    def random_avatar(self):
        choice = random.choice(self.bot.users)
        return choice.display_avatar.url
    
    @commands.Cog.listener("on_audit_log_entry_create")
    async def moderation_logs(self, entry: discord.AuditLogEntry):
        return await self.bot.modlogs.do_log(entry)

#    @commands.Cog.listener("on_text_level_up")
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

            message = message.replace("{level}", str(level))
            return await self.bot.send_embed(channel, message, user = member)

        await do_roles()
        await do_message()

#    @commands.Cog.listener("on_command_completion")
    async def command_moderation_logs(self, ctx: commands.Context):
        try:
            return await self.bot.modlogs.do_log(ctx)
        except Exception as e:
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


    @tasks.loop(minutes=4)
    async def do_pfp_loop(self):
        pfps = await self.get_pfps()
        embeds = [Embed(title="new pfp", url=p).set_image(url=p) for p in pfps]
        logger.info("sending avatars now")
        for guild_id, channel_id in await self.bot.db.fetch(
            """SELECT guild_id,channel_id FROM pfps"""
        ):
            if guild := self.bot.get_guild(int(guild_id)):
                if channel := guild.get_channel(int(channel_id)):
                    try:
                        await channel.send(embeds=embeds)
                    except Exception as e:
                        logger.info(f"autopfp loop raised an exception: {e}")
                        pass

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

    async def namehistory_event(self, before, after):
        if before.name != after.name:
            name = before.name
            nt = "username"
        elif before.global_name != after.global_name:
            name = before.global_name
            nt = "globalname"
        elif before.display_name != after.display_name:
            name = before.display_name
            nt = "display"
        else:
            return
        if name is None:
            return
        await self.bot.db.execute(
            """INSERT INTO names (user_id, type, username, ts) VALUES($1,$2,$3,$4) ON CONFLICT(user_id,username,ts) DO NOTHING""",
            before.id,
            nt,
            name,
            datetime.now(),
        )

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
    async def forcenick_event(self, before: discord.Member, after: discord.Member):
        if not (data := self.bot.cache.forcenick.get(before.guild.id)):
            return

        if not data.get(before.id):
            return
        if after.guild.me.guild_permissions.administrator is not True:
            return
        if after.guild.me.top_role < after.top_role:
            return
        #        if rl_check := await self.bot.glory_cache.ratelimited(
        #            f"forcenick{after.guild.id}", 4, 20
        #        ):
        #            await asyncio.sleep(rl_check)

        if await self.forcenick_check(after.guild, after) is True:
            if has_data := self.bot.cache.forcenick.get(before.guild.id):
                if name := has_data.get(before.id):
                    if after.nick != name:
                        await after.edit(nick=name[:32])
        else:
            if before.display_name != after.display_name:
                return await self.bot.db.execute(
                    """INSERT INTO names (user_id,type,username,ts) VALUES($1,$2,$3,$4) ON CONFLICT(user_id,username,ts) DO NOTHING""",
                    before.id,
                    "nickname",
                    before.display_name,
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
        if (
            await self.bot.glory_cache.ratelimited(
                f"ar:{message.guild.id}:{trigger}", 3, 5
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
        if data := self.bot.cache.autoresponders.get(message.guild.id):
            for trigger, response in data.items():  # type: ignore
                if trigger.endswith("*"):
                    if trigger.strip("*").lower() in message.content.lower():
                        await self.do_autoresponse(trigger, message)
                else:
                    trigger.rstrip().lstrip()
                    content = message.content  # )
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
        if message.author.id == 1119288050967650304:
            await message.reply(content = "faceless minor luvr sam")
        if message.guild is None:
            return
        if message.author.bot:
            return
        if message.channel.permissions_for(message.guild.me).send_messages is False:
            return
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        await self.check_message(message)

    async def do_afk(
        self, message: discord.Message, context: commands.Context, afk_data: Any
    ):
        author_afk_since: datetime = afk_data["date"]
        welcome_message = (f":wave_tone3: {message.author.mention}: **Welcome back**, "
                           f"you went away {discord.utils.format_dt(author_afk_since, style='R')}")
        embed = discord.Embed(description=welcome_message, color=0xffffff)
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
                    not any(
                        (
                            message.author.id in whitelist,
                            message.channel.id in whitelist,
                            any(role.id in whitelist for role in message.author.roles),
                        )
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
                        #                     gather(
                        #                          *(
                        await message.delete()
                        if not message.author.is_timed_out():  #
                            await message.author.timeout(
                                datetime.now().astimezone()
                                + timedelta(seconds=converted),
                                reason=reason,
                            )
                        await context.normal(
                            f"has been **timed out** for `{get_humanized_time(converted)}`. **Reason:** {reason}",
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

    def uwu_catgirl_mode(self, text: str):
        # Define emotive faces and replacements
        emotive_faces = ["(・`ω´・)", ";;w;;", "owo", "UwU", ">w<", "^w^"]
        replacements = {
            "r": "w",
            "l": "w",
            "R": "W",
            "L": "W",
            "o": "owo",
            "O": "OwO",
            "no": "nu",
            "has": "haz",
            "you": "yu",
            "y": "yw",
            "the": "da",
        }

        # Replace characters and apply random emotive faces
        for key, value in replacements.items():
            text = text.replace(key, value)

        text += " " + random.choice(emotive_faces)
        return text

    def nigger_talk(self, text: str) -> str:
        text = text.lower()
        replacements = {
            "about": "'bout",
            "are": "is",
            "because": "cuz",
            "before": "b4",
            "brother": "bruh",
            "can't": "cain't",
            "come": "com'",
            "could": "coulda",
            "don't": "don'",
            "for": "fo",
            "going to": "gonna",
            "got to": "gotta",
            "have": "got",
            "hello": "yo",
            "hey": "aye",
            "I am": "I'm",
            "my": "mah",
            "not": "ain't",
            "of": "o'",
            "okay": "aight",
            "please": "plz",
            "probably": "prolly",
            "sister": "sis",
            "something": "som'n",
            "sorry": "sry",
            "thanks": "thx",
            "that": "dat",
            "the": "da",
            "there": "der",
            "they": "dey",
            "they're": "dey",
            "though": "tho",
            "to": "2",
            "what's up": "whassup",
            "with": "wit",
            "you": "ya",
            "afternoon": "aftanoon",
            "again": "'gain",
            "alright": "aight",
            "always": "always",
            "amazing": "amaz'n",
            "anything": "anythin'",
            "awesome": "dope",
            "beautiful": "fine",
            "best": "best",
            "birthday": "bday",
            "buy": "cop",
            "by": "by",
            "care": "cae",
            "cool": "chill",
            "crazy": "wild",
            "dinner": "dinnah",
            "do not": "don'",
            "eat": "eat",
            "everybody": "evbody",
            "everything": "evrythin'",
            "feel": "feel",
            "find": "find",
            "forgot": "fuhgot",
            "forget": "fuhget",
            "goodbye": "peace",
            "happy": "lit",
            "have to": "hafta",
            "home": "crib",
            "house": "crib",
            "important": "impor'nt",
            "isn't": "ain't",
            "just": "jus'",
            "laugh": "crack up",
            "like": "like",
            "little": "lil'",
            "love": "luv",
            "make": "mak",
            "maybe": "maybe",
            "morning": "mornin'",
            "nothing": "nothin'",
            "now": "now",
            "people": "peeps",
            "perfect": "perfec'",
            "person": "pers'n",
            "pretty": "fine",
            "real": "real",
            "right": "right",
            "thank you": "good lookin' out",
            "thing": "thing",
            "this": "dis",
            "tired": "beat",
            "today": "2day",
            "tonight": "2nite",
            "understand": "get",
            "want to": "wanna",
            "what": "wha'",
            "where": "wher'",
            "why": "why",
            "wonderful": "wond'ful",
            "world": "wor'ld",
            "yeah": "ya",
            "yes": "yes",
            "yesterday": "ys'day",
            "afraid": "scared",
            "after": "afta",
            "all right": "aight",
            "anybody": "anybody",
            "anyone": "anyone",
            "ask": "ax",
            "believe": "believ'",
            "between": "btw",
            "boss": "boss",
            "busy": "bizzy",
            "car": "ride",
            "catch": "catch",
            "celebrate": "celebra'",
            "child": "kid",
            "class": "clas",
            "clean": "cleen",
            "close": "clo'",
            "difficult": "diff'",
            "dude": "dood",
            "each": "each",
            "easy": "ez",
            "enough": "'nuff",
            "especially": "'specially",
            "every": "ev'ry",
            "family": "fam",
            "famous": "famouz",
            "friend": "homie",
            "girlfriend": "bae",
            "grandfather": "grampa",
            "grandmother": "gramma",
            "great": "dope",
            "hate": "hate",
            "homework": "hwk",
            "hungry": "hungry",
            "husband": "husban'",
            "invited": "invited",
            "jacket": "jacket",
            "jealous": "jelly",
            "kitchen": "kitchen",
            "lunch": "lunch",
            "married": "married",
            "meeting": "meet'n",
            "money": "guap",
            "movie": "movie",
            "neighborhood": "hood",
            "nice": "tight",
            "parents": "parentz",
            "party": "kickback",
            "pay": "pay",
            "problem": "prob",
            "remember": "rememb'",
            "restaurant": "res'raun'",
            "running": "runnin'",
            "shopping": "shoppin'",
            "spending": "spendin'",
            "started": "started",
            "starting": "startin'",
            "staying": "stay'n",
            "summer": "summa",
            "talking": "talkin'",
            "teacher": "teach'a",
            "television": "TV",
            "thinking": "thinkin'",
            "vacation": "vacay",
            "wanted": "wanted",
            "watching": "watchin'",
            "weekend": "weeken'",
            "wife": "wifey",
            "working": "workin'",
            "worry": "worry",
            "two": "2",
            "too": "2",
            "accident": "acciden'",
            "actually": "act'ly",
            "appointment": "appointmen'",
            "argument": "argumen'",
            "careful": "careful",
            "choose": "choose",
            "comfortable": "comf'table",
            "continue": "continue",
            "decide": "decide",
            "definitely": "def'ly",
            "disgusting": "disgustin'",
            "doctor": "docta",
            "dollar": "dolla",
            "explain": "explain",
            "finally": "fin'ly",
            "bathroom": "john",
            "beer": "brew",
            "beverage": "drank",
            "big": "huge",
            "cash": "paper",
            "clothes": "threads",
            "dance": "groove",
            "excellent": "bomb",
            "food": "grub",
            "gun": "strap",
            "interesting": "tight",
            "know": "peep",
            "mad": "heated",
            "music": "jam",
            "police": "5-0",
            "prison": "the clink",
            "rich": "loaded",
            "shoes": "kicks",
            "sleep": "crash",
            "sneakers": "kicks",
            "steal": "jack",
            "stupid": "dumb",
            "sure": "fo sho",
            "talk": "rap",
            "true": "word",
            "walk": "stroll",
            "water": "H2O",
            "weak": "wack",
            "yes": "yurr",
            "give": "gimme",
            "cause": "cuh",
            "talking": "spittin",
            "family": "fam",
            "crazy": "insanelilbro",
            "she": "lil'shawty",
            "him": "lil dudz",
            "her": "tiny sha",
        }
        for key, value in replacements.items():
            text = text.replace(key, value)
        return text

    @commands.Cog.listener("on_message")
    async def system_messages_event(self, message: discord.Message) -> None:
        await self.bot.wait_until_ready()
        if message.author.bot or not message.guild:
            return
        if message.channel.permissions_for(message.guild.me).send_messages is False:
            return
        if message.channel.permissions_for(message.guild.me).moderate_members is False:
            return
        if message.channel.permissions_for(message.guild.me).manage_messages is False:
            return
        if message.is_system:
            if message.type == discord.MessageType.new_member:
                if await self.bot.db.fetchrow(
                    """SELECT * FROM system_messages WHERE guild_id = $1""",
                    message.guild.id,
                ):
                    if self.system_sticker is None:
                        self.system_sticker = await self.bot.fetch_sticker(
                            749054660769218631
                        )
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
        data = await self.bot.db.fetch(
            """SELECT user_id, events FROM filter_whitelist WHERE guild_id = $1 and user_id =  any($2::bigint[])""",
            message.guild.id,
            checks,
        )
        if not data:
            return None
        return data

    async def check_event_whitelist(self, message: discord.Message, event: str) -> bool:
        if data := await self.get_whitelist(message):
            for d in data:
                events = d.events.split(",")
                if (event.lower() in events) or ("all" in events):
                    if message.author.name == "aiohttp":
                        logger.info(
                            f"{message.author.name} was whitelisted for the event {event} due to row {d}"
                        )
                    return True
        return False

    @commands.Cog.listener("on_message")
    async def time_response(self, message: discord.Message) -> None:
        if message.author.bot or message.author is self.bot.user.bot:
            return
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        async with timeit() as timer:
            await self.on_message_filter(message)
        self.response_time = timer.elapsed

    # @commands.Cog.listener("on_message")
    async def uwulock_event(self, message: discord.Message) -> None:
        if message.content and message.content != "":
            if data := await self.bot.db.fetchval(
                """SELECT webhook FROM niggertalk WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3""",
                message.guild.id,
                message.channel.id,
                message.author.id,
            ):
                try:
                    async with aiohttp.ClientSession() as session:
                        webhook = discord.Webhook.from_url(f"{data}", session=session)
                        await message.delete()
                        return await webhook.send(self.nigger_talk(message.content))
                except discord.errors.NotFound:
                    await self.bot.db.execute(
                        """DELETE FROM niggertalk WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3""",
                        message.guild.id,
                        message.channel.id,
                        message.author.id,
                    )
                    logger.error(
                        f"Failed to send niggertalk message to {message.author.name} in {message.guild.name} due to webhook not found"
                    )
            if data := await self.bot.db.fetchval(
                """SELECT webhook FROM uwulock WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3""",
                message.guild.id,
                message.channel.id,
                message.author.id,
            ):
                try:
                    async with aiohttp.ClientSession() as session:
                        webhook = discord.Webhook.from_url(f"{data}", session=session)
                        await message.delete()
                        return await webhook.send(
                            self.uwu_catgirl_mode(message.content)
                        )
                except discord.errors.NotFound:
                    await self.bot.db.execute(
                        """DELETE FROM uwulock WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3""",
                        message.guild.id,
                        message.channel.id,
                        message.author.id,
                    )
                    logger.error(
                        f"Failed to send uwulock message to {message.author.name} in {message.guild.name} due to webhook not found"
                    )

    @commands.Cog.listener("on_message_edit")
    async def filter_response_edit(
        self, before: discord.Message, after: discord.Message
    ):  # type: ignore
        if before.author.bot or before.author is self.bot.user.bot:
            return
        ctx = await self.bot.get_context(after)
        if ctx.valid:
            return
        return await self.on_message_filter(after)

    async def on_message_filter(self, message: discord.Message) -> None:
        await self.bot.wait_until_ready()
        if message.author.bot or not message.guild:
            return
        if message.channel.permissions_for(message.guild.me).send_messages is False:
            return self.debug(message, "no send_messages perms")
        if message.guild.me.guild_permissions.moderate_members is False:
            return self.debug(message, "no moderate_members perms")
        if message.guild.me.guild_permissions.manage_messages is False:
            return self.debug(message, "no manage_members perms")
        block_command_execution = False
        context = await self.bot.get_context(message)
        filter_events = tuple(
            record.event
            for record in await self.bot.db.fetch(
                "SELECT event FROM filter_event WHERE guild_id = $1", context.guild.id
            )
        )
        if afk_data := self.bot.afks.get(message.author.id):
            if context.valid:
                if context.command.qualified_name.lower() == "afk":
                    pass
                else:
                    await self.do_afk(message, context, afk_data)
            else:
                await self.do_afk(message, context, afk_data)

        if message.mentions:
            for user in message.mentions:
                if user_afk := self.bot.afks.get(user.id):
                    if not await self.bot.glory_cache.ratelimited(
                        f"rl:afk_mention_message:{message.channel.id}", 2, 5
                    ):
                        embed = discord.Embed(
                            description=f"{message.author.mention}: {user.mention} is AFK: **{user_afk['status']} ** - {humanize.naturaltime(datetime.now() - user_afk['date'])}",
                            color=0xffffff,
                        )
                        await context.send(embed=embed)
        if timeframe := await self.bot.db.fetchval(
            """SELECT timeframe FROM automod_timeout WHERE guild_id = $1""",
            message.guild.id,
        ):
            try:
                converted = humanfriendly.parse_timespan(timeframe)
            except Exception:
                converted = 5
        else:
            converted = 5

        async def check():
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

        if (
            self.bot.cache.filter.get(context.guild.id)
            and block_command_execution is False
        ):
            if await check():
                if not await self.check_event_whitelist(message, "keywords"):

                    async def do_filter():
                        for keyword in self.bot.cache.filter.get(context.guild.id, []):
                            if keyword.lower().endswith("*"):
                                if (
                                    keyword.replace("*", "").lower()
                                    in message.content.lower()
                                ):
                                    await self.do_timeout(
                                        message, "muted by the chat filter", context
                                    )
                                break
                            else:
                                if keyword.lower() in message.content.lower().split(
                                    " "
                                ):
                                    await self.do_timeout(
                                        message, "muted by the chat filter", context
                                    )
                                    break

                            await sleep(0.001)

                    ensure_future(do_filter())

        if (
            "spoilers" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, DICT)
            .get("spoilers", DICT)
            .get("is_enabled", False)
            is True
            and block_command_execution is False
        ):
            if not await self.check_event_whitelist(message, "spoilers"):
                if message.content.count("||") >= (
                    self.bot.cache.filter_event[context.guild.id]["spoilers"][
                        "threshold"
                    ]
                    * 2
                ):
                    #    if await check():
                    reason = "Muted by spoiler filter"
                    await self.do_timeout(message, reason, context)
                    block_command_execution = True
        if (
            "headers" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, DICT)
            .get("headers", DICT)
            .get("is_enabled", False)
            is True
            and block_command_execution is False
        ):
            if not await self.check_event_whitelist(message, "headers"):
                for m in message.content.split("\n"):
                    if m.startswith("# "):
                        if (
                            len(m.split(" "))
                            >= self.bot.cache.filter_event[context.guild.id]["headers"][
                                "threshold"
                            ]
                        ):
                            await self.do_timeout(
                                message, "Muted by the header filter", context
                            )
                            block_command_execution = True
        if (
            "images" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, DICT)
            .get("images", DICT)
            .get("is_enabled", False)
            is True
            and block_command_execution is False
        ):
            if not await self.check_event_whitelist(message, "images"):
                if len(message.attachments) > 0:
                    threshold = self.bot.cache.filter_event[context.guild.id]["images"][
                        "threshold"
                    ]
                    for attachment in message.attachments:  # type: ignore
                        if await self.bot.glory_cache.ratelimited(
                            f"ai-{message.guild.id}-{message.author.id}", threshold, 10
                        ):
                            await self.do_timeout(
                                message, "Muted by my image filter", context
                            )
                            block_command_execution = True
        if (
            "links" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, DICT)
            .get("links", DICT)
            .get("is_enabled", False)
            is True
            and block_command_execution is False
        ):
            if not await self.check_event_whitelist(message, "links"):
                # if await check():
                matches = url_regex.findall(message.content)
                if len(matches) > 0:
                    for m in matches:
                        if "tenor.com" not in m:
                            reason = "muted by the link filter"
                            await self.do_timeout(message, reason, context)
                            block_command_execution = True

        if (
            "spam" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, DICT)
            .get("spam", DICT)
            .get("is_enabled", False)
            is True
            and block_command_execution is False
        ):
            # if await check():
            if await self.bot.glory_cache.ratelimited(
                f"amtis-{message.guild.id}", 20, 10
            ):
                if await check():
                    if not await self.check_event_whitelist(message, "spam"):
                        #
                        if (
                            await self.bot.glory_cache.ratelimited(
                                f"amasm-{message.channel.id}", 1, 300
                            )
                            == 0
                        ):
                            await message.channel.edit(
                                slowmode_delay=5, reason="Auto Mod Auto Slow Mode"
                            )
                            await message.channel.send(
                                embed=discord.Embed(
                                    description=f"Set the channel to **slow mode due to excessive spam**, it will be disabled in <t:{int(datetime.now().timestamp())+500}:R>"
                                )
                            )
                            ensure_future(self.revert_slowmode(message.channel))
            if (
                await self.bot.glory_cache.ratelimited(
                    f"rl:message_spam{message.author.id}-{message.guild.id}",
                    self.bot.cache.filter_event[context.guild.id]["spam"]["threshold"]
                    - 1,
                    5,
                )
                != 0
            ):
                if await self.bot.glory_cache.ratelimited(
                    f"spam:message{message.author.id}:{message.guild.id}", 1, 4
                ):
                    if await check():
                        if not await self.check_event_whitelist(message, "spam"):
                            if (
                                message.guild.me.guild_permissions.moderate_members
                                is True
                            ):
                                await message.author.timeout(
                                    datetime.now().astimezone()
                                    + timedelta(seconds=converted)
                                )
                else:
                    if not await self.check_event_whitelist(message, "spam"):
                        if await check():
                            reason = "flooding chat"
                            await self.do_timeout(message, reason, context)
                            block_command_execution = True
                if not await self.check_event_whitelist(message, "spam"):
                    if await check():
                        if message.guild.me.guild_permissions.manage_messages is True:
                            await message.channel.purge(
                                limit=10,
                                check=lambda m: m.author.id == message.author.id,
                            )
                            block_command_execution = True

        if (
            "emojis" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, DICT)
            .get("emojis", DICT)
            .get("is_enabled", False)
            is True
            and block_command_execution is False
        ):
            if len(find_emojis(message.content)) >= (
                self.bot.cache.filter_event[context.guild.id]["emojis"]["threshold"]
            ):
                if not await self.check_event_whitelist(message, "emojis"):
                    # if await check():
                    reason = "muted by the emoji filter"
                    await self.do_timeout(message, reason, context)

                    block_command_execution = True

        if (
            "invites" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, DICT)
            .get("invites", DICT)
            .get("is_enabled", False)
            is True
            and block_command_execution is False
        ):
            if not await self.check_event_whitelist(message, "invites"):
                if len(message.invites) > 0:
                    reason = "muted by the invite filter"
                    await self.do_timeout(message, reason, context)

                    block_command_execution = True

        if (
            "caps" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, DICT)
            .get("caps", DICT)
            .get("is_enabled", False)
            is True
            and block_command_execution is False
        ):
            if not await self.check_event_whitelist(message, "caps"):
                if len(tuple(c for c in message.content if c.isupper())) >= (
                    self.bot.cache.filter_event[context.guild.id]["caps"]["threshold"]
                ):
                    reason = "muted by the cap filter"
                    await self.do_timeout(message, reason, context)

                    block_command_execution = True

        if (
            "massmention" in filter_events
            and self.bot.cache.filter_event.get(context.guild.id, DICT)
            .get("massmention", DICT)
            .get("is_enabled", False)
            is True
            and block_command_execution is False
        ):
            if not await self.check_event_whitelist(message, "massmention"):
                if len(message.mentions) >= (
                    self.bot.cache.filter_event[context.guild.id]["massmention"][
                        "threshold"
                    ]
                ):
                    reason = "muted by the mention filter"
                    await self.do_timeout(message, reason, context)

                    block_command_execution = True

        if block_command_execution is True:
            return

        if self.bot.cache.autoreacts.get(message.guild.id):

            async def do_autoreact():
                try:

                    def check_emoji(react: Any):  # type: ignore
                        if not isinstance(react, str):
                            return True
                        if match := EMOJI_REGEX.match(react):
                            emoji = match.groupdict()
                            if re := message.guild.get_emoji(int(emoji["id"])):  # type: ignore  # noqa: F841
                                return True
                            else:
                                return False
                        return True

                    keywords_covered = []
                    for keyword, reaction in self.bot.cache.autoreacts[  # type: ignore
                        message.guild.id
                    ].items():
                        if keyword not in ["spoilers", "images", "emojis", "stickers"]:
                            if keyword in message.content:
                                reactions = self.bot.cache.autoreacts[message.guild.id][
                                    keyword
                                ]
                                reactions = [reaction for reaction in reactions]
                                reactions = [r for r in reactions]

                                async def do_reaction(
                                    message: discord.Message, reaction: str
                                ):
                                    try:
                                        name = unicodedata.name(reaction)
                                        if "variation" in name.lower():
                                            #                                           logger.info(f"not adding {reaction} due to the name being {name}")
                                            return
                                    #                                        logger.info(f"emoji name: {name}")
                                    except Exception:
                                        pass
                                    try:
                                        #                  if message.author.name == "aiohttp": logger.info(reaction)
                                        await message.add_reaction(reaction)
                                    except Exception as e:
                                        self.bot.eee = reaction
                                        #                                      logger.info(f"An Autoreaction error occurred : {e} : for emoji {reaction} with type {type(reaction)}")
                                        # return await message.channel.send(
                                        #     embed=discord.Embed(
                                        #         color=self.bot.color,
                                        #         description=f"i cannot react to messages due to an error, please report this: {e}",
                                        #     )
                                        # )
                                        pass  # type: ignore

                                gather(
                                    *(
                                        do_reaction(message, reaction)
                                        for reaction in reactions
                                    )
                                )

                                keywords_covered.append(keyword)
                                continue
                except Exception:
                    pass

            with suppress(discord.errors.HTTPException):
                await do_autoreact()

            tasks = []
            if await self.get_event_types(message):

                async def do_autoreact_event(_type: str):
                    #   if await self.bot.glory_cache.ratelimited(
                    #      f"rl:autoreact{message.guild.id}", 5, 30
                    #    ):
                    #    return
                    if reactions := self.bot.cache.autoreacts[message.guild.id].get(
                        _type
                    ):
                        await self.add_reaction(message, reactions)

                #                        await gather(
                #                           *(
                # #                             message.add_reaction(
                #                              get_emoji(reaction)
                # #                                if len(tuple(reaction)) < 1
                #                             else reaction
                #                        )
                #                       for reaction in reactions
                #                  )
                #                       )
                #
                events = await self.get_event_types(message)
                #                if message.author.name == "aiohttp": logger.info(f"{events}")
                if "images" in events and any(
                    tuple(
                        attachment.content_type.startswith(("image/", "video/"))
                        for attachment in message.attachments
                    )
                ):
                    #                   if message.author.name == "aiohttp": logger.info(f"doing autoreact for images")
                    await do_autoreact_event("images")
                #              else:
                #                 if message.author.name == "aiohttp": logger.info(f"not an image")
                if "spoilers" in events and (message.content.count("||") > 2):
                    tasks.append(do_autoreact_event("spoilers"))

                if "emojis" in events and find_emojis(message.content):
                    tasks.append(do_autoreact_event("emojis"))

                if "stickers" in events and message.stickers:
                    tasks.append(do_autoreact_event("stickers"))
        try:
            await gather(*tasks)
        except Exception:
            pass
        if not block_command_execution:
            return await self.uwulock_event(message)

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
        if before.premium_since is None and after.premium_since is not None:
            if data := await self.bot.db.fetchrow(
                "SELECT * FROM guild.boost WHERE guild_id = $1", before.guild.id
            ):
                channel = before.guild.get_channel(data.channel_id)
                # embed = await EmbedBuilder(message.author).build_embed(data.message)
                if channel and isinstance(channel, discord.TextChannel):
                    await self.bot.send_embed(channel, data.message, user=after)
        if before.premium_since is None and after.premium_since is not None:
            if data := await self.bot.db.fetch(
                """SELECT role_id FROM premiumrole WHERE guild_id = $1""",
                after.guild.id,
            ):
                for role_id in data:
                    if role := after.guild.get_role(role_id):
                        if role not in after.roles:
                            await after.add_roles(role, reason="Booster Role")
        elif before.premium_since is not None and after.premium_since is None:
            if data := await self.bot.db.fetch(
                """SELECT role_id FROM premiumrole WHERE guild_id = $1""",
                after.guild.id,
            ):
                for role_id in data:
                    if role := after.guild.get_role(role_id):
                        if role in after.roles:
                            await after.remove_roles(role, reason="Booster Role")

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
        if message.author.id == self.bot.user.id or message.author.id == 123:
            return
        return await self.bot.snipes.add_entry("snipe", message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content != after.content and before.author.id != self.bot.user.id:
            return await self.bot.snipes.add_entry("editsnipe", before)

    @commands.Cog.listener()
    async def on_reaction_remove(
        self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]
    ):
        return await self.bot.snipes.add_entry("rs", (reaction, user))

    @commands.Cog.listener("on_member_join")
    async def autorole_give(self, member: discord.Member):
        if data := self.bot.cache.autorole.get(member.guild.id):
            roles = [
                member.guild.get_role(i)
                for i in data
                if member.guild.get_role(i) is not None
            ]
            if await self.bot.glory_cache.ratelimited("ar", 4, 6) is not True:
                await asyncio.sleep(4)
            await member.add_roles(*roles, atomic=False)

    @tasks.loop(minutes=1)
    async def voicemaster_clear(self):
        async for row in self.bot.db.fetchiter(
            """SELECT guild_id, channel_id FROM voicemaster_data"""
        ):
            if guild := self.bot.get_guild(row.guild_id):
                if channel := guild.get_channel(row.channel_id):
                    members = [c for c in channel.members if c != self.bot.user]
                    if len(members) == 0:
                        await channel.delete(reason="voicemaster cleanup")

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        return await self.voicemaster_event(member, before, after)





    @ratelimit("voicemaster:{member.id}", 2, 5, False)
    async def create_and_move(
        self,
        member: discord.Member,
        after: discord.Voicestate,
        status: Optional[str] = None,
    ):
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
            await channel.delete()
            return None
        return channel

    async def voicemaster_event(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if not (
            not self.bot.is_ready()
            or (
                before.channel
                and after.channel
                and before.channel.id == after.channel.id
            )
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
                        f"rl: voicemaster_channel_create: {member.guild.id}", 5, 30
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
                        if stat := await self.bot.db.fetchrow(
                            """SELECT status FROM vm_status WHERE user_id = $1""",
                            member.id,
                        ):
                            status = stat["status"]
                        else:
                            status = None
                        {
                            member: discord.PermissionOverwrite(
                                connect=True, view_channel=True
                            )
                        }  # type: ignore
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


async def setup(bot):
    await bot.add_cog(Events(bot))
