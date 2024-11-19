from discord.ext import commands, tasks
import discord
import asyncio
# from collections import defaultdict
# from typing import Optional
from discord.ext.commands import Context
from tool.important.subclasses.command import TextChannel
# from loguru import logger
# from tool.important.subclasses.parser import Script
from loguru import logger
from cogs.servers import EmbedConverter
from tool.greed import Greed
# class EmbedConverter(commands.Converter):
#     async def convert(self, ctx: Context, code: str):
#         try:
#             script = Script(code, ctx.author)
#             await script.compile()
#         except Exception as e:
#             raise e
#         return code


class Vanity(commands.Cog):
    def __init__(self, bot: Greed):
        self.bot = bot
#         self.local_addr = ("23.160.168.195", 0)
#         self.helper = discord.ExpiringDictionary()
#         self.locks = defaultdict(asyncio.Lock)

#     async def cog_load(self):
#         await self.bot.db.execute(
#             """CREATE TABLE IF NOT EXISTS vanity_roles (guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL, PRIMARY KEY(guild_id, user_id))"""
#         )
#         logger.info("Starting the check vanity loop...")
#         self.check_vanity.start()
#         logger.info("Check vanity loop started!")

#     async def cog_unload(self):
#         logger.info("Stopping the check vanity loop...")
#         self.check_vanity.stop()
#         logger.info("Check vanity loop stopped!")

#     def activity(self, member: discord.Member):
#         return member.activity.name if member.activity and member.activity.name else ""

#     async def get_vanity_role(
#         self, guild: discord.Guild, role_id: Optional[int] = None
#     ) -> Optional[discord.Role]:
#         if role_id is None:
#             role_id = await self.bot.db.fetchval(
#                 """SELECT role_id FROM vanity_status WHERE guild_id = $1""", guild.id
#             )
#         return guild.get_role(int(role_id)) if role_id else None

#     async def award_message(self, member: discord.Member):
#         async with self.locks[f"award_message:{member.guild.id}"]:
#             data = await self.bot.db.fetchrow(
#                 """SELECT channel_id, message FROM vanity_status WHERE guild_id = $1""",
#                 member.guild.id,
#             )
#             if not data or await self.helper.ratelimit(
#                 f"award_message:{member.id}:{member.guild.id}", 1, 300
#             ):
#                 return
#             channel = self.bot.get_channel(data["channel_id"])
#             if channel and data["message"]:
#                 return await self.bot.send_embed(channel, data["message"], user=member)

#     async def assign_vanity_role(self, member: discord.Member, role: discord.Role):
#         if role not in member.roles:
#             await self.bot.db.execute(
#                 """INSERT INTO vanity_roles (guild_id, user_id) VALUES($1, $2) ON CONFLICT(guild_id, user_id) DO NOTHING""",
#                 member.guild.id,
#                 member.id,
#             )
#             await member.add_roles(role, local_addr=self.local_addr)

#     async def remove_vanity_role(self, member: discord.Member, role: discord.Role):
#         await self.bot.db.execute(
#             """DELETE FROM vanity_roles WHERE guild_id = $1 AND user_id = $2""",
#             member.guild.id,
#             member.id,
#         )
#         if role in member.roles:
#             await member.remove_roles(role, local_addr=self.local_addr)

#     async def check_status(self, member: discord.Member, role: Optional[int] = None):
#         if member.guild.vanity_url_code:
#             vanity = f"/{member.guild.vanity_url_code}"
#             if member.status != discord.Status.offline and vanity in self.activity(
#                 member
#             ):
#                 role = await self.get_vanity_role(member.guild, role)
#                 if role and role not in member.roles:
#                     await self.assign_vanity_role(member, role)
#                     await self.award_message(member)
#             else:
#                 role = await self.get_vanity_role(member.guild)
#                 if role and role in member.roles and not await self.bot.db.fetchrow(
#                     """SELECT * FROM vanity_roles WHERE guild_id = $1 AND user_id = $2""",
#                     member.guild.id,
#                     member.id,
#                 ):
#                     await self.remove_vanity_role(member, role)

