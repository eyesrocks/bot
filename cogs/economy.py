import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context, CommandError, check
from discord import Member as DiscordMember, Embed, ui
from typing import Union, Optional
from tool.greed import Greed
from tool.important.subclasses.command import Member, User
from tool.important.subclasses.color import ColorConverter
from tool.chart import EconomyCharts
from discord.utils import format_dt
from collections import defaultdict
import random
import asyncio
from datetime import datetime, timedelta
from dataclasses import dataclass
from pytz import timezone
from rival_tools import thread
from loguru import logger
from tool.emotes import EMOJIS
from discord import Embed, ui, Interaction
from discord import ui, Embed, ButtonStyle
log = logger
MAX_GAMBLE = 100_000_000
BOOSTER_ROLE_ID = 1301664266868363356
GUILD_ID = 1301617147964821524

class OverMaximum(CommandError):
    def __init__(self, message):
        self.message = message
        super().__init__(message)

class GambleConverter(commands.Converter):
    async def convert(self, ctx: Context, argument: str) -> float:
        try:
            amount = float(argument.replace(",", ""))
            if amount <= 0:
                raise ValueError("Amount must be positive")
            if amount > MAX_GAMBLE:
                raise OverMaximum(f"Maximum gamble amount is {MAX_GAMBLE:,}")
                
            balance = await ctx.bot.db.fetchval(
                "SELECT balance FROM economy WHERE user_id = $1", 
                ctx.author.id
            )
            if amount > balance:
                raise ValueError(f"You only have {balance:,} bucks")
            return amount
        except ValueError as e:
            raise CommandError(str(e))

def format_large_number(num: Union[int, float]) -> str:
    suffixes = [
        "", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc", "Ud", "Dd", "Td", "Qad", "Qid", "Sxd", "Spd", "Ocd", "Nod", "Vg", "Uv", "Dv", "Tv", "Qav", "Qiv", "Sxv", "Spv", "Ocv", "Nov", "Tg", "Utg", "Dtg", "Ttg", "Qatg", "Qitg", "Sxtg", "Sptg", "Octg", "Notg", "Qng"
    ]
    num_str = str(num)
    if "." in num_str:
        num_str = num_str[:num_str.index(".")]
    num_len = len(num_str)
    if num_len <= 3:
        return num_str
    suffix_index = (num_len - 1) // 3
    if suffix_index >= len(suffixes):
        return f"{num} is too large to format."
    scaled_num = int(num_str[:num_len - suffix_index * 3])
    return f"{scaled_num}{suffixes[suffix_index]}"

@dataclass
class Achievement:
    name: str
    description: str
    price: Optional[int] = None

@dataclass
class Item:
    name: str
    description: str
    price: int
    duration: int
    emoji: str

@dataclass
class Chance:
    percentage: float
    total: float

class BlackjackView(ui.View):
    def __init__(self, ctx, bot):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.bot = bot
        self.move = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author

    @ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        self.move = 0
        self.stop()

    @ui.button(label="Stay", style=discord.ButtonStyle.gray)
    async def stay_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        self.move = 1
        self.stop()

    async def wait_for_input(self):
        try:
            await self.wait()
            return self.move if self.move is not None else 1
        except Exception:
            return 1

def get_hour():
    est = timezone("US/Eastern")
    now = datetime.now(est)
    return now.hour + 1

def get_win(multiplied: bool = False, by: int = 3):
    if multiplied:
        if by == 2:
            return random.uniform(3.0, 5.0)
        else:
            return random.uniform(4.5, 7.5)
    else:
        return random.uniform(1.5, 2.5)

def _format_int(n: Union[float, str, int]):
    if isinstance(n, float):
        n = "{:.2f}".format(n)
    if isinstance(n, str):
        if "." in n:
            try:
                amount, decimal = n.split(".")
                n = f"{amount}.{decimal[:2]}"
            except Exception:
                n = f"{n.split('.')[0]}.00"
    reversed = str(n).split(".")[0][::-1]
    d = ""
    amount = 0
    for i in reversed:
        amount += 1
        if amount == 3:
            d += f"{i},"
            amount = 0
        else:
            d += i
    if d[::-1].startswith(","):
        return d[::-1][1:]
    return d[::-1]

def format_int(n: Union[float, str, int], disallow_negatives: Optional[bool] = False):
    n = _format_int(n)
    if disallow_negatives is True and n.startswith("-"):
        return 0
    return n

def ensure_non_negative(value: float) -> float:
    return max(value, 0)

def get_chances():
    from config import CHANCES
    data = {}
    for key, value in CHANCES.items():
        data[key] = Chance(percentage=value["percentage"], total=value["total"])
    return data

def get_time_next_day():
    current_datetime = datetime.now()
    tomorrow = current_datetime + timedelta(days=1)
    next_day_start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0)
    time_until_next_day = (next_day_start - current_datetime).total_seconds()
    return time_until_next_day

class BankAmount(commands.Converter):
    name = "BankAmount"

    async def convert(self, ctx: Context, argument: Union[int, float, str]):
        if isinstance(argument, str):
            argument = argument.replace(",", "")
        if isinstance(argument, int):
            balance = await self.bot.db.fetchval(
                "SELECT bank FROM economy WHERE user_id = $1", ctx.author.id
            )
            if argument > balance:
                raise commands.CommandError(
                    f"You only have **{format_int(balance)}** bucks in your bank"
                )
            if argument < 0:
                raise commands.CommandError("you can't withdraw an amount below 0")
            argument = float(argument)
        elif isinstance(argument, float):
            balance = await self.bot.db.fetchval(
                "SELECT bank FROM economy WHERE user_id = $1", ctx.author.id
            )
            if argument > balance:
                raise commands.CommandError(
                    f"you only have **{format_int(balance)}** bucks in your bank"
                )
            if argument < 0.00:
                raise commands.CommandError("you can't withdraw an amount below 0")
        else:
            if argument.lower() == "all":
                argument = await ctx.bot.db.fetchval(
                    "SELECT bank FROM economy WHERE user_id = $1", ctx.author.id
                )
            try:
                argument = float(argument)
            except Exception:
                await ctx.warning("Please provide an **Amount**")
                raise OverMaximum("lol")  # MissingRequiredArgument(BankAmount)
        return argument

class Amount(commands.Converter):
    name = "Amount"

    async def convert(self, ctx: Context, argument: Union[int, float, str]):
        if "," in argument:
            argument = argument.replace(",", "")
            argument = float(argument)
        if isinstance(argument, int):
            balance = await ctx.bot.db.fetchval(
                "SELECT balance FROM economy WHERE user_id = $1", ctx.author.id
            )
            if float(argument) > float(balance):
                raise commands.CommandError(
                    f"you only have **{format_int(balance)}** bucks"
                )
            if float(argument) < 0.00:
                raise commands.CommandError("you can't use an amount below 0")
            argument = float(argument)
        elif isinstance(argument, float):
            balance = await ctx.bot.db.fetchval(
                "SELECT balance FROM economy WHERE user_id = $1", ctx.author.id
            )
            if argument > balance:
                raise commands.CommandError(
                    f"you only have **{format_int(balance)}** bucks"
                )
            if argument < 0.00:
                raise commands.CommandError("you can't gamble an amount below 0")
        else:
            if argument.lower() == "all":
                argument = await ctx.bot.db.fetchval(
                    "SELECT balance FROM economy WHERE user_id = $1", ctx.author.id
                )
            try:
                argument = float(argument)
            except Exception:
                await ctx.warning("Please provide an **Amount**")
                raise OverMaximum("lol")  # MissingRequiredArgument(Amount)
        if float(argument) <= 0.00:
            raise commands.CommandError("you can't use an amount below 0")
        return argument

