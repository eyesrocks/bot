import discord
from discord.ext import commands
import datetime
import json
import os

class BotStatistics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot_start_time = datetime.datetime.utcnow()  # Track when the bot started
        self.stats_file = "bot_stats.json"  # JSON file to store statistics

        # Initialize statistics
        self.stats = {
            "servers_joined": 0,
            "servers_left": 0,
            "users_gained": 0,
            "users_lost": 0,
        }

        # Track member counts for all servers
        self.server_member_counts = {}

        # Load existing statistics from the JSON file
        self.load_stats()

    def load_stats(self):
        """Load statistics from the JSON file."""
        if os.path.exists(self.stats_file):
            with open(self.stats_file, "r") as file:
                self.stats = json.load(file)
        else:
            self.save_stats()

    def save_stats(self):
        """Save current statistics to the JSON file."""
        with open(self.stats_file, "w") as file:
            json.dump(self.stats, file)

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize member counts for all servers when the bot is ready."""
        for guild in self.bot.guilds:
            self.server_member_counts[guild.id] = guild.member_count
        print("Server member counts initialized.")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Triggered when the bot joins a new server."""
        self.stats["servers_joined"] += 1
        self.server_member_counts[guild.id] = guild.member_count
        self.stats["users_gained"] += guild.member_count
        self.save_stats()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Triggered when the bot leaves a server."""
        if guild.id in self.server_member_counts:
            self.stats["servers_left"] += 1
            self.stats["users_lost"] += self.server_member_counts[guild.id]
            del self.server_member_counts[guild.id]
        self.save_stats()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Triggered when a new member joins any server."""
        guild_id = member.guild.id
        if guild_id not in self.server_member_counts:
            # Initialize member count if not already present
            self.server_member_counts[guild_id] = member.guild.member_count
        else:
            self.server_member_counts[guild_id] += 1

        self.stats["users_gained"] += 1
        self.save_stats()

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Triggered when a member leaves any server."""
        guild_id = member.guild.id
        if guild_id not in self.server_member_counts:
            # Initialize member count if not already present
            self.server_member_counts[guild_id] = member.guild.member_count
        else:
            if self.server_member_counts[guild_id] > 0:
                self.server_member_counts[guild_id] -= 1

        self.stats["users_lost"] += 1
        self.save_stats()

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
            color=discord.Color.blue()
        )
        embed.add_field(name="Servers Joined", value=f"{self.stats['servers_joined']}", inline=True)
        embed.add_field(name="Servers Left", value=f"{self.stats['servers_left']}", inline=True)
        embed.add_field(name="Users Gained", value=f"{self.stats['users_gained']}", inline=True)
        embed.add_field(name="Users Lost", value=f"{self.stats['users_lost']}", inline=True)
        embed.add_field(name="Total Uptime", value=uptime_str, inline=False)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

        # Send embed
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(BotStatistics(bot))
