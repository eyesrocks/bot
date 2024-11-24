def parse_amount(argument: str) -> float:
    suffixes = {
        'k': 1_000,
        'm': 1_000_000,
        'b': 1_000_000_000,
        't': 1_000_000_000_000,
        'qa': 1_000_000_000_000_000,
        'qi': 1_000_000_000_000_000_000,
        'sx': 1_000_000_000_000_000_000_000,
        'sp': 1_000_000_000_000_000_000_000_000,
        'oc': 1_000_000_000_000_000_000_000_000_000,
        'no': 1_000_000_000_000_000_000_000_000_000_000,
    }
    argument = argument.lower().replace(",", "")
    if argument[-1] in suffixes:
        return float(argument[:-1]) * suffixes[argument[-1]]
    for suffix in suffixes:
        if argument.endswith(suffix):
            return float(argument[:-len(suffix)]) * suffixes[suffix]
    return float(argument)

class BankAmount(commands.Converter):
    name = "BankAmount"

    async def convert(self, ctx: Context, argument: Union[int, float, str]):
        argument = parse_amount(argument)
        balance = await self.bot.db.fetchval(
            "SELECT bank FROM economy WHERE user_id = $1", ctx.author.id
        )
        if argument > balance:
            raise commands.CommandError(
                f"You only have **{format_int(balance)}** bucks in your bank"
            )
        if argument < 0:
            raise commands.CommandError("you can't withdraw an amount below 0")
        return argument

class Amount(commands.Converter):
    name = "Amount"

    async def convert(self, ctx: Context, argument: Union[int, float, str]):
        argument = parse_amount(argument)
        balance = await ctx.bot.db.fetchval(
            "SELECT balance FROM economy WHERE user_id = $1", ctx.author.id
        )
        if argument > balance:
            raise commands.CommandError(
                f"you only have **{format_int(balance)}** bucks"
            )
        if argument < 0:
            raise commands.CommandError("you can't use an amount below 0")
        return argument

class GambleAmount(commands.Converter):
    name = "GambleAmount"

    async def convert(self, ctx: Context, argument: Union[int, float, str]):
        argument = parse_amount(argument)
        balance = await ctx.bot.db.fetchval(
            "SELECT balance FROM economy WHERE user_id = $1", ctx.author.id
        )
        if argument > balance:
            raise commands.CommandError(
                f"you only have **{format_int(balance)}** bucks"
            )
        if argument < 0:
            raise commands.CommandError("you can't gamble an amount below 0")
        if argument >= MAX_GAMBLE:
            raise OverMaximum(
                f"you can only gamble a maximum of **{format_int(MAX_GAMBLE - 1.0)}** looser"
            )
        return argument
