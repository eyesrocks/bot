import discord
from discord.ext import commands
import datetime

class BotStatistics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot_start_time = datetime.datetime.utcnow()  # Track when the bot started

        # Statistics tracking
        self.stats = {
            "servers_joined": 0,
            "servers_left": 0,
            "users_gained": 0,
            "users_lost": 0,  # New field to track users lost
        }

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Triggered when the bot joins a new server."""
        self.stats["servers_joined"] += 1
        self.stats["users_gained"] += guild.member_count

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Triggered when the bot leaves a server."""
        self.stats["servers_left"] += 1
        self.stats["users_lost"] += guild.member_count  # Track users lost separately

    @commands.command()
    async def botstats(self, ctx):
        """Displays bot statistics for the current day."""
        # Calculate uptime
        now = datetime.datetime.utcnow()
        uptime_duration = now - self.bot_start_time
        uptime_str = str(uptime_duration).split(".")[0]  # Format to HH:MM:SS

        # Create embed
        embed = discord.Embed(
            title="Bot Statistics",
            description="Daily statistics for the bot's activity.",
            color=self.bot.color  # Change this to your desired color
        )
        embed.add_field(name="Servers Joined", value=f"{self.stats['servers_joined']}", inline=True)
        embed.add_field(name="Servers Left", value=f"{self.stats['servers_left']}", inline=True)
        embed.add_field(name="Users Gained", value=f"{self.stats['users_gained']}", inline=True)
        embed.add_field(name="Users Lost", value=f"{self.stats['users_lost']}", inline=True)  # New field
        embed.add_field(name="Total Uptime", value=uptime_str, inline=False)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

        # Send embed
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(BotStatistics(bot))