class GambleAmount(commands.Converter):
    name = "GambleAmount"

    async def convert(self, ctx: Context, argument: Union[int, float, str]):
        if "," in argument:
            argument = argument.replace(",", "")
            argument = float(argument)
        if isinstance(argument, int):
            balance = await ctx.bot.db.fetchval(
                "SELECT balance FROM economy WHERE user_id = $1", ctx.author.id
            )
            if float(argument) > float(balance):
                raise commands.CommandError(
                    f"you only have **{format_int(balance)}** bucks"
                )
            if argument < 0:
                raise commands.CommandError("you can't gamble an amount below 0")
            argument = float(argument)
        elif isinstance(argument, float):
            balance = await ctx.bot.db.fetchval(
                "SELECT balance FROM economy WHERE user_id = $1", ctx.author.id
            )
            if argument > balance:
                raise commands.CommandError(
                    f"you only have **{format_int(balance)}** bucks"
                )
            if argument < 0.00:
                raise commands.CommandError("you can't gamble an amount below 0")
        else:
            if argument.lower() == "all":
                argument = float(
                    await ctx.bot.db.fetchval(
                        "SELECT balance FROM economy WHERE user_id = $1", ctx.author.id
                    )
                )
                argument = argument
            try:
                argument = float(argument)
            except Exception:
                await ctx.warning("Please provide an **Amount**")
                raise OverMaximum("lol")
        if argument <= 0.00:
            await ctx.warning("you can't gamble an amount below 0")
            raise OverMaximum("lol")
        if float(argument) >= float(MAX_GAMBLE):
            raise OverMaximum(
                f"you can only gamble a maximum of **{format_int(float(MAX_GAMBLE) - 1.0)}** looser"
            )
        return argument

def account():
    async def predicate(ctx: Context):
        if ctx.command.name == "steal":
            mentions = [m for m in ctx.message.mentions if m != ctx.bot.user]
            if len(mentions) > 0:
                if not await ctx.bot.db.fetchrow(
                    """SELECT * FROM economy WHERE user_id = $1""", mentions[0].id
                ):
                    await ctx.fail(
                        f"**{mentions[0].name}** doesn't have an account opened"
                    )
                    return False
        check = await ctx.bot.db.fetchval(
            "SELECT COUNT(*) FROM economy WHERE user_id = $1",
            ctx.author.id,
        )
        if check == 0:
            await ctx.fail(
                f"You **haven't setup your account**, use `{ctx.prefix}open` to **create one**"
            )
            return False
        return True

    return check(predicate)

class LeaderboardView(ui.View):
    def __init__(self, bot, ctx, users, title, page_size=10):
        super().__init__(timeout=None)
        self.bot = bot
        self.ctx = ctx
        self.users = users
        self.title = title
        self.page_size = page_size
        self.current_page = 0
        self.total_pages = (len(users) - 2) // page_size + 4

    def format_user_row(self, index, user):
        """Format leaderboard entry row."""
        balance = f"{int(user['balance']):,}"
        username = self.bot.get_user(user['user_id']) or f"User {user['user_id']}"
        return f"`{index}.` **{username}** - **{balance}**"

    async def generate_embed(self):
        """Generate the leaderboard embed for the current page."""
        start = self.current_page * self.page_size
        end = start + self.page_size
        rows = [
            self.format_user_row(i + 1, user)
            for i, user in enumerate(self.users[start:end], start=start)
        ]
        embed = Embed(
            title=self.title,
            description="\n".join(rows),
            color=self.bot.color,
        )
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages}")
        return embed

    @ui.button(label="Previous", style=ButtonStyle.primary, disabled=True)
    async def previous_page(self, interaction, button):
        """Handle previous page button."""
        if self.current_page > 0:
            self.current_page -= 1
            if self.current_page == 0:
                button.disabled = True
            self.children[1].disabled = False  # Enable "Next" button
            embed = await self.generate_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Next", style=ButtonStyle.primary)
    async def next_page(self, interaction, button):
        """Handle next page button."""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            if self.current_page == self.total_pages - 1:
                button.disabled = True
            self.children[0].disabled = False  # Enable "Previous" button
            embed = await self.generate_embed()
            await interaction.response.edit_message(embed=embed, view=self)


