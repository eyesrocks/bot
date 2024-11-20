from discord.ext import commands, tasks
import discord
from discord.ext.commands import Context
from tool.important.subclasses.command import TextChannel
from cogs.servers import EmbedConverter
from tool.greed import Greed
from loguru import logger
from typing import Optional 

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
        """Main command group for vanity-related commands."""
        await ctx.send_help(ctx.command.qualified_name)

    @vanity.command(
        name="set",
        brief="Set the channel for checking vanities",
        example=",vanity set #vanity-updates"
    )
    async def vanity_set(self, ctx, channel: TextChannel):
        """Set the channel where vanity updates will be sent."""
        await self.bot.db.execute(
            """INSERT INTO vanity (guild_id, channel_id) VALUES($1, $2) 
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = excluded.channel_id""",
            ctx.guild.id,
            channel.id,
        )
        await ctx.success(f"**Vanity channel** set to {channel.mention}")

    @vanity.command(
        name="message",
        brief="Set the vanity notification message",
        example=",vanity message {embed}{description: Vanity {vanity} has changed!}"
    )
    async def vanity_message(self, ctx: Context, *, message: EmbedConverter):
        """Set a custom message template for vanity notifications."""
        await self.bot.db.execute(
            """UPDATE vanity SET message = $2 WHERE guild_id = $1""",
            ctx.guild.id,
            message,
        )
        await ctx.success("Vanity message has been set.")

    @vanity.command(
        name="view",
        aliases=["config", "cfg", "settings"],
        brief="View your vanity configuration",
    )
    @commands.has_permissions(manage_roles=True)
    async def vanity_view(self, ctx: Context):
        """View the current vanity configuration for the guild."""
        data = await self.bot.db.fetchrow(
            """SELECT channel_id, message FROM vanity WHERE guild_id = $1""",
            ctx.guild.id,
        )
        if not data:
            return await ctx.fail("Vanity tracking is not set up.")

        desc = ""
        if channel := ctx.guild.get_channel(data["channel_id"]):
            desc += f"> **Channel:** {channel.mention}\n"
        if message := data["message"]:
            desc += f"> **Message:** `{message}`\n"

        embed = discord.Embed(
            title="Vanity Tracking Configuration",
            color=self.bot.color,
            description=desc
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener("on_guild_update")
    async def vanity_check(self, before: discord.Guild, after: discord.Guild):
        """
        Handles vanity URL updates in a guild and notifies servers with vanity monitoring enabled.
        """
        if before.vanity_url_code == after.vanity_url_code:
            return

        # Fetch all guilds monitoring vanities
        guilds = await self.bot.db.fetch(
            """SELECT guild_id, channel_id, message FROM vanity"""
        )

        for guild in guilds:
            await self.notify(
                guild=guild,
                old_vanity=before.vanity_url_code,
                new_vanity=after.vanity_url_code,
                owner=after.owner
            )

    async def notify(self, guild: dict, old_vanity: Optional[str], new_vanity: Optional[str], owner: Optional[discord.Member]):
        """
        Sends a notification about a dropped or updated vanity URL to specified guild channels.
        """
        channel_id = guild.get("channel_id")
        msg_template = guild.get("message")

        if not channel_id:
            logger.warning(f"Guild {guild.get('guild_id')} has no channel ID set for vanity tracking.")
            return

        # Ensure vanity codes are strings and handle `None` values
        old_vanity = old_vanity or "unknown"
        new_vanity = new_vanity or "unknown"

        # Construct the notification message
        if msg_template:
            message = (
                msg_template.replace("{old_vanity}", old_vanity)
                .replace("{new_vanity}", new_vanity)
                .replace("{owner}", owner.mention if owner else "Unknown Owner")
            )
        else:
            message = f"Vanity URL updated:\n**Old Vanity:** `{old_vanity}`\n**New Vanity:** `{new_vanity}`"

        try:
            # Send the notification via IPC or directly
            await self.bot.ipc.roundtrip(
                "send_message",
                channel_id=channel_id,
                message=message,
                user_id=owner.id if owner else None
            )
        except Exception as e:
            logger.error(f"Failed to send vanity notification for guild {guild.get('guild_id')}: {e}")


async def setup(bot):
    """Set up the Vanity cog."""
    await bot.add_cog(Vanity(bot))
