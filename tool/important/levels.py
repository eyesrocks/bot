import math
import random
from datetime import datetime
from collections import defaultdict
from asyncio import Lock, gather, create_task, sleep, Future, get_event_loop
from typing import Optional, Coroutine, Callable, Any, Dict, TypeVar, List
from asyncio.futures import Future
from typing_extensions import Self

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
from discord.ext.commands import Context
from io import BytesIO
from loguru import logger
from humanize import naturaltime
from xxhash import xxh64_hexdigest as hash_

from tool.collage import _make_bar

T = TypeVar("T")
Coro = Coroutine[Any, Any, T]
CoroT = TypeVar("CoroT", bound=Callable[..., Coro[Any]])


def get_timestamp() -> float:
    return datetime.now().timestamp()


class Level:
    def __init__(self, multiplier: float = 0.5, bot: Optional[Client] = None):
        self.multiplier = multiplier
        self.bot = bot
        self.logger = logger

        self.locks = defaultdict(Lock)
        self.text_cache_lock = Lock()

        self.cache: Dict[str, Dict[str, Any]] = {}
        self.messages: Dict[str, Message] = {}
        self.text_cache: Dict[str, Dict[str, Any]] = {}
        self.level_cache: Dict[str, Any] = {}

        self.flush_task: Optional[Future] = None

    async def setup(self, bot: Client) -> Self:
        """
        Setup the leveling system. Registers the on_message listener and
        starts the periodic flush task for text XP.
        """
        self.bot = bot
        self.logger.info("Starting levelling loop")
        self.bot.add_listener(self.do_message_event, "on_message")
        self.flush_task = create_task(self.periodic_flush_text_cache())
        self.logger.info("Levelling loop started")
        return self

    async def periodic_flush_text_cache(self):
        """Periodically flush the aggregated text XP cache to the database."""
        flush_interval = 10
        while True:
            try:
                await sleep(flush_interval)
                await self.flush_text_cache()
            except Exception as e:
                self.logger.error(f"Error during periodic flush: {e}")

    async def flush_text_cache(self):
        """Flush all cached text-level data in a batch update."""
        async with self.text_cache_lock:
            keys = list(self.text_cache.keys())
            for key in keys:
                data = self.text_cache.pop(key)
                added_xp = sum(self.add_xp(m) for m in data["messages"])
                amount = data["amount"]
                try:
                    await self.bot.db.execute(
                        """INSERT INTO text_levels (guild_id, user_id, xp, msgs) 
                           VALUES($1, $2, $3, $4)
                           ON CONFLICT(guild_id, user_id) DO UPDATE 
                           SET xp = text_levels.xp + excluded.xp,
                               msgs = text_levels.msgs + excluded.msgs 
                           RETURNING xp""",
                        data["guild_id"],
                        data["user_id"],
                        added_xp,
                        amount,
                    )
                    self.logger.debug(
                        f"Flushed text cache for key {key} (XP +{added_xp}, msgs {amount})"
                    )
                except Exception as e:
                    self.logger.error(f"Failed to flush text cache for key {key}: {e}")

    def get_xp(self, level: int) -> int:
        base = (level - 1) / (0.05 * (1 + math.sqrt(5)))
        return math.ceil(math.pow(base, 2))

    def get_level(self, xp: int) -> int:
        return math.floor(0.05 * (1 + math.sqrt(5)) * math.sqrt(xp)) + 1

    def xp_to_next_level(
        self, current_level: Optional[int] = None, current_xp: Optional[int] = None
    ) -> int:
        if current_xp is not None:
            current_level = self.get_level(current_xp)
        return self.get_xp(current_level + 1) - self.get_xp(current_level)

    def add_xp(self, message: Optional[Message] = None) -> int:
        if message:
            eligible = sum(1 for w in message.content.split() if len(w) > 1)
            xp = eligible + (10 * len(message.attachments))
            return min(xp, 50) if xp > 0 else 1
        return int(random.randint(1, 50) / self.multiplier)

    def difference(self, ts: float) -> int:
        return int(get_timestamp()) - int(ts)

    def get_key(
        self, guild: Guild, member: Member, channel: Optional[VoiceChannel] = None
    ) -> str:
        return hash_(f"{guild.id}-{channel.id if channel else ''}-{member.id}")

    async def validate(
        self, guild: Guild, channel: VoiceChannel, member: Member
    ) -> bool:
        """
        Validate and update a voice-level entry. If a cached entry exists,
        update the DB with new XP and dispatch level-up if necessary.
        """
        key = self.get_key(guild, member, channel)
        if key in self.cache:
            before_xp = (
                await self.bot.db.fetchval(
                    """SELECT xp FROM voice_levels WHERE guild_id = $1 AND user_id = $2""",
                    guild.id,
                    member.id,
                    cached=False,
                )
                or 0
            )
            added_xp = self.add_xp()
            after_xp = await self.bot.db.execute(
                """INSERT INTO voice_levels (guild_id, user_id, xp, time_spent) 
                   VALUES($1, $2, $3, $4)
                   ON CONFLICT(guild_id, user_id) DO UPDATE 
                   SET xp = voice_levels.xp + excluded.xp,
                       time_spent = voice_levels.time_spent + excluded.time_spent 
                   RETURNING xp""",
                guild.id,
                member.id,
                added_xp,
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
            self.cache.pop(key, None)
            return True
        self.cache[key] = {
            "guild": guild,
            "channel": channel,
            "member": member,
            "ts": int(get_timestamp()),
        }
        return False

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
            added_xp = sum(self.add_xp(m) for m in self.text_cache[key]["messages"])
            after_xp = before_xp + added_xp
            new_level = self.get_level(int(after_xp))
            if self.text_cache[key].get("messaged", 0) != new_level:
                if self.get_level(int(before_xp)) != self.get_level(int(after_xp)):
                    self.bot.dispatch(
                        "text_level_up", message.guild, message.author, new_level
                    )
                    await self.bot.db.execute(
                        """INSERT INTO text_levels (guild_id, user_id, xp, msgs) 
                           VALUES($1, $2, $3, $4)
                           ON CONFLICT(guild_id, user_id) DO UPDATE 
                           SET xp = text_levels.xp + excluded.xp,
                               msgs = text_levels.msgs + excluded.msgs 
                           RETURNING xp""",
                        message.guild.id,
                        message.author.id,
                        added_xp,
                        self.text_cache[key]["amount"],
                    )
                    self.text_cache.pop(key)
                    return True
        except Exception:
            pass
        return False

    async def validate_text(self, message: Message, execute: bool = False) -> bool:
        """
        Accumulate text XP for a message. If 'execute' is True, the XP is
        immediately processed; otherwise, it is queued for the periodic flush.
        """
        msg_id = f"{message.guild.id}-{message.channel.id}-{message.id}"
        if msg_id in self.messages:
            return False
        async with self.locks["text_levels"]:
            if msg_id not in self.messages:
                self.messages[msg_id] = message
            key = f"{message.guild.id}-{message.author.id}"
            async with self.text_cache_lock:
                if key in self.text_cache:
                    self.text_cache[key]["amount"] += 1
                    self.text_cache[key]["messages"].append(message)
                else:
                    self.text_cache[key] = {
                        "amount": 1,
                        "messages": [message],
                        "guild_id": message.guild.id,
                        "user_id": message.author.id,
                    }
            if execute:
                async with self.text_cache_lock:
                    data = self.text_cache.pop(key, None)
                if data:
                    added_xp = sum(self.add_xp(m) for m in data["messages"])
                    await self.bot.db.execute(
                        """INSERT INTO text_levels (guild_id, user_id, xp, msgs) 
                           VALUES($1, $2, $3, $4)
                           ON CONFLICT(guild_id, user_id) DO UPDATE 
                           SET xp = text_levels.xp + excluded.xp,
                               msgs = text_levels.msgs + excluded.msgs 
                           RETURNING xp""",
                        message.guild.id,
                        message.author.id,
                        added_xp,
                        data["amount"],
                    )
                return True
            await self.check_level_up(message)
            return True

    async def check_guild(self, guild: Guild) -> bool:
        return bool(
            await self.bot.db.fetchrow(
                """SELECT 1 FROM text_level_settings WHERE guild_id = $1""", guild.id
            )
        )

    async def get_statistics(self, member: Member, type: str) -> Optional[List[Any]]:
        xp, amount = 0, 0
        if type.lower() == "text":
            data = await self.bot.db.fetchrow(
                """SELECT xp, msgs FROM text_levels WHERE guild_id = $1 AND user_id = $2""",
                member.guild.id,
                member.id,
                cached=False,
            )
            if data:
                xp += int(data.xp)
                amount += int(data.msgs)
            key = f"{member.guild.id}-{member.id}"
            if key in self.text_cache:
                xp += sum(self.add_xp(m) for m in self.text_cache[key]["messages"])
                amount += len(self.text_cache[key]["messages"])
        else:
            data = await self.bot.db.fetchrow(
                """SELECT xp, time_spent FROM voice_levels WHERE guild_id = $1 AND user_id = $2""",
                member.guild.id,
                member.id,
                cached=False,
            )
            if data:
                xp += int(data.xp)
                amount += int(data.time_spent)
        return [xp, amount] if xp or amount else None

    async def do_voice_levels(self):
        if not self.bot or not self.bot.is_ready:
            await self.bot.wait_until_ready()
        async with self.locks["voice_levels"]:
            tasks = [
                self.validate(guild, vc, member)
                for guild in self.bot.guilds
                for vc in guild.voice_channels
                if vc.members
                for member in vc.members
            ]
            if tasks:
                await gather(*tasks)

    async def member_left(
        self, guild: Guild, channel: VoiceChannel, member: Member
    ) -> bool:
        key = self.get_key(guild, member, channel)
        if key in self.cache:
            await self.validate(guild, channel, member)
            return True
        return False

    async def voice_update(self, member: Member, before: VoiceState, after: VoiceState):
        if before.channel:
            await self.member_left(before.guild, before.channel, member)
        if after.channel:
            await self.validate(after.guild, after.channel, member)

    async def do_message_event(self, message: Message):
        if (
            not self.bot
            or message.author.bot
            or not message.guild
            or not await self.check_guild(message.guild)
        ):
            return
        ctx = await self.bot.get_context(message)
        if not ctx.valid:
            await self.validate_text(message)

    def get_voice_time(self, time: int) -> str:
        return naturaltime(datetime.fromtimestamp(int(get_timestamp()) + time))

    async def get_member_xp(self, ctx: Context, type: str, member: Member) -> Embed:
        data = await self.get_statistics(member, type)
        if not data:
            return await ctx.fail("No data found yet")
        xp, amount = data
        amount_type = "VC Time" if type.lower() == "voice" else "messages"
        if type.lower() == "voice":
            amount = f"`{self.get_voice_time(amount)}`"
        needed_xp = self.get_xp(self.get_level(xp) + 1)
        percentage = int((xp / needed_xp) * 100)
        bar_img = BytesIO(
            await _make_bar(percentage, "#2f4672", 100 - percentage, "black")
        )
        bar = File(fp=bar_img, filename="bar.png")

        embed = (
            Embed(
                title=f"{member}'s {type.lower()} Level",
                url="https://greed.rocks/",
                color=0x2F4672,
            )
            .add_field(name=amount_type, value=amount, inline=False)
            .add_field(name="Level", value=self.get_level(xp), inline=False)
            .add_field(name="XP", value=f"{xp} / {needed_xp}", inline=False)
            .set_image(url=f"attachment://{bar.filename}")
        )
        await ctx.send(embed=embed, file=bar)
        return embed

    def get_coroutine_names_with_kwarg(self, kwarg_name: str) -> List[str]:
        """
        (This method is unchanged from earlier.)
        """
        from inspect import getmembers, iscoroutinefunction, signature

        members = getmembers(self, predicate=iscoroutinefunction)
        coroutine_names = []
        for name, func in members:
            if kwarg_name in signature(func).parameters:
                coroutine_names.append(name)
        return coroutine_names
