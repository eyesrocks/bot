from discord.ext import commands, tasks
import discord
import asyncio
from typing import Optional
from discord.ext.commands import Context
from tool.important.subclasses.command import TextChannel
from tool.important.subclasses.parser import Script
from cogs.servers import EmbedConverter
from tool.greed import Greed
from loguru import logger


class Vanity(commands.Cog):
    def __init__(self, bot: Greed):
        self.bot = bot

    @commands.group(
        name="vanity",
        example=",vanity",
        invoke_without_command=True,
    )
    @commands.has_permissions(manage_roles=True)
    async def vanity(self, ctx: Context):
        await ctx.send_help(ctx.command.qualified_name)

    @vanity.command(
        name="set",
        brief="set the channel for checking vanities",
        example=",vanity set #vanity-updates"
    )
    async def vanity_set(self, ctx, channel: TextChannel):
        await self.bot.db.execute(
            """INSERT INTO vanity (guild_id, channel_id) VALUES($1, $2) ON CONFLICT (guild_id) DO UPDATE SET channel_id = excluded.channel_id""",
            ctx.guild.id,
            channel.id,
        )
        return await ctx.success(f"**Vanity channel** set to {channel.mention}")

    @vanity.command(
        name="message",
        brief="Set the message",
        example=",vanity message {embed}{description: thanks for repping {user.mention}}"
    )
    async def vanity_message(self, ctx: Context, *, message: EmbedConverter):
        await self.bot.db.execute(
            """UPDATE vanity SET message = $2 WHERE guild_id = $1""",
            ctx.guild.id,
            message,
        )
        await ctx.success("Vanity message has been set")

    @vanity.command(
        name="view",
        aliases=["config", "cfg", "settings"],
        brief="View your vanity status settings",
    )
    @commands.has_permissions(manage_roles=True)
    async def vanity_view(self, ctx: Context):
        data = await self.bot.db.fetchrow(
            """SELECT channel_id, message FROM vanity WHERE guild_id = $1""",
            ctx.guild.id,
        )
        if not data:
            return await ctx.fail("Vanity sniping is not set up")
        desc = ""
        if channel := ctx.guild.get_channel(data["channel_id"]):
            desc += f"> **Channel:** {channel.mention}\n"
        if message := data["message"]:
            desc += f"> **Message:** `{message}`\n"
        embed = discord.Embed(
            title="Vanity Status Config", color=self.bot.color, description=desc
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener("on_guild_update")
    async def vanity_check(self, before: discord.Guild, after: discord.Guild):
        """
        Handles vanity URL updates in a guild and notifies servers with vanity monitoring enabled.
        """
        if before.vanity_url_code == after.vanity_url_code:
            return

        guilds = await self.bot.db.fetch(
            """SELECT guild_id, channel_id, message FROM vanity"""
        )

        for guild in guilds:
            await self.notify(
                guild,
                before.vanity_url_code,
                after.owner
            )

    async def notify(self, guild: dict, vanity: str, owner: Optional[discord.Member]):
        """
        Sends a notification about a dropped vanity URL to specified guild channels across all clusters.
        """
        channel_id = guild.get("channel_id")
        msg = guild.get("message")

        if not channel_id:
            return

        # Fetch the TextChannel object from the channel_id
        channel = self.bot.get_channel(channel_id)
        if not channel:  # Handle cases where the channel is invalid or deleted
            logger.error(f"Channel with ID {channel_id} not found")
            return

        vanity = str(vanity) if vanity else "unknown"

        # Replace placeholders in the message
        message = (msg or f"Vanity **{vanity}** has been dropped").replace("{vanity}", vanity)
        
        message = message.replace("{description:", "").replace("}", "")
    # Create the embed
        embed = discord.Embed(
             title="Vanity URL Changed",
            description=message,  # The main body of the embed (the message)
            color=self.bot.color,  # You can change the color of the embed
        )

        try:
        # Send the embed to the channel
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send vanity notification: {e}")

async def setup(bot):
    await bot.add_cog(Vanity(bot))
