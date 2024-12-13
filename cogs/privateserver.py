import discord
from discord.ext import commands
from discord.ext.commands import Cog

class Private(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_db())

    async def setup_db(self):
        """Sets up the database table if it doesn't exist."""
        await self.bot.db.execute('''
            CREATE TABLE IF NOT EXISTS whitelist (
                user_id BIGINT PRIMARY KEY
            )
        ''')

        await self.bot.db.execute('''
            CREATE TABLE IF NOT EXISTS server_settings (
                guild_id BIGINT PRIMARY KEY,
                private_server_enabled BOOLEAN DEFAULT FALSE
            )
        ''')


    async def check_donator(self, ctx):
        """Check if the user is a donator by checking the database."""
        try:
            # Query to check if the user is a donator
            is_donator = await self.bot.db.fetchrow(
                """SELECT * FROM donators WHERE user_id = $1""", ctx.author.id
            )
            if not is_donator:
                return False
            return True
        except Exception as e:
            await ctx.send(f"An error occurred while checking donator status: {e}")
            return False


    @commands.group(invoke_without_command=True)
    async def privateserver(self, ctx):
        """Base command for the private server group."""
        await ctx.success("Please specify a subcommand like `add`, `remove`, or `enable`/`disable`.")

    @privateserver.command(
        name="add",
        brief="whitelist a user to your private server",
        example=",privateserver add (userid)",
    )
    @commands.has_permissions(manage_guild=True)
    async def add(self, ctx, user: discord.User):
        """Adds a user to the whitelist."""

        if not await self.check_donator(ctx):
            return await ctx.fail(
                "You are not boosting [/pomice](https://discord.gg/pomice). Boost this server to use this command."
            )

        if ctx.author.guild_permissions.administrator:
            await self.bot.db.execute('''
                INSERT INTO whitelist (user_id) VALUES ($1)
                ON CONFLICT (user_id) DO NOTHING
            ''', user.id)
            await ctx.success(f"{user.name} has been added to the whitelist.")
        else:
            await ctx.fail("You do not have permission to add users to the whitelist.")

    @privateserver.command(
        name="remove",
        brief="remove a user from being whitelisted",
        example=",privateserver remove (userid)",
    )
    @commands.has_permissions(manage_guild=True)
    async def remove(self, ctx, user: discord.User):
        """Removes a user from the whitelist."""

        if not await self.check_donator(ctx):
            return await ctx.fail(
                "You are not boosting [/pomice](https://discord.gg/pomice). Boost this server to use this command."
            )
        
        if ctx.author.guild_permissions.administrator:
            await self.bot.db.execute('''
                DELETE FROM whitelist WHERE user_id = $1
            ''', user.id)
            await ctx.success(f"{user.name} has been removed from the whitelist.")
        else:
            await ctx.warning("You do not have permission to remove users from the whitelist.")

    @privateserver.command(
        name="enable",
        brief="enable the private server feature",
        example=",privateserver enable",
    )
    @commands.has_permissions(manage_guild=True)
    async def enable(self, ctx):
        """Enables the private server feature (whitelist) for this server."""

        if not await self.check_donator(ctx):
            return await ctx.fail(
                "You are not boosting [/pomice](https://discord.gg/pomice). Boost this server to use this command."
            )

        guild_id = ctx.guild.id
        await self.bot.db.execute('''
            INSERT INTO server_settings (guild_id, private_server_enabled)
            VALUES ($1, TRUE)
            ON CONFLICT (guild_id) DO UPDATE SET private_server_enabled = TRUE
        ''', guild_id)
        await ctx.success("Private server feature has been enabled.")

    @privateserver.command(
        name="disable",
        brief="disable the private server feature",
        example=",privateserver disable",
    )
    @commands.has_permissions(manage_guild=True)
    async def disable(self, ctx):
        """Disables the private server feature (whitelist) for this server."""

        if not await self.check_donator(ctx):
            return await ctx.fail(
                "You are not boosting [/pomice](https://discord.gg/pomice). Boost this server to use this command."
            )

        guild_id = ctx.guild.id
        await self.bot.db.execute('''
            UPDATE server_settings SET private_server_enabled = FALSE WHERE guild_id = $1
        ''', guild_id)
        await ctx.success("Private server feature has been disabled.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Checks if a new member is whitelisted and kicks them if not, based on server setting."""
        guild_id = member.guild.id
        result = await self.bot.db.fetchrow('''
            SELECT private_server_enabled FROM server_settings WHERE guild_id = $1
        ''', guild_id)
        if not result or not result.private_server_enabled:
            return
        whitelist_check = await self.bot.db.fetchrow('''
            SELECT user_id FROM whitelist WHERE user_id = $1
        ''', member.id)
        
        if whitelist_check is None:
            await member.kick(reason="Not whitelisted in this private server.")
        
        
async def setup(bot):
    await bot.add_cog(Private(bot))