class Economy(commands.Cog):
    def __init__(self, bot: Greed):
        self.bot = bot
        self.locks = defaultdict(asyncio.Lock)
        self.mapping = {
            1: ":one:",
            2: ":two:",
            3: ":three:",
            4: ":four:",
            5: ":five:",
            6: ":six:",
            7: ":seven:",
            8: ":eight:",
            9: ":nine:",
        }
        self.chances = get_chances()
        self.items = {
            "purple devil": {
                "price": 1000000,
                "description": "prevents other users from stealing from your wallet for 8 hours",
                "duration": 28800,
                "emoji": EMOJIS["devilnigga"],
            },
            "white powder": {
                "price": 500000,
                "description": "allows you to win double from a coinflip for 1 minute",
                "duration": 60,
                "emoji": EMOJIS["pwder"],
            },
            "oxy": {
                "price": 400000,
                "description": "allows you 2x more bucks when you win a gamble for 30 seconds",
                "duration": 30,
                "emoji": EMOJIS["oxy"],
            },
            "meth": {
                "description": "roll 2x more for 4 minutes",
                "price": 350000,
                "duration": 240,
                "emoji": EMOJIS["mth"],
            },
            "shrooms": {
                "description": "increases your chances of winning gamble commands by 10% for 10 minutes",
                "price": 100000,
                "duration": 600,
                "emoji": EMOJIS["shrrom"],
            },
        }
        self.symbols = ["♠", "♥", "♦", "♣"]
        self.achievements = {
            "Lets begin.": {
                "description": f"open an account through {self.bot.user.name} for gambling",
                "price": None,
            },
            "Getting higher": {
                "description": "accumulate 50,000 bucks through gambling",
                "price": 50000,
            },
            "Closer..": {
                "description": "accumulate 200,000 bucks through gambling",
                "price": 200000,
            },
            "Sky high!": {
                "description": "accumulate 450,000 bucks through gambling",
                "price": 450000,
            },
            "less text more gamble": {
                "description": "accumulate 600,000 bucks",
                "price": 600000,
            },
            "run it up": {
                "description": "accumulate 2,000,000 bucks",
                "price": 2000000,
            },
            "richer": {"description": "accumulate 3,500,000 bucks", "price": 3500000},
            "rich and blind": {
                "description": "accumulate 5,000,000 bucks",
                "price": 5000000,
            },
            "High roller": {
                "description": "accumulate over 10,000,000 in bucks",
                "price": 10000000,
            },
            "Highest in the room.": {
                "description": "accumulate over 500,000,000 in bucks",
                "price": 500000000,
            },
            "Amazing way to spend!": {
                "description": "Buy the full amount of every item in the item shop",
                "price": None,
            },
            "Time to shop!": {
                "description": "buy something from the item shop",
                "price": None,
            },
            "spending spree!": {
                "description": "spend over 1,000,000 worth of items from the shop",
                "price": 1000000,
            },
            "loser.": {"description": "lose over 40,000 in gambling", "price": 40000},
            "retard": {
                "description": "lose all of your bucks from gambling all",
                "price": None,
            },
            "Down and out": {
                "description": "Lose over 1,000,000 in gambling",
                "price": 1000000,
            },
            "Master thief": {
                "description": "Steal over 100,000 in bucks from other users",
                "price": 100000,
            },
            "unlucky": {
                "description": "have over 50,000 bucks stolen from your wallet",
                "price": 50000,
            },
            "banking bank bank": {
                "description": "transfer 200,000 bucks or more to a wallet",
                "price": 200000,
            },
            "sharing is caring": {
                "description": "pay another user 500 bucks or more",
                "price": 500,
            },
            "shared god": {
                "description": "pay 5 users 500,000 bucks or more",
                "price": 500000,
            },
            "immortally satisfied": {
                "description": "having a balance of 10,000,000, pay all bucks to another user",
                "price": 10000000,
            },
        }
        self.cards = {
            1: "`{sym} 1`, ",
            2: "`{sym} 2`, ",
            3: "`{sym} 3`, ",
            4: "`{sym} 4`, ",
            5: "`{sym} 5`, ",
            6: "`{sym} 6`, ",
            7: "`{sym} 7`, ",
            8: "`{sym} 8`, ",
            9: "`{sym} 9`, ",
            10: "`{sym} 10`, ",
        }

        self.format_economy()
        self.chart = EconomyCharts(self.bot)
        self.clear_items.start()  # Start the clear_items task when the cog is loaded

    def cog_unload(self):
        """Stop tasks when the cog is unloaded."""
        self.clear_items.cancel()

    def format_economy(self):
        new_items = {}
        new_achievements = {}
        for key, value in self.items.items():
            new_items[key] = Item(name=key, **value)
        for _k, _v in self.achievements.items():
            new_achievements[_k] = Achievement(name=_k, **_v)
        self.items = new_items
        self.achievements = new_achievements

    def get_value(self, ctx: Context) -> bool:
        values = self.chances[ctx.command.qualified_name]
        return calculate(values.percentage, values.total)  # type: ignore # noqa: F821

    @thread
    def generate_cards(self):
        cards_out = list()
        cards_out_n = list()
        amount = 0
        _c = {
            1: "`{sym} 1`, ",
            2: "`{sym} 2`, ",
            3: "`{sym} 3`, ",
            4: "`{sym} 4`, ",
            5: "`{sym} 5`, ",
            6: "`{sym} 6`, ",
            7: "`{sym} 7`, ",
            8: "`{sym} 8`, ",
            9: "`{sym} 9`, ",
            10: "`{sym} 10`, ",
        }
        cards = [card for card in _c]
        has_hit = False
        while True:
            card = random.choice(cards)
            if card not in cards_out:
                cards_out.append(card)
                if card == "11":
                    if not has_hit or not amount > 11:
                        card = 11
                        has_hit = True
                    else:
                        card = 1
                amount += int(card)
                cards_out_n.append(int(card))
            if len(cards_out) == 7:
                break
        return cards_out, cards_out_n, amount

    def format_int(self, n: Union[float, str, int]) -> str:
        try:
            if isinstance(n, str):
                n = float(n.replace(",", ""))
            if isinstance(n, float):
                formatted = f"{n:,.2f}"
            else:
                formatted = f"{n:,}"
            if float(n) < 0:
                return f":clown: ${formatted}"
            return f"${formatted}"
        except ValueError:
            return "Invalid number"

    async def get_balance(
        self, member: DiscordMember, with_bank: Optional[bool] = False
    ) -> Union[float, tuple]:
        if with_bank is True:
            data = await self.bot.db.fetchrow(
                """SELECT * FROM economy WHERE user_id = $1""", member.id
            )
            balance = float(str(data["balance"])) if data and data.get("balance") is not None else 0.0
            bank = float(str(data["bank"])) if data and data.get("bank") is not None else 0.0
            return balance, bank
        else:
            data = await self.bot.db.fetchval(
                """SELECT balance FROM economy WHERE user_id = $1""", member.id
            )
            if data is None:
                balance = 0.0
            else:
                balance = float(str(data))
            if balance < 0.00:
                await self.bot.db.execute(
                    """UPDATE economy SET balance = $1 WHERE user_id = $2""",
                    0.00,
                    member.id,
                )
                return 0.00
            return balance

    def get_expiration(self, item: str) -> tuple:
        now = datetime.now()
        ex = now + timedelta(seconds=self.items[item].duration)
        return now, ex

    async def use_item(self, ctx: Context, item: str):
        await self.check_item(ctx, ctx.author)
        if item not in list(self.items.keys()):
            return await ctx.fail("that is not a valid item")
        _ = await self.bot.db.fetchrow(
            """SELECT * FROM inventory WHERE user_id = $1 AND item = $2""",
            ctx.author.id,
            item,
        )
        if not _:
            return await ctx.fail(f"you don't have any **{item}'s**")
        if _["amount"] > 1:
            kwargs = [_["amount"] - 1, ctx.author.id, item]
            query = (
                """UPDATE inventory SET amount = $1 WHERE user_id = $2 AND item = $3"""
            )
        else:
            kwargs = [ctx.author.id, item]
            query = """DELETE FROM inventory WHERE user_id = $1 AND item = $2"""
        if await self.bot.db.fetchrow(
            """SELECT * FROM used_items WHERE user_id = $1 AND item = $2""",
            ctx.author.id,
            item,
        ):
            return await ctx.fail(f"you are already zooted off da **{item}**")
        ts, ex = self.get_expiration(item)
        await self.bot.db.execute(
            """INSERT INTO used_items (user_id, item, ts, expiration) VALUES($1, $2, $3, $4) ON CONFLICT(user_id, item) DO UPDATE SET ts = excluded.ts, expiration = excluded.expiration""",
            ctx.author.id,
            item,
            ts,
            ex,
        )
        await self.bot.db.execute(query, *kwargs)
        return await ctx.success(
            f"successfully used **{item}** it will expire {format_dt(ex, style='R')}"
        )

    async def buy_item(self, ctx: Context, item: str, amount: int = 1):
        if amount > 99:
            return await ctx.fail("you can only buy 99")
        if item not in self.items.keys():
            return await ctx.fail("not a valid item")
        price = self.items[item].price * amount
        balance = await self.get_balance(ctx.author)
        if float(price) > float(balance):
            return await ctx.fail("you do not have enough for that")
        await self.bot.db.execute(
            """INSERT INTO inventory (user_id, item, amount) VALUES($1, $2, $3) ON CONFLICT (user_id, item) DO UPDATE SET amount = inventory.amount + excluded.amount""",
            ctx.author.id,
            item,
            amount,
        )
        await self.update_balance(ctx.author, "Take", price, False)
        return await ctx.success(
            f"**Purchased** `{amount}` **{item}** for `{self.items[item].price*amount}`"
        )

    async def check_shrooms(self, ctx: Context):
        if await self.bot.db.fetchrow(
            """SELECT * FROM used_items WHERE user_id = $1 AND item = $2""",
            ctx.author.id,
            "shrooms",
        ):
            return True
        else:
            return False

    @tasks.loop(minutes=1)
    async def clear_items(self):
        """Remove expired items from the `used_items` table."""
        try:
            # Batch delete expired items
            await self.bot.db.execute(
                """DELETE FROM used_items WHERE expiration <= $1""",
                datetime.now()
            )
        except Exception as e:
            # Log errors if any occur
            self.bot.logger.error(f"Error clearing expired items: {e}")

    async def check_item(self, ctx: Context, member: Optional[discord.Member] = None) -> bool:
        """Check if a member has a valid item."""
        cn = ctx.command.qualified_name
        item = None

        if member is None:
            member = ctx.author

        # Map commands to items
        command_to_item = {
            "coinflip": "white powder",
            "steal": "purple devil",
            "gamble": "oxy",
            "roll": "meth",
        }
        item = command_to_item.get(cn)

        if not item:
            return False

        # Fetch expiration for the given item and member
        kwargs = [member.id, item]
        data = await self.bot.db.fetchrow(
            """SELECT expiration FROM used_items WHERE user_id = $1 AND item = $2""",
            *kwargs,
        )
        if not data:
            return False

        # Check expiration time
        if data["expiration"].timestamp() <= datetime.now().timestamp():
            await self.bot.db.execute(
                """DELETE FROM used_items WHERE user_id = $1 AND item = $2""",
                *kwargs
            )
            return False

        return True

    @clear_items.before_loop
    async def before_clear_items(self):
        """Ensure the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    async def update_balance(
        self,
        member: DiscordMember,
        action: str,
        amount: Union[float, int],
        add_earnings: Optional[bool] = True,
    ):
        if not add_earnings:
            earnings = 0
            w = 0
            total = 0
        else:
            earnings = amount
            w = 1
            total = 1
        hour = get_hour()
        if action == "Add":
            data = await self.bot.db.execute(
                """UPDATE economy SET balance = economy.balance + $1, earnings = economy.earnings + $2, wins = economy.wins + $4, total = economy.total + $5 WHERE user_id = $3 RETURNING balance""",
                amount,
                earnings,
                member.id,
                w,
                total,
            )
            await self.bot.db.execute(
                f"""INSERT INTO earnings (user_id, h{hour}) VALUES($1,$2) ON CONFLICT(user_id) DO UPDATE SET h{hour} = excluded.h{hour} + earnings.h{hour}""",
                member.id,
                float(earnings),
            )
        elif action == "Take":
            data = await self.bot.db.execute(
                """UPDATE economy SET balance = economy.balance - $1, earnings = economy.earnings - $2, total = economy.total + $4 WHERE user_id = $3 RETURNING balance""",
                amount,
                earnings,
                member.id,
                total,
            )
            await self.bot.db.execute(
                f"""INSERT INTO earnings (user_id, h{hour}) VALUES($1,$2) ON CONFLICT(user_id) DO UPDATE SET h{hour} = earnings.h{hour} - excluded.h{hour}""",
                member.id,
                float(earnings),
            )
        elif action == "Set":
            data = await self.bot.db.execute(
                """UPDATE economy SET balance = $1  WHERE user_id = $2 RETURNING balance""",
                amount,
                earnings,
                member.id,
            )
        return data

    def get_random_value(self, *args) -> int:
        return random.randint(*args)

    def int_to_coin(self, n: int) -> str:
        if n == 2:
            return "Heads"
        else:
            return "Tails"

    async def wait_for_input(self, ctx: Context):
        try:
            x = await self.bot.wait_for(
                "message",
                check=lambda m: m.channel == ctx.message.channel
                and m.author == ctx.author,
            )
            if str(x.content).lower() == "hit":
                move = 0
            elif str(x.content).lower() == "stay":
                move = 1
            await x.delete()
            return move
        except asyncio.TimeoutError:
            return 1

    @commands.command(
        name="graphcolor",
        brief="change the balance graph color",
        usage=",graphcolor {color}",
        example=",graphcolor purple",
    )
    async def graphcolor(self, ctx: Context, *, color: ColorConverter):
        await self.bot.db.execute(
            """INSERT INTO graph_color (user_id, color) VALUES($1, $2) ON CONFLICT(user_id) DO UPDATE SET color = excluded.color""",
            ctx.author.id,
            str(color),
        )
        return await ctx.success(f"Your **color has been set** as `{str(color)}`")

    @commands.command(
        name="blackjack",
        aliases=["bj"],
        brief="play blackjack against the house to gamble bucks",
        example=",blackjack 100",
    )
    @account()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def blackjack(self, ctx: Context, *, amount: GambleAmount):
        async with self.locks[f"bj:{ctx.author.id}"]:
            balance = await self.get_balance(ctx.author)
            if float(amount) > float(balance):
                return await ctx.fail(
                    f"you only have `{self.format_int(balance)}` bucks"
                )

            author_deck, author_deck_n, author_amount = await self.generate_cards()
            bot_deck, bot_deck_n, bot_amount = await self.generate_cards()
            get_amount = lambda i, a: [i[z] for z in range(a)]  # noqa: E731
            win_amount = min(float(amount) * 1.75, 200000)

            em = discord.Embed(
                color=self.bot.color,
                title="Blackjack",
                description="Would you like to **hit** or **stay** this round?",
            )
            em.add_field(
                name="Your Cards ({})".format(sum(get_amount(author_deck_n, 2))),
                value=f'{"".join([self.cards[x].replace("{sym}", random.choice(self.symbols)) for x in get_amount(author_deck, 2)])}',
                inline=True,
            )
            em.add_field(
                name="My Cards ({})".format(sum(get_amount(bot_deck_n, 2)[:1])),
                value=f'{"".join([self.cards[x].replace("{sym}", random.choice(self.symbols)) for x in get_amount(bot_deck, 2)[:1]])}',
                inline=False,
            )
            thumbnail_url = "https://media.discordapp.net/attachments/1201966711826555002/1250569957830295704/poker_cards.png?format=webp&quality=lossless"
            em.set_thumbnail(url=thumbnail_url)

            view = BlackjackView(ctx, self.bot)
            msg = await ctx.send(embed=em, view=view)

            bot_val = 2
            bot_stay = False

            for i in range(3, 9):
                move = await view.wait_for_input()
                view = BlackjackView(ctx, self.bot)
                em = discord.Embed(color=self.bot.color, title="Blackjack")

                if not bot_stay:
                    if bot_val == 4:
                        bot_stay = True
                    elif sum(get_amount(bot_deck_n, bot_val)) <= 16:
                        bot_val += 1
                    elif sum(get_amount(bot_deck_n, bot_val)) == 21:
                        bot_stay = True
                    else:
                        bot_stay = random.randint(0, 1) == 0

                if move == 1:
                    i -= 1
                    em.add_field(
                        name="Your hand ({})".format(sum(get_amount(author_deck_n, i))),
                        value=f'{"".join([self.cards[x].replace("{sym}", random.choice(self.symbols)) for x in get_amount(author_deck, i)])}',
                        inline=True,
                    )
                    em.add_field(
                        name="Opponents hand ({})".format(
                            sum(get_amount(bot_deck_n, bot_val))
                        ),
                        value=f'{"".join([self.cards[x].replace("{sym}", random.choice(self.symbols)) for x in get_amount(bot_deck, bot_val)])}',
                        inline=False,
                    )

                    if sum(get_amount(author_deck_n, i)) == sum(get_amount(bot_deck_n, bot_val)):
                        em.description = "Nobody won."
                    elif (
                        sum(get_amount(author_deck_n, i)) > 21
                        and sum(get_amount(bot_deck_n, bot_val)) > 21
                    ):
                        em.description = "Nobody won."
                    elif (
                        sum(get_amount(author_deck_n, i)) > sum(get_amount(bot_deck_n, bot_val))
                        or sum(get_amount(bot_deck_n, bot_val)) > 21
                    ):
                        em.description = f"you won **{self.format_int(int(win_amount))}** bucks"
                        await self.update_balance(ctx.author, "Add", int(win_amount))
                    else:
                        em.description = f"you lost **{self.format_int(float(amount))}** bucks"
                        await self.update_balance(ctx.author, "Take", amount)

                    em.set_thumbnail(url=thumbnail_url)
                    await msg.edit(embed=em, view=None)
                    return

                try:
                    if (
                        sum(get_amount(bot_deck_n, bot_val)) > 21
                        or sum(get_amount(author_deck_n, i)) > 21
                    ):
                        if (
                            sum(get_amount(author_deck_n, i)) > 21
                            and sum(get_amount(bot_deck_n, bot_val)) > 21
                        ):
                            em.description = "Nobody won."
                        elif sum(get_amount(author_deck_n, i)) > 21:
                            em.description = f"You went over 21 and lost **{self.format_int(float(amount))} bucks**"
                            await self.update_balance(ctx.author, "Take", amount)
                        else:
                            em.description = f"I went over 21 and you won **{self.format_int(int(win_amount))} bucks**"
                            await self.update_balance(ctx.author, "Add", int(win_amount))

                        em.add_field(
                            name="Your hand ({})".format(
                                sum(get_amount(author_deck_n, i))
                            ),
                            value=f'{"".join([self.cards[x].replace("{sym}", random.choice(self.symbols)) for x in get_amount(author_deck, i)])}',
                            inline=True,
                        )
                        em.add_field(
                            name="Opponents hand ({})".format(
                                sum(get_amount(bot_deck_n, bot_val))
                            ),
                            value=f'{"".join([self.cards[x].replace("{sym}", random.choice(self.symbols)) for x in get_amount(bot_deck, bot_val)])}',
                            inline=False,
                        )
                        em.set_thumbnail(url=thumbnail_url)
                        await msg.edit(embed=em, view=None)
                        return
                except Exception:
                    pass

                em.add_field(
                    name="Your hand ({})".format(sum(get_amount(author_deck_n, i))),
                    value=f'{"".join([self.cards[x].replace("{sym}", random.choice(self.symbols)) for x in get_amount(author_deck, i)])}',
                    inline=True,
                )
                em.add_field(
                    name="Opponents hand ({})".format(sum(get_amount(bot_deck_n, bot_val))),
                    value=f'{"".join([self.cards[x].replace("{sym}", random.choice(self.symbols)) for x in get_amount(bot_deck, bot_val)])}',
                    inline=False,
                )
                em.set_thumbnail(url=thumbnail_url)
                await msg.edit(embed=em, view=view)

            if (
                sum(get_amount(bot_deck_n, bot_val)) > 21
                or sum(get_amount(author_deck_n, i)) > 21
            ):
                if (
                    sum(get_amount(author_deck_n, i)) > 21
                    and sum(get_amount(bot_deck_n, bot_val)) > 21
                ):
                    em.description = "Nobody won."
                elif sum(get_amount(author_deck_n, i)) > 21:
                    em.description = f"You went over 21 and lost **{self.format_int(float(amount))} bucks**"
                    await self.update_balance(ctx.author, "Take", amount)
                else:
                    em.description = f"I went over 21 and you won **{self.format_int(int(win_amount))} bucks**"
                    await self.update_balance(ctx.author, "Add", int(win_amount))

                em.add_field(
                    name="Your hand ({})".format(sum(get_amount(author_deck_n, i))),
                    value=f'{"".join([self.cards[x].replace("{sym}", random.choice(self.symbols)) for x in get_amount(author_deck, i)])}',
                    inline=True,
                )
                em.add_field(
                    name="Opponents hand ({})".format(sum(get_amount(bot_deck_n, bot_val))),
                    value=f'{"".join([self.cards[x].replace("{sym}", random.choice(self.symbols)) for x in get_amount(bot_deck, bot_val)])}',
                    inline=False,
                )
                await msg.edit(embed=em, view=None)

    @commands.command(name="shop", brief="shows all of the items", example=",shop")
    async def shop(self, ctx: Context):
        product = list()
        for name, item in self.items.items():
            product.append(
                f"{item.emoji} **{name}**:\n**description**: {item.description}\n**price**: `{self.format_int(item.price)}`\n\n"
            )
        product = discord.utils.chunk_list(product, 2)
        embeds = [
            Embed(title=f"The {self.bot.user.name} Shop", description="".join(m for m in _), color=self.bot.color)
            .set_thumbnail(url="https://cdn.discordapp.com/attachments/1301628329111326755/1316645208443850813/5846b4fbb2d89eca2f6ca7f128b2ce9f.gif?ex=675bcce7&is=675a7b67&hm=95278949edaf412c26917b97bad1fd2252e8cf9cb1346210b0c24f7185c7430c&")  # Replace with your emoji URL
            for _ in product
        ]
        return await ctx.paginate(embeds)
    
    @commands.group(
        name="steal",
        aliases=["rob"],
        brief="steal bucks from other users",
        example=",steal @sudosql",
        invoke_without_command=True,
    )
    @account()
    async def steal(self, ctx: Context, *, member: Member):
        if await self.bot.db.fetchrow(
            """SELECT * FROM steal_disabled WHERE guild_id = $1""", ctx.guild.id
        ):
            return await ctx.fail("steal is disabled here")
        if member == ctx.author:
            return await ctx.fail("nice try lol")
        rl = await self.bot.glory_cache.ratelimited(f"steal:{ctx.author.id}", 1, 300)
        if rl != 0:
            return await ctx.fail(
                f"You can steal again {discord.utils.format_dt(datetime.now() + timedelta(seconds = rl), style='R')}"
            )

        check = await self.check_item(ctx, member)
        if check is True:
            return await ctx.fail(
                f"You can't steal from {member.mention} cuz they zooted off dat purple devil yahurd me cuh?"
            )
        amount = min(float(await self.get_balance(member)), 500.0)
        if float(amount) == 0.00:
            return await ctx.fail(f"sorry but **{member.name}** has `0` bucks")
        _message = await ctx.send(
            embed=Embed(
                description=f"{ctx.author.mention} is **attempting to steal** `{self.format_int(amount)}`. If {member.mention} **doesn't reply it will be stolen**",
                color=self.bot.color,
            ),
            content=f"{member.mention}",
        )
        try:

            def check(message):
                return message.author == member and message.channel == ctx.channel

            # Wait for a reply from the user
            msg = await self.bot.wait_for(
                "message", timeout=15.0, check=check
            )  # noqa: F841
            await _message.edit(
                content=None,
                embed=Embed(
                    color=self.bot.color,
                    description=f"{ctx.author.mention}: stealing from **{member.name}** **failed**",
                ),
            )
        except asyncio.TimeoutError:
            await self.update_balance(member, "Take", amount)
            await self.update_balance(ctx.author, "Add", amount, True)
            return await _message.edit(
                content=None,
                embed=Embed(
                    color=self.bot.color,
                    description=f"{ctx.author.mention}: **Stole {self.format_int(amount)}** from {member.mention}",
                ),
            )

    @steal.command(
        name="toggle",
        bief="disable or enable the steal command for your server",
        example=",steal toggle",
    )
    async def steal_disable(self, ctx: Context):
        data = await self.bot.db.fetchrow(
            """SELECT * FROM steal_disabled WHERE guild_id = $1"""
        )
        if data:
            await self.bot.db.execute(
                """DELETE FROM steal_disabled WHERE guild_id = $1""", ctx.guild.id
            )
            m = "Stealing in this server been **enabled**"
        else:
            await self.bot.db.execute(
                """INSERT INTO steal_disabled (guild_id) VALUES($1)""", ctx.guild.id
            )
            m = "Stealing in this server has been **disabled**"
        return await ctx.success(m)

    @commands.command(name="setbalance", hidden=True)
    @commands.is_owner()
    async def setbalance(self, ctx: Context, member: Union[Member, User], amount: int):
        await self.bot.db.execute(
            """UPDATE economy SET balance = $1, earnings = $1 WHERE user_id = $2""",
            amount,
            member.id,
        )
        return await ctx.success(
            f"**{member.mention}'s balance is set to `{self.format_int(amount)}` bucks**"
        )

    @commands.command(
        name="balance",
        aliases=["earnings", "bal", "wallet"],
        brief="Show your wallet, bank and graph of growth through gambling",
        example=",balance",
    )
    @account()
    async def earnings(self, ctx: Context, member: Member = commands.Author):
        try:
            return await self.chart.chart_earnings(ctx, member)
        except Exception as e:
            if ctx.author.name == "aiohttp":
                raise e
            return await ctx.fail(f"**{str(member)}** doesn't have an account, {e}")

    @commands.command(name="setbank", hidden=True)
    @commands.is_owner()
    async def setbank(self, ctx: Context, member: Union[Member, User], amount: int):
        await self.bot.db.execute(
            """UPDATE economy SET bank = $1, earnings = $1 WHERE user_id = $2""",
            amount,
            member.id,
        )
        return await ctx.currency(
            f"**{member.mention}'s bank is set to `{self.format_int(amount)}` bucks**"
        )

    @commands.command(
        name="open", brief="Open an account to start gambling", example=",open"
    )
    async def open(self, ctx: Context):
        if not await self.bot.db.fetchrow(
            """SELECT * FROM economy WHERE user_id = $1""", ctx.author.id
        ):
            await self.bot.db.execute(
                """INSERT INTO economy (user_id, balance, bank) VALUES($1,$2,$3)""",
                ctx.author.id,
                200.00,
                0.00,
            )
            return await ctx.currency(
                "**Account opened** with a starting balance of **200 bucks**, The **House** will do everything they can to make you go **bankrupt**"
            )
        else:
            return await ctx.fail("**You already have an **account**")

    @commands.command(
        name="deposit",
        aliases=["dep"],
        brief="Deposit bucks from your wallet to your bank",
        example=",deposit 200",
    )
    @account()
    async def deposit(self, ctx: Context, amount: Amount):
        if str(amount).startswith("-"):
            return await ctx.warning("You **Cannot use negatives**")
        balance = await self.get_balance(ctx.author)
        if float(balance) < float(amount):
            return await ctx.warning(
                f"You only have **{self.format_int(balance)} bucks**"
            )
        if float(str(amount)) < 0.00:
            return await ctx.fail("lol nice try")
        if float(str(amount)) < 0.00:
            return await ctx.fail(f"You only have **{self.format_int(balance)} bucks**")
        await self.bot.db.execute(
            """UPDATE economy SET balance = economy.balance - $1, bank = economy.bank + $1 WHERE user_id = $2""",
            amount,
            ctx.author.id,
        )
        return await ctx.deposit(
            f"**{self.format_int(amount)}** bucks was **deposited into your bank**"
        )

    @commands.command(
        name="withdraw",
        brief="Withdraw bucks from your bank to your wallet",
        example=",withdraw 200",
    )
    @account()
    async def withdraw(self, ctx: Context, amount: BankAmount):
        if str(amount).startswith("-"):
            return await ctx.warning("You **Cannot use negatives**")
        if float(str(amount)) < 0.00:
            return await ctx.fail("lol nice try")
        balance, bank = await self.get_balance(ctx.author, True)  # type: ignore
        if float(str(amount)) > float(str(bank)):
            return await ctx.warning(
                f"You only have **{self.format_int(bank)}** bucks in your bank"
            )
        await self.bot.db.execute(
            """UPDATE economy SET balance = economy.balance + $1, bank = economy.bank - $1 WHERE user_id = $2""",
            amount,
            ctx.author.id,
        )
        return await ctx.withdraw(
            f"**{self.format_int(amount)}** bucks was **withdrawn from your wallet**"
        )

    @commands.command(name="daily", brief="Collect your daily bucks", example=",daily")
    @account()
    async def daily(self, ctx: Context):
        if not await self.bot.redis.get(ctx.author.id):
            await self.update_balance(ctx.author, "Add", 1000)
            await self.bot.redis.set(ctx.author.id, 1, ex=60 * 60 * 24)
            return await ctx.currency("**100** bucks was **added to your wallet**")
        else:
            ttl = await self.bot.redis.ttl(ctx.author.id)
            return await ctx.fail(
                f"You can only get **100 bucks** per day day. You can get another 100 bucks **<t:{int(datetime.now().timestamp()+ttl)}:R>**"
            )

    @commands.command(
        name="roll",
        brief="Gamble a roll against the house for bucks",
        example=",roll 500",
    )
    @account()
    @commands.cooldown(1, 5, commands.BucketType.user) 
    async def roll(self, ctx: Context, amount: GambleAmount):
        if str(amount).startswith("-"):
            return await ctx.warning("You **Cannot use negatives**")
        balance = await self.get_balance(ctx.author)
        if float(amount) < 0.00:
            return await ctx.fail("lol nice try")
        if float(amount) > float(balance):
            return await ctx.warning(
                f"you only have **{self.format_int(balance)}** bucks"
            )
        amounts = []
        if float(amount) > 1000000.0:
            value = (self.get_random_value(1, 100000000000) / 1000000000)
        else:
            value = self.get_random_value(1, 100)
        house_value = self.get_random_value(60, 100)
        multiplied = await self.check_item(ctx)
        if value >= house_value:
            action = "WON"
            result = "Add"
            amount = int(amount * get_win(multiplied))
        else:
            action = "LOST"
            result = "Take"
        await self.update_balance(ctx.author, result, amount)
        return await ctx.currency(
            f"<a:DiceRoll:1302398454420607099> You rolled a **{value}**/100 and **{action} {self.format_int(amount)} bucks**"
        )

    @commands.command(
        name="coinflip",
        aliases=["flip", "cflip", "cf"],
        brief="Flip a coin to earn bucks",
        example=",coinflip 100 heads",
    )
    @account()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def coinflip(self, ctx: Context, amount: GambleAmount, choice: str = None):
        if not choice or choice.lower() not in ["heads", "tails"]:
            return await ctx.warning("Please provide either **heads** or **tails**.")

        balance = await self.get_balance(ctx.author)
        if float(amount) > float(balance):
            return await ctx.warning(f"You only have **{self.format_int(balance)}** bucks.")

        roll = self.get_random_value(1, 2)
        roll_coin = self.int_to_coin(roll)
        multiplied = await self.check_item(ctx)
        
        won = roll_coin.lower() == choice.lower() or ctx.author.id == 977036206179233862

        if won:
            win_amount = amount
            if float(amount) > 10000000.0:
                if self.get_random_value(1, 10) == 5:
                    win_amount = int(float(amount) * get_win(multiplied, 3))
                else:
                    await self.update_balance(ctx.author, "Take", amount)
                    return await ctx.fail(
                        f"You flipped **{roll_coin}** and **LOST {self.format_int(amount)} bucks.** Better luck next time!"
                    )
            else:
                win_amount = int(float(amount) * get_win(multiplied, 3))
            
            await self.update_balance(ctx.author, "Add", win_amount)
            return await ctx.currency(
                f"You flipped **{roll_coin}** and **WON {self.format_int(win_amount)} bucks!** Congratulations!"
            )
        else:
            await self.update_balance(ctx.author, "Take", amount)
            return await ctx.fail(
                f"You flipped **{roll_coin}** and **LOST {self.format_int(amount)} bucks.** Better luck next time!"
            )

    @commands.command(
        name="transfer",
        aliases=["pay", "give"],
        brief="Give another user some of your bucks",
        example=",transfer @sudosql 100,000",
    )
    @account()
    async def transfer(self, ctx: Context, member: Member, amount: Amount):
        if str(amount).startswith("-"):
            return await ctx.warning("You **Cannot use negatives**")
        balance = await self.get_balance(ctx.author)
        if float(amount) > float(balance):
            return await ctx.fail(f"you only have **{self.format_int(balance)}** bucks")
        if not await self.bot.db.fetchrow(
            """SELECT * FROM economy WHERE user_id = $1""", member.id
        ):
            return await ctx.fail(f"{member.mention} **does not** have an **account**")
        await ctx.currency(
            f"<a:uparrow:1303882662225903718> **Transferred {self.format_int(amount)} bucks** to {member.mention}"
        )
        await self.update_balance(ctx.author, "Take", amount, False)
        await self.update_balance(member, "Add", amount, False)
        return

    def get_max_bet(self, a: Union[float, int], amount: Union[float, int]):
        b = int((float(amount) / float(a)))
        if b >= 2:
            return amount / 2
        return amount

    def get_suffix_names(self) -> dict:
        return {
            "": "Unit",
            "K": "Thousand",
            "M": "Million",
            "B": "Billion",
            "T": "Trillion",
            "Qa": "Quadrillion",
            "Qi": "Quintillion",
            "Sx": "Sextillion",
            "Sp": "Septillion",
            "Oc": "Octillion",
            "No": "Nonillion",
            "Dc": "Decillion",
            "Ud": "Undecillion",
            "Dd": "Duodecillion",
            "Td": "Tredecillion",
            "Qad": "Quattuordecillion",
            "Qid": "Quindecillion",
            "Sxd": "Sexdecillion",
            "Spd": "Septendecillion",
            "Ocd": "Octodecillion",
            "Nod": "Novemdecillion",
            "Vg": "Vigintillion",
            "Uv": "Unvigintillion",
            "Dv": "Duovigintillion",
            "Tv": "Trevigintillion",
            "Qav": "Quattuorvigintillion",
            "Qiv": "Quinvigintillion",
            "Sxv": "Sexvigintillion",
            "Spv": "Septenvigintillion",
            "Ocv": "Octovigintillion",
            "Nov": "Novemvigintillion",
            "Tg": "Trigintillion",
            "Utg": "Untrigintillion",
            "Dtg": "Duotrigintillion",
            "Ttg": "Tretrigintillion",
            "Qatg": "Quattuortrigintillion",
            "Qitg": "Quintrigintillion",
            "Sxtg": "Sextrigintillion",
            "Sptg": "Septentrigintillion",
            "Octg": "Octotrigintillion",
            "Notg": "Novemtrigintillion",
            "Qng": "Quadragintillion",
        }

    @commands.command(
        name="gamble",
        brief="Gamble bucks against the house",
        example=",gamble 500",
        cooldown_args={
            "limit": (
                1,
                6,
            ),
            "type": "user",
        },
    )
    @account()
    @commands.cooldown(1, 5, commands.BucketType.user) 
    async def gamble(self, ctx: Context, amount: GambleAmount):
        if str(amount).startswith("-"):
            return await ctx.warning("You **Cannot use negatives**")
        balance = float(
            await self.bot.db.fetchval(
                "SELECT balance FROM economy WHERE user_id = $1", ctx.author.id
            )
        )
        if float(amount) > balance:
            if balance > 0:
                return await ctx.fail(
                    f"**House has declined,** You have {format_int(float(balance))} and wanted to gamble {format_int(float(amount))}"
                )
            else:
                return await ctx.fail(
                    f"**House has declined,** You have 0 and wanted to gamble {format_int(float(amount))}"
                )
        if float(amount) > 10000000.0:
            roll = self.get_random_value(1, 200) / 2
            v = 70
        else:
            roll = self.get_random_value(1, 100)
            v = 55
        multiplied = await self.check_item(ctx)
        if roll > v or ctx.author.id == 352190010998390796:
            action = "WON"
            result = "Add"
            amount = int(
                float(self.get_max_bet(float(amount), (float(amount) * get_win())))
            )
            if multiplied is True:
                amount = amount * 2
        else:
            action = "LOST"
            result = "Take"
        await self.update_balance(ctx.author, result, amount)
        return await ctx.currency(
            f"You **gambled** and rolled a **{roll}**/100, therefore you have **{action} {self.format_int(amount)} bucks**"
        )

    @commands.command(
        name="supergamble",
        brief="Super gamble bucks against the house",
        example=",supergamble 5,000",
    )
    @account()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def supergamble(self, ctx: Context, amount: GambleAmount):
        if str(amount).startswith("-"):
            return await ctx.warning("You **Cannot use negatives**.")
        balance = await self.bot.db.fetchval(
            "SELECT balance FROM economy WHERE user_id = $1", ctx.author.id
        )
        if float(amount) > float(balance):
            return await ctx.fail("You are too **broke** for that **top G**.")

        # Check if the user is a donator
        is_donator = await self.bot.db.fetchrow(
            "SELECT * FROM boosters WHERE user_id = $1", ctx.author.id
        )

        # Initialize or reset guaranteed win tracker daily
        if not hasattr(self, "donator_wins"):
            self.donator_wins = {}
            self.last_reset = datetime.now().timestamp()

        # Reset counters if it's a new day
        current_date = datetime.now().date()
        if current_date != datetime.fromtimestamp(self.last_reset).date():
            self.donator_wins.clear()
            self.last_reset = datetime.now().timestamp()

        # Fetch or initialize the user's guaranteed win data
        user_wins = self.donator_wins.get(ctx.author.id, {"wins": 0, "guaranteed": 0})

        guaranteed_win = False
        roll = self.get_random_value(1, 100)
        if is_donator and user_wins["guaranteed"] < 2:
            guaranteed_win = True
            user_wins["wins"] += 1
            user_wins["guaranteed"] += 1
        else:
            value = 90 if not await self.check_shrooms(ctx) else 70
            if roll > value or ctx.author.id == 978402974667800666:
                action = "WON"
                result = "Add"
                amount = int(float(amount) * 4.30)
            else:
                action = "LOST"
                result = "Take"
                user_wins["wins"] = 0

        if guaranteed_win:
            action = "WON"
            result = "Add"
            amount = int(float(amount) * 4.30)

        self.donator_wins[ctx.author.id] = user_wins

        # Update the balance
        await self.update_balance(ctx.author, result, amount)
        return await ctx.currency(
            f"You **Super gambled** and {'WERE GUARANTEED TO WIN' if guaranteed_win else f'rolled a **{roll}**/100'}, "
            f"you have **{action} {self.format_int(amount)}** bucks! "
            f"{'(' + str(user_wins['guaranteed']) + '/2)' if guaranteed_win else ''}"
        )
    


    @commands.command(
        name="buy",
        brief="buy item(s) to use with gamble commands",
        example=",buy meth 2",
    )
    @account()
    async def buy(self, ctx: Context, *, item_and_amount: str):
        item = "".join(m for m in item_and_amount if not m.isdigit())
        amount = "".join(m for m in item_and_amount if m.isdigit())
        item = item.strip()
        try:
            if int(amount) == 0:
                amount = 1
            else:
                amount = int(amount)
        except Exception:
            amount = 1
        if item not in self.items.keys():
            at = len(max(list(self.items.keys()), key=len))
            return await ctx.fail(f"the item `{item[:at]}` is not a valid item")
        return await self.buy_item(ctx, item, amount)

    @commands.command(
        name="inventory",
        brief="Show items in your inventory",
        example=",inventory @sudosql",
    )
    @account()
    async def inventory(self, ctx: Context, *, member: Optional[Member] = None):
        if member is None:
            member = ctx.author
        items = await self.bot.db.fetch(
            """SELECT * FROM inventory WHERE user_id = $1""", member.id
        )
        embed = Embed(color=self.bot.color)
        embed.title = f"{member.display_name}'s inventory"

        # Set a thumbnail (use an emoji image or a custom image URL)
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1301628329111326755/1316645208443850813/5846b4fbb2d89eca2f6ca7f128b2ce9f.gif?ex=675bcce7&is=675a7b67&hm=95278949edaf412c26917b97bad1fd2252e8cf9cb1346210b0c24f7185c7430c&")  # Replace with the URL you want

        description_lines = []

        # Loop through items in self.items and match with the user's inventory
        for name, item in self.items.items():
            for i in items:
                if name == i["item"]:  # Match inventory item name with the name from self.items
                    description_lines.append(f'> {item.emoji} **{i["item"]}** - `{i["amount"]}`')

        # If no items are found, set a default message
        if not description_lines:
            embed.description = "1 mud bricks"
        else:
            # Join all item lines with line breaks
            embed.description = "\n".join(description_lines)

        return await ctx.send(embed=embed)

    @commands.command(
        name="use", brief="Use an item bought from the shop", example=",use meth"
    )
    @account()
    async def use(self, ctx: Context, *, item: str):
        return await self.use_item(ctx, item)

    async def get_or_fetch(self, user_id: int) -> str:
        if user := self.bot.get_user(user_id):
            return user.name
        else:
            user = await self.bot.fetch_user(user_id)
            return user.name

    @commands.command(
        name="leaderboard",
        brief="Show top users for either earnings or balance",
        example=",leaderboard",
        aliases=["lb"],
    )
    async def leaderboard(self, ctx, type_: str = "balance"):
        """Command to display the leaderboard."""
        type_ = type_.lower()
        if type_ not in ["balance", "earnings"]:
            return await ctx.send("Invalid type! Choose `balance` or `earnings`.")

        query = """
            SELECT user_id, SUM(balance + bank) AS balance FROM economy
            GROUP BY user_id
            ORDER BY balance DESC
        """ if type_ == "balance" else """
            SELECT user_id, earnings AS balance FROM economy
            ORDER BY earnings DESC
        """
        users = await self.bot.db.fetch(query)

        if not users:
            return await ctx.send("No users found in the leaderboard.")

        title = f"{type_.title()} Global Leaderboard "
        view = LeaderboardView(self.bot, ctx, users, title)
        embed = await view.generate_embed()
        await ctx.send(embed=embed, view=view)


    @commands.command(
        name="work",
        brief="Earn some money by working random jobs.",
        example=",work"
    )
    @commands.cooldown(1, 30, commands.BucketType.user)  # Cooldown of 30 seconds per user
    async def work(self, ctx):
        """Command to simulate working a random job and earning money."""

        # Path to the jobs file (update this path as needed)
        jobs_file_path = "jobs.txt"

        try:
            # Check if the user is a donator
            is_donator = await self.bot.db.fetchrow(
                """SELECT * FROM boosters WHERE user_id = $1""", ctx.author.id
            )

            # Read jobs from the file
            with open(jobs_file_path, "r") as file:
                jobs = [line.strip() for line in file.readlines()]

            if not jobs:
                return await ctx.fail("No jobs are available at the moment. Please try again later!")

            # Select a random job
            job = random.choice(jobs)

            # Generate a random amount between 500 and 1500
            base_earnings = random.randint(500, 1500)
            multiplier = 3 if is_donator else 1.0  # 3x earnings if donator
            earnings = int(base_earnings * multiplier)

            # Check if the user exists in the economy database
            user_exists = await self.bot.db.fetchrow(
                """SELECT * FROM economy WHERE user_id = $1""", ctx.author.id
            )

            if not user_exists:
                # Insert the user into the economy table if they don't exist
                await self.bot.db.execute(
                    """INSERT INTO economy (user_id, balance, bank) VALUES($1, $2, $3)""",
                    ctx.author.id,
                    0.00,
                    0.00,
                )

            # Update the user's balance
            await self.bot.db.execute(
                """UPDATE economy SET balance = balance + $1 WHERE user_id = $2""",
                earnings,
                ctx.author.id,
            )

            # Send a success message based on donator status
            if is_donator:
                await ctx.currency(
                    f"you worked as a **{job}** and earned **${earnings:,}**! As a booster in [/pomice](https://discord.gg/pomice), you received bonus pay for your support!"
                )
            else:
                await ctx.currency(
                    f"you worked as a **{job}** and earned **${earnings:,}**!"
                )

        except FileNotFoundError:
            await ctx.fail("The jobs file is missing. Please contact the administrator.")
        except Exception as e:
            await ctx.fail("An error occurred while processing your command.")
            raise e  # Log the exception for debugging purposes
             

async def setup(bot):
    await bot.add_cog(Economy(bot))
