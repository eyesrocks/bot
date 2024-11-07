from asyncio import (
    Lock,
    ensure_future as do_soon,
    Future,
    gather,
    iscoroutinefunction,
    Task,
    create_task,
    as_completed,
)
from collections import defaultdict as collection
import math
import random
import discord
import traceback
from tool.collage import _make_bar
import json
from discord.ext import tasks
from io import BytesIO
from discord.ext.commands import Context
from discord import (
    Message,
    Client,
    Guild,
    VoiceChannel,
    Member,
    VoiceState,
    Embed,
    File,
)
from datetime import datetime
from humanize import naturaltime
from typing import Optional, Coroutine, Callable, Any, Dict, TypeVar
from loguru import logger
from typing_extensions import Self, NoReturn
from xxhash import xxh64_hexdigest as hash_

T = TypeVar("T")
Coro = Coroutine[Any, Any, T]
CoroT = TypeVar("CoroT", bound=Callable[..., Coro[Any]])


def get_timestamp():
    return datetime.now().timestamp()


class Level:
    def __init__(self, multiplier: float = 0.5, bot: Optional[Client] = None):
        self.multiplier = multiplier
        self.bot = bot
        self._events = ["on_text_level_up", "on_voice_level_up"]
        self.listeners: Dict[str, Future] = {}
        self.logger = logger
        self.startup_finished = False
        self.locks = collection(Lock)
        self.cache = {}
        self.messages = []
        self.text_cache = {}
        self.level_cache = {}
        self.text_level_loop.start()
#        self.autoboard_channel.start()

    async def setup(self, bot: Client) -> Self:
        self.bot = bot
        self.logger.info("Starting levelling loop")
        self.bot.loop.create_task(self.do_text_levels())
        self.bot.add_listener(self.do_message_event, "on_message")
        self.logger.info("Levelling loop started")
        return self


    @tasks.loop(minutes=2)
    async def text_level_loop(self):
        try:
            await self.do_text_levels()
        except Exception as error:
            exc = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
            logger.info(f"text_level_loop raised {exc}")

    @tasks.loop(minutes=2)
    async def voice_level_loop(self):
        try:
            await self.do_voice_levels()
        except Exception as error:
            exc = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
            logger.info(f"voice_level_loop raised {exc}")

