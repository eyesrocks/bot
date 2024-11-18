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
            "users_lost": 0,  # Track users lost separately
        }

        # Track the member counts of servers the bot is in
        self.server_member_counts = {}

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize member counts when the bot starts."""
        for guild in self.bot.guilds:
            self.server_member_counts[guild.id] = guild.member_count

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Triggered when the bot joins a new server."""
        self.stats["servers_joined"] += 1
        self.stats["users_gained"] += guild.member_count
        self.server_member_counts[guild.id] = guild.member_count  # Track initial member count

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Triggered when the bot leaves a server."""
        self.stats["servers_left"] += 1
        self.stats["users_lost"] += self.server_member_counts.get(guild.id, 0)  # Use tracked member count
        self.server_member_counts.pop(guild.id, None)  # Remove from tracking

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Triggered when a new member joins a server."""
        guild_id = member.guild.id
        if guild_id in self.server_member_counts:
            self.server_member_counts[guild_id] += 1
            self.stats["users_gained"] += 1

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Triggered when a member leaves a server."""
        guild_id = member.guild.id
        if guild_id in self.server_member_counts:
            self.server_member_counts[guild_id] -= 1
            self.stats["users_lost"] += 1

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
            color=discord.Color.blue()  # Change this to your desired color
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
