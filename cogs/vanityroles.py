from discord.ext import commands, tasks
import discord
from typing import Optional, Union, List
from discord.ext.commands import Context
from tool.important.subclasses.command import TextChannel
from cogs.servers import EmbedConverter
from tool.eyes import Eyes
from loguru import logger
from rival_tools import ratelimit
import asyncio
from collections import defaultdict


class VanityRoles(commands.Cog):
    def __init__(self, bot: Eyes):
        self.bot = bot
        self.local_addr = "23.160.168.122"
        self.locks = defaultdict(asyncio.Lock)

    async def cog_load(self):
        await self.bot.db.execute(
            """CREATE TABLE IF NOT EXISTS vanity_roles (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                PRIMARY KEY(guild_id, user_id)
            )"""
        )
        await self.bot.db.execute(
            """CREATE TABLE IF NOT EXISTS vanity_status (
                guild_id BIGINT PRIMARY KEY,
                role_id BIGINT,
                channel_id BIGINT,
                message TEXT
            )"""
        )
        await self.bot.db.execute(
            """CREATE TABLE IF NOT EXISTS vanity (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT,
                message TEXT
            )"""
        )
        self.check_vanity.start()
        logger.info("Started the vanity check loop!")

    async def cog_unload(self):
        self.check_vanity.stop()
        logger.info("Stopped the vanity check loop!")

    @commands.group(
        name="vanityroles",
        example=";vanityroles",
        invoke_without_command=True,
    )
    @commands.has_permissions(manage_roles=True)
    async def vanityroles(self, ctx: Context):
        await ctx.send_help(ctx.command.qualified_name)

    def activity(self, member: discord.Member) -> str:
        return member.activity.name if member.activity and hasattr(member.activity, 'name') else ""

    async def get_vanity_role(self, guild: discord.Guild, role_id: Optional[int] = None) -> Optional[discord.Role]:
        if role_id is None:
            role_id = await self.bot.db.fetchval(
                """SELECT role_id FROM vanity_status WHERE guild_id = $1""", guild.id
            )
        return guild.get_role(role_id) if role_id else None

    async def award_message(self, member: discord.Member) -> None:
        lock = self.locks[f"award_message:{member.guild.id}"]
        async with lock:
            data = await self.bot.db.fetchrow(
                """SELECT channel_id, message FROM vanity_status WHERE guild_id = $1""",
                member.guild.id,
            )
            if not data or not data.get("channel_id") or not data.get("message"):
                return

            if await self.bot.glory_cache.ratelimited(f"award_message:{member.id}:{member.guild.id}", 1, 300):
                await asyncio.sleep(3)

            channel = self.bot.get_channel(data["channel_id"])
            if channel:
                await self.bot.send_embed(channel, data["message"], user=member)

    async def assign_vanity_role(self, member: discord.Member, role: discord.Role) -> None:
        if not member or not role or role in member.roles:
            return

        try:
            await self.bot.db.execute(
                """INSERT INTO vanity_roles (guild_id, user_id) VALUES ($1, $2)
                ON CONFLICT (guild_id, user_id) DO NOTHING""",
                member.guild.id,
                member.id,
            )

            if member.guild.me.top_role <= role:
                logger.error(f"Cannot assign {role.name} in {member.guild.name}: role too high.")
                return

            await member.add_roles(role, reason="Vanity URL in status")
            logger.info(f"Assigned {role.name} to {member.name} in {member.guild.name}")
        except discord.HTTPException as e:
            logger.error(f"HTTP error assigning role: {e}")
        except discord.Forbidden:
            logger.error(f"Missing permission to assign role {role.name}")
        except Exception as e:
            logger.error(f"Failed to assign vanity role: {e}")

    async def remove_vanity_role(self, member: discord.Member, role: discord.Role) -> None:
        if role not in member.roles:
            return
        try:
            await self.bot.db.execute(
                """DELETE FROM vanity_roles WHERE guild_id = $1 AND user_id = $2""",
                member.guild.id,
                member.id,
            )
            await member.remove_roles(role)
            logger.info(f"Removed vanity role {role.name} from {member.name}")
        except Exception as e:
            logger.error(f"Failed to remove vanity role: {e}")

    async def check_status(self, member: discord.Member, role_id: Optional[int] = None) -> None:
        if not member.guild.vanity_url_code:
            return

        vanity_urls = [f"discord.{d}/invite/{member.guild.vanity_url_code}" for d in ["gg", "com", "app"]]
        activity = self.activity(member)

        try:
            if member.status != discord.Status.offline and any(vanity in activity for vanity in vanity_urls):
                role = await self.get_vanity_role(member.guild, role_id)
                if role and role not in member.roles:
                    await self.assign_vanity_role(member, role)
                    await self.award_message(member)
            else:
                role = await self.get_vanity_role(member.guild, role_id)
                if role and role in member.roles:
                    has_record = await self.bot.db.fetchrow(
                        """SELECT 1 FROM vanity_roles WHERE guild_id = $1 AND user_id = $2""",
                        member.guild.id,
                        member.id,
                    )
                    if has_record:
                        await self.remove_vanity_role(member, role)
        except Exception as e:
            logger.error(f"Error checking status for {member}: {e}")

    @tasks.loop(seconds=30)
    async def check_vanity(self):
        try:
            records = await self.bot.db.fetch(
                """SELECT guild_id, role_id FROM vanity_status"""
            )
            if not records:
                return

            for record in records:
                guild = self.bot.get_guild(record["guild_id"])
                if not guild:
                    continue
                await asyncio.gather(
                    *[self.check_status(member, record["role_id"]) for member in guild.members],
                    return_exceptions=True,
                )
        except Exception as e:
            logger.error(f"Error in check_vanity loop: {e}")

    @vanityroles.command(name="role", brief="Set the reward role", example=",vanity role @role")
    async def vanity_role(self, ctx: Context, *, role: discord.Role):
        if not ctx.guild.vanity_url_code:
            return await ctx.fail("Guild does **not have a vanity**.")
        await self.bot.db.execute(
            """INSERT INTO vanity_status (guild_id, role_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET role_id = excluded.role_id""",
            ctx.guild.id,
            role.id,
        )
        return await ctx.success(f"Users with the vanity set will receive {role.mention} role.")

    @vanityroles.group(name="award", brief="Configure award messages", invoke_without_command=True)
    async def vanity_award(self, ctx: Context):
        await ctx.send_help(ctx.command.qualified_name)

    @vanity_award.command(name="message", brief="Set the award message")
    async def vanity_award_message(self, ctx: Context, *, message: EmbedConverter):
        try:
            await self.bot.db.execute(
                """UPDATE vanity_status SET message = $2 WHERE guild_id = $1""",
                ctx.guild.id,
                message,
            )
        except Exception:
            return await ctx.fail(f"**Set the vanity role first** using `{ctx.prefix}vanity role`")
        return await ctx.success("**Vanity award message** has been set.")

    @vanity_award.command(name="channel", brief="Set the award message channel")
    async def vanity_award_channel(self, ctx: Context, *, channel: TextChannel):
        try:
            await self.bot.db.execute(
                """UPDATE vanity_status SET channel_id = $2 WHERE guild_id = $1""",
                ctx.guild.id,
                channel.id,
            )
        except Exception:
            return await ctx.fail(f"**Set the vanity role first** using `{ctx.prefix}vanity role`")
        return await ctx.success(f"**Vanity award channel** set to {channel.mention}")

    @vanityroles.command(name="view", aliases=["config", "cfg", "settings"], brief="View vanity role settings")
    async def vanity_view(self, ctx: Context):
        data = await self.bot.db.fetchrow(
            """SELECT role_id, channel_id, message FROM vanity_status WHERE guild_id = $1""",
            ctx.guild.id,
        )
        if not data:
            return await ctx.fail("**Vanity status reward is not set up.**")

        desc = ""
        if role := ctx.guild.get_role(data["role_id"]):
            desc += f"> **Role:** {role.mention}\n"
        if channel := ctx.guild.get