#     @tasks.loop(seconds=30)
#     async def check_vanity(self):
#         guilds_roles = await self.bot.db.fetch(
#             """SELECT guild_id, role_id FROM vanity_status"""
#         )
#         for guild_id, role_id in guilds_roles:
#             guild = self.bot.get_guild(int(guild_id))
#             if guild:
#                 await asyncio.gather(
#                     *[self.check_status(member, role_id) for member in guild.members]
#                 )

    @commands.group(
        name="vanity",
#         brief="Reward users with a role for repping the vanity",
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
    async def vanity_set(self, ctx, channel: discord.TextChannel):
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
        if before.vanity_url_code == after.vanity_url_code:
            return
        
        guilds = await self.bot.db.fetch(
            """SELECT guild_id, channel_id, message FROM vanity"""
        )
        
        for g in guilds:
            guild_id = g["guild_id"]
            channel_id = g["channel_id"]
            message = g["message"]
            
            guild = await self.bot.get_guild(guild_id)
            if guild is None:
                await self.bot.db.execute(
                    """DELETE FROM vanity WHERE guild_id = $1""",
                    guild_id,
                )
                logger.info("1")
                continue            
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                await self.bot.db.execute(
                    """DELETE FROM vanity WHERE guild_id = $1""",
                    guild_id,
                )
                logger.info("2")
                continue
            
            if message:
                message = message.replace("{vanity}", before.vanity_url_code or "None")
                await self.bot.send_embed(channel, message, guild=after)
            else:
                await channel.send(embed=discord.Embed(description=f"> The vanity **{before.vanity_url_code}** has been dropped"))


#     @vanity.command(
#         name="role", brief="Set the reward role", example=",vanity role @pic"
#     )
#     @commands.has_permissions(manage_roles=True)
#     async def vanity_role(self, ctx: Context, *, role: Role):
#         if not ctx.guild.vanity_url_code:
#             return await ctx.fail("Guild does not have a vanity URL")
#         role = role[0]
#         await self.bot.db.execute(
#             """INSERT INTO vanity_status (guild_id, role_id) VALUES($1, $2) ON CONFLICT (guild_id) DO UPDATE SET role_id = excluded.role_id""",
#             ctx.guild.id,
#             role.id,
#         )
#         await ctx.success(f"Users with the vanity set will receive {role.mention} role")

#     @vanity.group(
#         name="award",
#         brief="Add a message into a channel upon someone repping",
#         invoke_without_command=True,
#     )
#     @commands.has_permissions(manage_roles=True)
#     async def vanity_award(self, ctx: Context):
#         await ctx.send_help(ctx.command.qualified_name)

#     @vanity_award.command(
#         name="message",
#         brief="Set the message",
#         example=",vanity award message {embed}{description: thanks for repping {user.mention}}",
#     )
#     @commands.has_permissions(manage_roles=True)
#     async def vanity_award_message(self, ctx: Context, *, message: EmbedConverter):
#         try:
#             await self.bot.db.execute(
#                 """UPDATE vanity_status SET message = $2 WHERE guild_id = $1""",
#                 ctx.guild.id,
#                 message,
#             )
#         except Exception:
#             await ctx.fail(f"Vanity role needs to be set with `{ctx.prefix}vanity role`")
#         else:
#             await ctx.success("Vanity Award message has been set")

#     @vanity_award.command(
#         name="channel",
#         brief="Set the award message channel",
#         example="vanity award channel #text",
#     )
#     @commands.has_permissions(manage_roles=True)
#     async def vanity_award_channel(self, ctx: Context, *, channel: TextChannel):
#         try:
#             await self.bot.db.execute(
#                 """UPDATE vanity_status SET channel_id = $2 WHERE guild_id = $1""",
#                 ctx.guild.id,
#                 channel.id,
#             )
#         except Exception:
#             await ctx.fail(f"Vanity role needs to be set with `{ctx.prefix}vanity role`")
#         else:
#             await ctx.success(f"Vanity award channel set to {channel.mention}")

#     @vanity.command(
#         name="view",
#         aliases=["config", "cfg", "settings"],
#         brief="View your vanity status settings",
#     )
#     @commands.has_permissions(manage_roles=True)
#     async def vanity_view(self, ctx: Context):
#         data = await self.bot.db.fetchrow(
#             """SELECT role_id, channel_id, message FROM vanity_status WHERE guild_id = $1""",
#             ctx.guild.id,
#         )
#         if not data:
#             return await ctx.fail("Vanity status reward is not set up")
#         desc = ""
#         if role := ctx.guild.get_role(data["role_id"]):
#             desc += f"> **Role:** {role.mention}\n"
#         if channel := ctx.guild.get_channel(data["channel_id"]):
#             desc += f"> **Channel:** {channel.mention}\n"
#         if message := data["message"]:
#             desc += f"> **Message:** `{message}`\n"
#         embed = discord.Embed(
#             title="Vanity Status Config", color=self.bot.color, description=desc
#         )
#         await ctx.send(embed=embed)

#     @vanity.command(name="reset", brief="Reset the vanity reward role")
#     @commands.has_permissions(manage_roles=True)
#     async def vanity_reset(self, ctx: Context):
#         await self.bot.db.execute(
#             """DELETE FROM vanity_status WHERE guild_id = $1""", ctx.guild.id
#         )
#         await ctx.success("Vanity status configuration reset")


async def setup(bot):
    await bot.add_cog(Vanity(bot))
