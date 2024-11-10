@commands.group(
    name="timezone",
    aliases=["tz", "time"],
    invoke_without_command=True,
    brief="get the local time of a user if set",
    example=",timezone @lim",
)
async def timezone(
    self, ctx: Context, member: discord.Member | discord.User = commands.Author
):
    if data := await self.bot.db.fetchval(
        """SELECT tz FROM timezone WHERE user_id = $1""", member.id
    ):
        return await ctx.success(
            f"{member.mention}'s **current time** is <t:{await self.get_time(data)}:F>"
        )
    else:
        return await ctx.fail(
            f"{member.mention} **does not have their time set** with `timezone set`"
        )

@timezone.command(
    name="set",
    brief="set a timezone via location or timezone",
    example=",timezone set New York/et",
)
async def timezone_set(self, ctx: Context, *, timezone: str):
    try:
        data = await get_timezone(timezone)
    except Exception as e:
        raise e

    if data:
        await self.bot.db.execute(
            """INSERT INTO timezone (user_id, tz) VALUES($1, $2) ON CONFLICT(user_id) DO UPDATE SET tz = excluded.tz""",
            ctx.author.id,
            data,
        )
        current_time = await self.get_time(data)
        return await ctx.success(
            f"Set your current time to <t:{current_time}:F>"
        )
    else:
        return await ctx.fail(f"Could not find a timezone for `{timezone}`")