#    @tasks.loop(minutes=3)
    async def autoboard_channel(self):
        guilds = await self.bot.db.fetch(
            """SELECT guild_id, autoboard_channel FROM text_level_settings"""
        )
        for guild in guilds:
            try:
                guild_ = self.bot.get_guild(guild.guild_id)
                if not guild_:
                    continue
                if data := guild.autoboard_channel:
                    channel_id, message_id = json.loads(data)
                    channel = guild_.get_channel(channel_id)
                    if not channel:
                        continue
                    try:
                        message = await channel.fetch_message(message_id)
                    except discord.errors.NotFound:
                        await self.bot.db.execute(
                            """DELETE FROM text_level_settings WHERE guild_id = $1""",
                            guild.guild_id,
                        )
                    rows = await self.bot.db.fetch(
                        """SELECT user_id, xp, msgs FROM text_levels WHERE guild_id = $1 ORDER BY xp DESC LIMIT 5;""",
                        guild.guild_id,
                        cached=False,
                    )
                    desc = ""
                    for i, row in enumerate(rows, start=1):
                        desc += f"`{i}` <@!{row.user_id}>\n"
                    embed = Embed(
                        title="Top Users", description=desc, color=self.bot.color
                    )
                    await message.edit(embed=embed)
            except Exception:
                continue

    def get_xp(self, level: int) -> int:
        """
        :param level : Level(int)
        :return      : Amount of xp(int) needed to reach the level
        """
        return math.ceil(math.pow((level - 1) / (0.05 * (1 + math.sqrt(5))), 2))

    def get_level(self, xp: int) -> int:
        """
        :param xp : XP(int)
        :return   : Level(int)
        """
        return math.floor(0.05 * (1 + math.sqrt(5)) * math.sqrt(xp)) + 1

    def xp_to_next_level(
        self, current_level: Optional[int] = None, current_xp: Optional[int] = None
    ) -> int:
        if current_xp is not None:
            current_level = self.get_level(current_xp)
        return self.get_xp(current_level + 1) - self.get_xp(current_level)

    def add_xp(self, message: Optional[Message] = None) -> int:
        if message:
            words = message.content.split(" ")
            eligble = len([w for w in words if len(w) > 1])
            xp = eligble + (10 * len(message.attachments))
            if xp == 0:
                xp = 1
            return min(xp, 50)
        else:
            return random.randint(1, 50) / self.multiplier

    def difference(self, ts: float) -> int:
        now = int(get_timestamp())
        return now - int(ts)

    def get_key(
        self, guild: Guild, member: Member, channel: Optional[VoiceChannel] = None
    ):
        if channel:
            return hash_(f"{guild.id}-{channel.id}-{member.id}")
        return hash_(f"{guild.id}-{member.id}")

    async def validate(
        self, guild: Guild, channel: VoiceChannel, member: Member
    ) -> bool:
        val = False
        key = hash_(f"{guild.id}-{channel.id}-{member.id}")
        if key in self.cache:
            if member.id == 352190010998390796:
                logger.info("user was in the cache")
            before_xp = (
                await self.bot.db.fetchval(
                    """SELECT xp FROM voice_levels WHERE guild_id = $1 AND user_id = $2""",
                    guild.id,
                    member.id,
                    cached=False,
                )
                or 0
            )
            after_xp = await self.bot.db.execute(
                """INSERT INTO voice_levels (guild_id, user_id, xp, time_spent) VALUES($1, $2, $3, $4) ON CONFLICT(guild_id ,user_id) DO UPDATE SET xp = voice_levels.xp + excluded.xp, time_spent = voice_levels.time_spent + excluded.time_spent RETURNING xp""",
                guild.id,
                member.id,
                self.add_xp(),
                self.difference(self.cache[key]["ts"]),
            )
            if self.get_level(int(before_xp)) != self.get_level(int(after_xp)):
                self.bot.dispatch(
                    "voice_level_up",
                    guild,
                    channel,
                    member,
                    self.get_level(int(after_xp)),
                )
            if key in self.cache:
                self.cache.pop(key)
            else:
                logger.warning(f"Key {key} was already removed from cache.")
            val = True
        else:
            if member.id == 352190010998390796:
                logger.info("user was not in the cache")
            self.cache[key] = {
                "guild": guild,
                "channel": channel,
                "member": member,
                "ts": int(get_timestamp()),
            }
        return val

    async def check_level_up(self, message: Message) -> bool:
        try:
            before_xp = (
                await self.bot.db.fetchval(
                    """SELECT xp FROM text_levels WHERE guild_id = $1 AND user_id = $2""",
                    message.guild.id,
                    message.author.id,
                    cached=False,
                )
                or 0
            )
            key = f"{message.guild.id}-{message.author.id}"
            added_xp = sum([self.add_xp(m) for m in self.text_cache[key]["messages"]])
            if not before_xp:
                before_xp = 0
            after_xp = (before_xp or 0) + (added_xp or 0)
            new_level = self.get_level(int(after_xp))
            if self.text_cache[key].get("messaged", 0) != new_level:
                if self.get_level(int(before_xp)) != self.get_level(int(after_xp)):
                    self.bot.dispatch(
                        "text_level_up",
                        message.guild,
                        message.author,
                        self.get_level(int(after_xp)),
                    )
                    await self.bot.db.execute("""INSERT INTO text_levels (guild_id, user_id, xp, msgs) VALUES($1, $2, $3, $4) ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = text_levels.xp + excluded.xp, msgs = text_levels.msgs + excluded.msgs RETURNING xp""",
                        message.guild.id,
                        message.author.id,
                        added_xp,
                        self.text_cache[key]["amount"]
                    )
                    self.text_cache.pop(key)
                    return True
        except Exception:
            pass
        return False


    async def validate_text(self, message: Message, execute: bool = False) -> bool:
        if message in self.messages:
            return False
        async with self.locks["text_levels"]:
            if message not in self.messages:
                self.messages.append(message)
            key = f"{message.guild.id}-{message.author.id}"
            if key in self.text_cache:
                if execute is True:
                    if message not in self.text_cache[key]["messages"]:
                        self.text_cache[key]["messages"].append(message)
                        amount = self.text_cache[key]["amount"] + 1
                    else:
                        amount = self.text_cache[key]["amount"]
                    added_xp = sum(
                        [self.add_xp(m) for m in self.text_cache[key]["messages"]]
                    )
                    self.text_cache[key]["messages"].clear()
                    if not await self.check_level_up(message):
                        await self.bot.db.execute(
                            """INSERT INTO text_levels (guild_id, user_id, xp, msgs) VALUES($1, $2, $3, $4) ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = text_levels.xp + excluded.xp, msgs = text_levels.msgs + excluded.msgs RETURNING xp""",
                            message.guild.id,
                            message.author.id,
                            added_xp,
                            amount,
                        )
                        self.text_cache.pop(key)
                    return True
                else:
                    self.text_cache[key]["amount"] += 1
                    self.text_cache[key]["messages"].append(message)
                    await self.check_level_up(message)
                    return True
            else:
                self.text_cache[key] = {"amount": 1, "messages": [message]}
                if execute is True:
                    added_xp = sum(
                        [self.add_xp(m) for m in self.text_cache[key]["messages"]]
                    )
                    amount = self.text_cache[key]["amount"]
                    if not await self.check_level_up(message):
                        await self.bot.db.execute(
                            """INSERT INTO text_levels (guild_id,user_id,xp,msgs) VALUES($1,$2,$3,$4) ON CONFLICT(guild_id,user_id) DO UPDATE SET xp = text_levels.xp + excluded.xp, msgs = text_levels.msgs + excluded.msgs RETURNING xp""",
                            message.guild.id,
                            message.author.id,
                            added_xp,
                            amount,
                        )
                        self.text_cache.pop(key)
                    return True
                else:
                    return True

    async def check_guild(self, guild: Guild) -> bool:
        if not await self.bot.db.fetchrow("""SELECT * FROM text_level_settings WHERE guild_id = $1""", guild.id):
            return False
        return True

    async def get_statistics(self, member: Member, type: str) -> Optional[list]:
        vals = [0, 0]
        if type.lower() == "text":
            if data := await self.bot.db.fetchrow(
                """SELECT xp, msgs FROM text_levels WHERE guild_id = $1 AND user_id = $2""",
                member.guild.id,
                member.id,
                cached=False,
            ):
                vals[0] += int(data.xp)
                vals[1] += int(data.msgs)
            key = f"{member.guild.id}-{member.id}"
            if key in self.text_cache:
                added_xp = sum([self.add_xp(m) for m in self.text_cache[key]["messages"]])
                vals[0] += added_xp
                vals[1] += len(self.text_cache[key]["messages"])

        else:
            if data := await self.bot.db.fetchrow(
                """SELECT xp, time_spent FROM voice_levels WHERE guild_id = $1 AND user_id = $2""",
                member.guild.id,
                member.id,
                cached=False,
            ):
                vals[0] += int(data.xp)
                vals[1] += int(data.time_spent)
        return vals


    async def do_voice_levels(self):
        if self.bot is None:
            return
        if not self.bot.is_ready:
            await self.bot.wait_until_ready()
        async with self.locks["voice_levels"]:
            active_voice_channels = [
                v
                for g in self.bot.guilds
                for v in g.voice_channels
                if len(v.members) > 0
            ]
            tasks = [
                self.validate(v.guild, v, m)
                for v in active_voice_channels
                for m in v.members
            ]
            if tasks:
                gather(*tasks)

    async def member_left(
        self, guild: Guild, channel: VoiceChannel, member: Member
    ) -> bool:
        if self.bot is None:
            return
        try:
            key = hash_(f"{guild.id}-{channel.id}-{member.id}")
            if key in self.cache:
                await self.validate(guild, channel, member)
                value = True
            else:
                value = False
        except Exception:
            value = False
        return value

    async def voice_update(self, member: Member, before: VoiceState, after: VoiceState):
        if before.channel is not None:
            await self.member_left(before.channel.guild, before.channel, member)
            if after.channel is not None:
                await self.validate(before.channel.guild, after.channel, member)
        else:
            if after.channel is not None:
                await self.validate(after.channel.guild, after.channel, member)

    async def do_message_event(self, message: Message):
        if self.bot is None:
            return
        if message.author.bot:
            return
        if not message.guild:
            return
        if not await self.check_guild(message.guild):
            return
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        await self.validate_text(message)

    async def do_text_levels(self):
        if self.bot is None:
            return

        tasks = [
            create_task(self.validate_text(m, execute=True)) for m in self.messages
        ]
        if tasks:
            for t in as_completed(tasks):
                await t

    def get_voice_time(self, time: int) -> str:
        currently = int(get_timestamp())
        difference = currently + time
        return naturaltime(datetime.from_timestamp(difference))

    async def get_member_xp(self, ctx: Context, type: str, member: Member) -> Embed:
        if data := await self.get_statistics(member, type):
            xp, amount = data
        else:
            return await ctx.fail("no data found yet")
        if type.lower() == "voice":
            amount = f"`{self.get_voice_time(amount)}`"
            amount_type = "vc time"
        else:
            amount_type = "messages"
        needed_xp = self.get_xp(self.get_level(xp) + 1)
        percentage_completed = int((xp / needed_xp) * 100)
        kwargs = (
            percentage_completed,
            "pink",
            int(100 - percentage_completed),
            "black",
        )
        # the kwargs white and black are the colors for the bar
        bar = File(fp=BytesIO(await _make_bar(*kwargs)), filename="bar.png")
        embed = (
            Embed(title=f"{str(member)}'s {type.lower()} level", url="https://greed.bot")
            .add_field(name=amount_type.lower(), value=amount, inline=False)
            .add_field(name="level", value=self.get_level(xp), inline=False)
            .add_field(
                name="xp",
                value=f"{xp} / {needed_xp}",
                inline=False,
            )
            .set_image(url=f"attachment://{bar.filename}")
        )
        return await ctx.send(embed=embed, file=bar)
