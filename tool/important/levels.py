import math
import random
import traceback
from datetime import datetime
from collections import defaultdict
from asyncio import Lock, create_task, gather, as_completed
from typing import Optional, Coroutine, Callable, Any, Dict, TypeVar
from asyncio.futures import Future
from typing_extensions import Self

from discord import Message, Client, Guild, VoiceChannel, Member, VoiceState, Embed, File
from discord.ext import tasks
from discord.ext.commands import Context
from io import BytesIO
from loguru import logger
from humanize import naturaltime
from xxhash import xxh64_hexdigest as hash_

from tool.collage import _make_bar

T = TypeVar("T")
Coro = Coroutine[Any, Any, T]
CoroT = TypeVar("CoroT", bound=Callable[..., Coro[Any]])


def get_timestamp():
    return datetime.now().timestamp()


class Level:
    def __init__(self, multiplier: float = 0.5, bot: Optional[Client] = None):
        self.multiplier = multiplier
        self.bot = bot
        self.listeners: Dict[str, Future] = {}
        self.logger = logger
        self.locks = defaultdict(Lock)
        self.cache = {}
        self.messages = []
        self.text_cache = {}
        self.level_cache = {}
        self.text_level_loop.start()

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
            exc = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            logger.info(f"text_level_loop raised {exc}")

    def get_xp(self, level: int) -> int:
        return math.ceil(math.pow((level - 1) / (0.05 * (1 + math.sqrt(5))), 2))

    def get_level(self, xp: int) -> int:
        return math.floor(0.05 * (1 + math.sqrt(5)) * math.sqrt(xp)) + 1

    def xp_to_next_level(self, current_level: Optional[int] = None, current_xp: Optional[int] = None) -> int:
        if current_xp is not None:
            current_level = self.get_level(current_xp)
        return self.get_xp(current_level + 1) - self.get_xp(current_level)

    def add_xp(self, message: Optional[Message] = None) -> int:
        if message:
            words = message.content.split(" ")
            eligible = len([w for w in words if len(w) > 1])
            xp = eligible + (10 * len(message.attachments))
            return min(xp, 50) if xp > 0 else 1
        return random.randint(1, 50) / self.multiplier

    def difference(self, ts: float) -> int:
        return int(get_timestamp()) - int(ts)

    def get_key(self, guild: Guild, member: Member, channel: Optional[VoiceChannel] = None):
        if channel:
            return hash_(f"{guild.id}-{channel.id}-{member.id}")
        return hash_(f"{guild.id}-{member.id}")

    async def validate(self, guild: Guild, channel: VoiceChannel, member: Member) -> bool:
        key = self.get_key(guild, member, channel)
        if key in self.cache:
            before_xp = await self.bot.db.fetchval(
                """SELECT xp FROM voice_levels WHERE guild_id = $1 AND user_id = $2""",
                guild.id,
                member.id,
                cached=False,
            ) or 0
            after_xp = await self.bot.db.execute(
                """INSERT INTO voice_levels (guild_id, user_id, xp, time_spent) VALUES($1, $2, $3, $4)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = voice_levels.xp + excluded.xp,
                time_spent = voice_levels.time_spent + excluded.time_spent RETURNING xp""",
                guild.id,
                member.id,
                self.add_xp(),
                self.difference(self.cache[key]["ts"]),
            )
            if self.get_level(int(before_xp)) != self.get_level(int(after_xp)):
                self.bot.dispatch("voice_level_up", guild, channel, member, self.get_level(int(after_xp)))
            self.cache.pop(key, None)
            return True
        self.cache[key] = {"guild": guild, "channel": channel, "member": member, "ts": int(get_timestamp())}
        return False

    async def check_level_up(self, message: Message) -> bool:
        try:
            before_xp = await self.bot.db.fetchval(
                """SELECT xp FROM text_levels WHERE guild_id = $1 AND user_id = $2""",
                message.guild.id,
                message.author.id,
                cached=False,
            ) or 0
            key = f"{message.guild.id}-{message.author.id}"
            added_xp = sum([self.add_xp(m) for m in self.text_cache[key]["messages"]])
            after_xp = before_xp + added_xp
            new_level = self.get_level(int(after_xp))
            if self.text_cache[key].get("messaged", 0) != new_level:
                if self.get_level(int(before_xp)) != self.get_level(int(after_xp)):
                    self.bot.dispatch("text_level_up", message.guild, message.author, self.get_level(int(after_xp)))
                    await self.bot.db.execute(
                        """INSERT INTO text_levels (guild_id, user_id, xp, msgs) VALUES($1, $2, $3, $4)
                        ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = text_levels.xp + excluded.xp,
                        msgs = text_levels.msgs + excluded.msgs RETURNING xp""",
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
        if message in self.messages:
            return False
        async with self.locks["text_levels"]:
            if message not in self.messages:
                self.messages.append(message)
            key = f"{message.guild.id}-{message.author.id}"
            if key in self.text_cache:
                if execute:
                    if message not in self.text_cache[key]["messages"]:

                        self.text_cache[key]["messages"].append(message)
                        amount = self.text_cache[key]["amount"] + 1
                    else:
                        amount = self.text_cache[key]["amount"]
                    added_xp = sum([self.add_xp(m) for m in self.text_cache[key]["messages"]])
                    self.text_cache[key]["messages"].clear()
                    if not await self.check_level_up(message):
                        await self.bot.db.execute(
                            """INSERT INTO text_levels (guild_id, user_id, xp, msgs) VALUES($1, $2, $3, $4)
                            ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = text_levels.xp + excluded.xp,
                            msgs = text_levels.msgs + excluded.msgs RETURNING xp""",
                            message.guild.id,
                            message.author.id,
                            added_xp,
                            amount,
                        )
                        self.text_cache.pop(key)
                    return True
                self.text_cache[key]["amount"] += 1
                self.text_cache[key]["messages"].append(message)
                await self.check_level_up(message)
                return True
            self.text_cache[key] = {"amount": 1, "messages": [message]}
            if execute:
                added_xp = sum([self.add_xp(m) for m in self.text_cache[key]["messages"]])
                amount = self.text_cache[key]["amount"]
                if not await self.check_level_up(message):
                    await self.bot.db.execute(
                        """INSERT INTO text_levels (guild_id, user_id, xp, msgs) VALUES($1, $2, $3, $4)
                        ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = text_levels.xp + excluded.xp,
                        msgs = text_levels.msgs + excluded.msgs RETURNING xp""",
                        message.guild.id,
                        message.author.id,
                        added_xp,
                        amount,
                    )
                    self.text_cache.pop(key)
                return True
            return True

    async def check_guild(self, guild: Guild) -> bool:
        return bool(await self.bot.db.fetchrow("""SELECT * FROM text_level_settings WHERE guild_id = $1""", guild.id))

    async def get_statistics(self, member: Member, type: str) -> Optional[list]:
        vals = [0, 0]
        if type.lower() == "text":
            data = await self.bot.db.fetchrow(
                """SELECT xp, msgs FROM text_levels WHERE guild_id = $1 AND user_id = $2""",
                member.guild.id,
                member.id,
                cached=False,
            )
            if data:
                vals[0] += int(data.xp)
                vals[1] += int(data.msgs)
            key = f"{member.guild.id}-{member.id}"
            if key in self.text_cache:
                added_xp = sum([self.add_xp(m) for m in self.text_cache[key]["messages"]])
                vals[0] += added_xp
                vals[1] += len(self.text_cache[key]["messages"])
        else:
            data = await self.bot.db.fetchrow(
                """SELECT xp, time_spent FROM voice_levels WHERE guild_id = $1 AND user_id = $2""",
                member.guild.id,
                member.id,
                cached=False,
            )
            if data:
                vals[0] += int(data.xp)
                vals[1] += int(data.time_spent)
        return vals

    async def do_voice_levels(self):
        if not self.bot or not self.bot.is_ready:
            await self.bot.wait_until_ready()
        async with self.locks["voice_levels"]:
            active_voice_channels = [v for g in self.bot.guilds for v in g.voice_channels if v.members]
            tasks = [self.validate(v.guild, v, m) for v in active_voice_channels for m in v.members]
            if tasks:
                await gather(*tasks)

    async def member_left(self, guild: Guild, channel: VoiceChannel, member: Member) -> bool:
        key = self.get_key(guild, member, channel)
        if key in self.cache:
            await self.validate(guild, channel, member)
            return True
        return False

    async def voice_update(self, member: Member, before: VoiceState, after: VoiceState):
        if before.channel:
            await self.member_left(before.channel.guild, before.channel, member)
        if after.channel:
            await self.validate(after.channel.guild, after.channel, member)

    async def do_message_event(self, message: Message):
        if not self.bot or message.author.bot or not message.guild or not await self.check_guild(message.guild):
            return
        ctx = await self.bot.get_context(message)
        if not ctx.valid:
            await self.validate_text(message)

    async def do_text_levels(self):
        tasks = [create_task(self.validate_text(m, execute=True)) for m in self.messages]
        if tasks:
            for t in as_completed(tasks):
                await t

    def get_voice_time(self, time: int) -> str:
        return naturaltime(datetime.fromtimestamp(int(get_timestamp()) + time))

    async def get_member_xp(self, ctx: Context, type: str, member: Member) -> Embed:
        data = await self.get_statistics(member, type)
        if not data:
            return await ctx.fail("no data found yet")
        xp, amount = data
        amount_type = "vc time" if type.lower() == "voice" else "messages"
        if type.lower() == "voice":
            amount = f"`{self.get_voice_time(amount)}`"
        needed_xp = self.get_xp(self.get_level(xp) + 1)
        percentage_completed = int((xp / needed_xp) * 100)
        bar = File(
            fp=BytesIO(await _make_bar(percentage_completed, "pink", 100 - percentage_completed, "black")),
            filename="bar.png",
        )
        embed = (
            Embed(title=f"{str(member)}'s {type.lower()} level", url="https://greed.wtf")
            .add_field(name=amount_type.lower(), value=amount, inline=False)
            .add_field(name="level", value=self.get_level(xp), inline=False)
            .add_field(name="xp", value=f"{xp} / {needed_xp}", inline=False)
            .set_image(url=f"attachment://{bar.filename}")
        )
        return await ctx.send(embed=embed, file=bar)
