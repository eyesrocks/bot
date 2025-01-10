import discord
from discord import (
    CustomActivity,
    Embed,
    Guild,
    Invite,
    Member,
    Message,
    Permissions,
    Status,
    Thread,
    User,
    Message,
    MessageType
)
import datetime
import os
import sys
import random
import asyncio
from discord.ext import commands, tasks
from tool.important import Context  # type: ignore
from jishaku.codeblocks import codeblock_converter
from discord import User, Member, Guild
from typing import Union, Optional, Literal
from loguru import logger
from tool.greed import Greed
from asyncio import TimeoutError
from discord import Webhook
import aiohttp


class Owner(commands.Cog):
    def __init__(self, bot: Greed):
        self.bot = bot
        self.guild_id = 1301617147964821524
        self.cooldowns = {}
        self.cooldown_time = 3
        self.static_message = "<@&1302845236242022440>"
        self.webhook_url = "https://discord.com/api/webhooks/1312262024750825484/fzvkQJDh5PbZshuDuoGz_VNpxwDlN5GS9O-xc0XPgI6u6__6EhDevYTXopAeBOG4-g7Z"
        self.check_subs.start()
        self.check_boosts.start()


    async def cog_load(self):
#        setattr(self.bot.connection.__events, "on_rival_information", self.bot.on_rival_information)
        if hasattr(self.bot, "connection"):
            bot = self.bot
            @bot.connection.event
            async def on_rival_information(data, id): return await bot.on_rival_information(data, id)
#        bot.connection.__events.on_rival_information = self.bot.on_rival_information
        await self.bot.db.execute(
            """
            CREATE TABLE IF NOT EXISTS donators (
                user_id BIGINT PRIMARY KEY,
                ts TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await self.bot.db.execute(
            """
            CREATE TABLE IF NOT EXISTS boosters (
                user_id BIGINT PRIMARY KEY,
                ts TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await self.bot.db.execute("""
        CREATE TABLE IF NOT EXISTS antisr_guilds (
            guild_id BIGINT PRIMARY KEY
        );
        """)

        await self.bot.db.execute("""
        CREATE TABLE IF NOT EXISTS antisr_users (
            guild_id BIGINT,
            user_id BIGINT,
            PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.bot.db.execute("""
        CREATE TABLE IF NOT EXISTS antisr_ignores (
            guild_id BIGINT,
            target_id BIGINT,
            is_role BOOLEAN,
            PRIMARY KEY (guild_id, target_id)
        );
        """)

    def cog_unload(self):
        self.check_subs.cancel()
        self.check_boosts.cancel()

    @tasks.loop(seconds=60)
    async def check_boosts(self):
        """Check and sync booster roles with boosters database."""
        try:
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                return

            booster_role = guild.get_role(1301664266868363356)
            if not booster_role:
                logger.warning("Could not find booster role")
                return

            role_members = {member.id for member in booster_role.members}
            owner_ids = set(self.bot.owner_ids)

            all_boosters = role_members.union(owner_ids)

            await self.bot.db.executemany(
                """
                INSERT INTO boosters (user_id, ts)
                VALUES ($1, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO NOTHING
                """,
                [(member_id,) for member_id in all_boosters]
            )

            await self.bot.db.execute(
                """
                DELETE FROM boosters
                WHERE user_id NOT IN (SELECT user_id FROM boosters WHERE user_id = ANY($1::bigint[]))
                """,
                list(all_boosters)
            )

            logger.info(f"Synced {len(all_boosters)} boosters to database")

        except Exception as e:
            logger.error(f"Error in booster check: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in subscription check: {e}", exc_info=True)



    @tasks.loop(seconds=60)
    async def check_subs(self):
        """Check and sync subscription roles with donator database."""
        try:
            if not (guild := self.bot.get_guild(self.guild_id)):
                return
            premium = guild.get_role(1305842894111768587)
            basic = guild.get_role(1326913774686441543)
            prime = guild.get_role(1326916553475883018)
            plus = guild.get_role(1310104324197580850)
            if not (basic and prime and premium and plus): 
                logger.warning("Could not find subscription roles")
                return

            await self.bot.db.executemany(
                """
                INSERT INTO donators (user_id, ts)
                VALUES ($1, CURRENT_TIMESTAMP) 
                ON CONFLICT (user_id) DO NOTHING
                """,
                [(owner,) for owner in self.bot.owner_ids]
            )

            role_members = set(m.id for m in basic.members + prime.members + premium.members + plus.members)
            await self.bot.db.executemany(
                """
                INSERT INTO donators (user_id, ts)
                VALUES ($1, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO NOTHING
                """,
                [(member_id,) for member_id in role_members]
            )

            logger.info(f"Synced {len(role_members)} subscribers to donator database")

        except Exception as e:
            logger.error(f"Error in subscription check: {e}", exc_info=True)


    @commands.Cog.listener("on_member_join")
    async def global_ban_event(self, member: Member):
        if global_ban := await self.bot.db.fetchval(
            """SELECT reason FROM globalbans WHERE user_id = $1""", member.id
        ):
            try:
                await member.guild.ban(member, reason=f"Global banned: {global_ban}")
            except Exception:
                pass

    async def do_ban(self, guild: Guild, member: Union[User, Member], reason: str):
        if guild.get_member(member.id):
            try:
                await guild.ban(member, reason=reason)
                return 1
            except Exception:
                return 0
        else:
            return 0


    async def do_global_ban(self, member: Union[Member, User], reason: str):
        if len(member.mutual_guilds) > 0:
            bans = await asyncio.gather(
                *[self.do_ban(guild, member, reason) for guild in member.mutual_guilds]
            )
            return sum(bans)
        else:
            return 0


    @commands.command(name = "saveemoji")
    @commands.is_owner()
    async def saveemoji(self, ctx: Context, *emojis: discord.PartialEmoji):
        for emoji in emojis:
            await emoji.save(f"assets/{emoji.name}.{'gif' if emoji.animated else 'png'}")


    @commands.group(name="donator", invoke_without_command=True)
    @commands.is_owner()
    async def donator(self, ctx: Context, *, member:Union[Member, User]):
        if await self.bot.db.fetchrow(
            """SELECT * FROM donators WHERE user_id = $1""", member.id
        ):
            await self.bot.db.execute(
                """DELETE FROM donators WHERE user_id = $1""", member.id
            )
            m = f"removed **donator permissions** from {member.mention}"
        else:
            await self.bot.db.execute(
                """INSERT INTO donators (user_id, ts) VALUES($1, $2)""",
                member.id,
                datetime.datetime.now(),
            )
            m = f"**donator permissions** has been applied to {member.mention}"
        return await ctx.success(m)


    @commands.group(name="premium", invoke_without_command=True)
    @commands.is_owner()
    async def premium(self, ctx: Context, *, member: Union[Member, User]):
        """
        Toggle premium permissions for a user. If the user already has premium, their permissions will be removed. Otherwise, premium will be applied.
        """
        # Ensure the table exists before any operation
        await self.bot.db.execute(
            """
            CREATE TABLE IF NOT EXISTS premium_users (
                user_id BIGINT PRIMARY KEY,
                ts TIMESTAMP
            )
            """
        )

        # Check if the user is already in the premium_users table
        if await self.bot.db.fetchrow("SELECT * FROM premium_users WHERE user_id = $1", member.id):
            # Remove premium permissions if they exist
            await self.bot.db.execute("DELETE FROM premium_users WHERE user_id = $1", member.id)
            message = f"Removed **premium permissions** from {member.mention}"
        else:
            # Add premium permissions if they don't exist
            await self.bot.db.execute(
                "INSERT INTO premium_users (user_id, ts) VALUES ($1, $2)",
                member.id,
                datetime.datetime.now()
            )
            message = f"**Premium permissions** have been applied to {member.mention}"

        await ctx.send(message)


    @donator.command(name="check")
    @commands.is_owner()
    async def donator_check(self, ctx: Context, member: Union[Member, User]):
        if await self.bot.db.fetchrow(
            """SELECT * FROM donators WHERE user_id = $1""", member.id
        ):
            return await ctx.success(f"{member.mention} **is a donator**")
        return await ctx.success(f"{member.mention} **is not** a donator")

    @commands.group(usage="[command]")
    async def commandstats(self, ctx: commands.Context):
        """See command usage statistics"""
        if ctx.invoked_subcommand is None:
            if args := ctx.message.content.split()[1:]:
                await self.commandstats_single(ctx, " ".join(args))
            else:
                await ctx.send_help()

    @commandstats.command(name="owncheck")
    async def commandstats_server(
        self, ctx: commands.Context, user: Optional[discord.Member] = None
    ):
        """Most used commands in this server"""
        if ctx.guild is None:
            raise commands.CommandError("Unable to get current guild")

        content = discord.Embed(
            title=f"Most used commands in {ctx.guild.name}"
            + ("" if user is None else f" by {user}")
        )
        opt = [user.id] if user is not None else []
        data = await self.bot.db.fetch(
            """
            SELECT command_name, SUM(uses) as total FROM command_usage
                WHERE command_type = 'internal'
                  AND guild_id = $1
                  AND user_id = $2
                GROUP BY command_name
                ORDER BY total DESC
            """,
            ctx.guild.id,
            *opt,
        )
        if not data:
            raise commands.CommandError("No commands have been used yet!")

        rows = []
        total = 0
        for i, (command_name, count) in enumerate(data, start=1):
            total += count
            rows.append(
                f"`{i}` **{count}** use{'' if count == 1 else 's'} : "
                f"`{ctx.prefix}{command_name}`"
            )

        if rows:
            content.set_footer(text=f"Total {total} commands")
            await self.bot.dummy_paginator(ctx, content, rows)
        else:
            content.description = "No data"
            await ctx.send(embed=content)

    @commands.command(name="globalstats")
    @commands.is_owner()
    async def commandstats_global(
        self, ctx: commands.Context, user: Optional[discord.Member] = None
    ):
        """Most used commands globally"""
        content = discord.Embed(
            title="Most used commands" + ("" if user is None else f" by {user}")
        )
        opt = [user.id] if user is not None else [u.id for u in self.bot.users]
        data = await self.bot.db.fetch(
            """
            SELECT command_name, SUM(uses) as total FROM command_usage
                WHERE command_type = 'internal'
                  AND user_id = any($1::bigint[])
                GROUP BY command_name
                ORDER BY total DESC
            """,
            opt,
        )
        if not data:
            raise commands.CommandError("No commands have been used yet!")

        rows = []
        total = 0
        for i, (command_name, count) in enumerate(data, start=1):
            total += count
            rows.append(
                f"`{i}` **{count}** use{'' if count == 1 else 's'} : "
                f"`{ctx.prefix}{command_name}`"
            )

        if rows:
            content.set_footer(text=f"Total {total} commands")
            await self.bot.dummy_paginator(ctx, content, rows)
        else:
            content.description = "No data :("
            await ctx.send(embed=content)

    async def commandstats_single(self, ctx: commands.Context, command_name):
        """Stats of a single command"""
        command = self.bot.get_command(command_name)
        if command is None:
            raise commands.CommandError(
                f"Command `{ctx.prefix}{command_name}` does not exist!"
            )

        content = discord.Embed(
            title=f":bar_chart: `{ctx.prefix}{command.qualified_name}`"
        )

        # set command name to be tuple of subcommands if this is a command group
        group = hasattr(command, "commands")
        if group:
            command_name = tuple(
                [f"{command.name} {x.name}" for x in command.commands] + [command_name]
            )
        else:
            command_name = command.qualified_name

        total_uses: int = 0
        most_used_by_user_id: Optional[int] = None
        most_used_by_user_amount: int = 0
        most_used_by_guild_amount: int = 0
        most_used_by_guild_id: Optional[int] = None

        global_use_data = await self.bot.db.fetchrow(
            """
            SELECT SUM(uses) as total, user_id, MAX(uses) FROM command_usage
                WHERE command_type = 'internal'
                  AND command_name = ANY($1)
                GROUP BY user_id
            """,
            command_name,
        )
        if global_use_data:
            total_uses, most_used_by_user_id, most_used_by_user_amount = global_use_data

        content.add_field(name="Uses", value=total_uses)

        uses_by_guild_data = await self.bot.db.fetchrow(
            """
            SELECT guild_id, MAX(uses) FROM command_usage
                WHERE command_type = 'internal'
                  AND command_name = ANY($1)
                GROUP BY guild_id
            """,
            command_name,
        )
        if uses_by_guild_data:
            most_used_by_guild_id, most_used_by_guild_amount = uses_by_guild_data

        if ctx.guild:
            uses_in_this_server = (
                await self.bot.db.fetchval(
                    """
                    SELECT SUM(uses) FROM command_usage
                        WHERE command_type = 'internal'
                          AND command_name = ANY($1)
                          AND guild_id = $2
                    GROUP BY guild_id
                    """,
                    command_name,
                    ctx.guild.id,
                )
                or 0
            )
            content.add_field(name="on this server", value=uses_in_this_server)

        # show the data in embed fields
        if most_used_by_guild_id:
            content.add_field(
                name="Server most used in",
                value=f"{self.bot.get_guild(most_used_by_guild_id)} ({most_used_by_guild_amount})",
                inline=False,
            )

        if most_used_by_user_id:
            content.add_field(
                name="Most total uses by",
                value=f"{self.bot.get_user(most_used_by_user_id)} ({most_used_by_user_amount})",
            )

        # additional data for command groups
        if group:
            content.description = "Command Group"
            subcommands_tuple = tuple(
                f"{command.name} {x.name}" for x in command.commands
            )
            subcommand_usage = await self.bot.db.fetch(
                """
                SELECT command_name, SUM(uses) FROM command_usage
                    WHERE command_type = 'internal'
                      AND command_name = ANY($1)
                GROUP BY command_name ORDER BY SUM(uses) DESC
                """,
                subcommands_tuple,
            )
            if subcommand_usage:
                content.add_field(
                    name="Subcommand usage",
                    value="\n".join(f"{s[0]} - **{s[1]}**" for s in subcommand_usage),
                    inline=False,
                )

        await ctx.send(embed=content)

    @commands.command(name="traceback", aliases=["tb", "trace"])
    @commands.is_owner()
    async def traceback(self, ctx: Context, code: str):
        data = await self.bot.db.fetchrow(
            """SELECT * FROM traceback WHERE error_code = $1""", code
        )
        if not data:
            return await ctx.fail(f"no error under code **{code}**")
        self.bot.get_guild(data.guild_id)  # type: ignore
        self.bot.get_channel(data.channel_id)  # type: ignore
        self.bot.get_user(data.user_id)  # type: ignore
        embed = discord.Embed(
            title =f"Error Code {code}", description=f"```{data.error_message}```",
            color = 0xf7cd00,
        )
        embed.add_field(name="Context", value=f"`{data.content}`", inline=False)
        return await ctx.send(embed=embed)


    @commands.command(name="restart", hidden=True)
    @commands.is_owner()
    async def restart(self, ctx):
        await ctx.success("**Restarting bot...**")
        os.execv(sys.executable, ["python"] + sys.argv)

    @commands.command(name="globalban", hidden=True)
    @commands.is_owner()
    async def globalban(self, ctx, user: Union[User, Member], *, reason: str):
        if await self.bot.db.fetch(
            """SELECT reason FROM globalbans WHERE user_id = $1""", user.id
        ):
            await self.bot.db.execute(
                """DELETE FROM globalbans WHERE user_id = $1""", user.id
            )
            return await ctx.success(
                f"successfully unglobally banned {user.mention} ({user.id})"
            )
        else:
            await self.bot.db.execute(
                """INSERT INTO globalbans (user_id, reason) VALUES ($1, $2)""",
                user.id,
                reason,
            )
            bans = await self.do_global_ban(user, reason)
            return await ctx.success(
                f"**Global banned** {user.mention} ({user.id}) from **{bans} guilds**"
            )

    @commands.command(aliases=["guilds"], hidden=True)
    @commands.is_owner()
    async def guildlist(
        self, ctx, s: Optional[Union[discord.Member, discord.User]] = None
    ):
        if s is None:
            m = self.bot.guilds
            n = self.bot.user.name
        else:
            m = s.mutual_guilds
            n = s.name
        if len(m) == 0:
            return await ctx.fail("no guilds in mutuals")
        embeds = []
        ret = []
        num = 0
        pagenum = 0

        for i in sorted(m, key=lambda x: len(x.members), reverse=True):
            num += 1
            ret.append(f"`{num}.` **{i.name}**(``{i.id}``) - {len(i.members):,}")
            pages = [p for p in discord.utils.as_chunks(ret, 10)]

        for page in pages:
            pagenum += 1
            embeds.append(
                discord.Embed(
                    color=self.bot.color,
                    title=f"{n}'s guilds",
                    description="\n".join(page),
                )
                .set_author(
                    name=ctx.author.display_name, icon_url=ctx.author.display_avatar
                )
                .set_footer(
                    text=f"Page {pagenum}/{len(pages)}({len(self.bot.guilds)} entries)"
                )
            )

        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])

        return await ctx.paginate(embeds)

    @commands.command(name="unbanowner", hidden=True)
    @commands.is_owner()
    async def unban_owner(self, ctx, guild_id: int):
        """
        Unban the owner of the bot from a guild.

        Parameters:
        - guild_id (int): The ID of the guild to unban the owner from.
        """
        guild = self.bot.get_guild(guild_id)

        if not guild:
            return await ctx.fail(
                "Invalid guild ID. Make sure the bot is in the specified guild."
            )

        owner_id = await self.bot.application_info()
        owner_id = owner_id.owner.id

        try:
            await guild.unban(discord.Object(owner_id))
            await ctx.success(
                f"Successfully unbanned the bot owner from {guild.name}"
            )
        except discord.HTTPException:
            await ctx.fail(
                "Failed to unban the bot owner. Check the bot's permissions."
            )

    @commands.command(hidden=True)
    @commands.is_owner()
    async def leaveserver(self, ctx, guild: discord.Guild):
        try:
            await guild.leave()
            await ctx.success(f"Left **{guild.name}** (`{guild.id}`)")
        except discord.Forbidden:
            return await guild.leave()
        except Exception as e:
            logger.error(e)

    @commands.command(aliases=["link"], hidden=True)
    @commands.is_owner()
    async def guildinvite(self, ctx, *, guild: discord.Guild):
        guild = self.bot.get_guild(guild.id)
        link = await random.choice(guild.text_channels).create_invite(
            max_age=0, max_uses=0
        )
        await ctx.send(link)

    @commands.command(name="eval", hidden=True)
    @commands.is_owner()
    async def _eval(self, ctx, *, argument: codeblock_converter):
        await ctx.invoke(self.bot.get_command("jishaku py"), argument=argument)

    @commands.group(name="blacklist", invoke_without_command=True, hidden=True)
    @commands.is_owner()
    async def blacklist(self, ctx):
        """Blacklist users from using the bot"""

        return await ctx.send_help()


    @blacklist.command(name="add", hidden=True)
    @commands.is_owner()
    async def blacklist_add(
        self,
        ctx, 
        user: Union[discord.User, discord.Guild, int],
        note: str = "No reason specified",
    ):
        """Blacklist someone from using the bot."""


        if isinstance(user, discord.Guild):
            name = user.name
            object_id = user.id
            object_type = "guild_id"
            await user.leave()
        elif isinstance(user, discord.User):
            name = str(user)
            object_id = user.id
            object_type = "user_id"
        elif isinstance(user, int):
            name = str(user)
            object_id = user
            object_type = "guild_id" if await self.bot.fetch_guild(object_id) else "user_id"
        else:
            return await ctx.fail("Invalid user or guild identifier.")

        try:

            await self.bot.db.execute(
                """
                INSERT INTO blacklisted (object_id, object_type, blacklist_author, reason)
                VALUES ($1, $2, $3, $4)
                """,
                object_id,
                object_type,
                ctx.author.id,
                note,
            )
        except Exception as e:

            if "unique constraint" in str(e).lower():
                await ctx.fail(f"{name} is already **blacklisted**.")
            else:
                await ctx.fail(f"An error occurred while blacklisting: {e}")
        else:
            await ctx.success(f"{name} has been **blacklisted** - {note}")


    @blacklist.command(name="remove", hidden=True)
    @commands.is_owner()
    async def blacklist_remove(
        self, ctx, user: Union[discord.User, discord.Guild, int]
    ):
        """Unblacklist a user"""
        if isinstance(user, (discord.Guild, int)):
            if isinstance(user, int): user = user
            else: user = user.id
            object_id = user
            object_type = "guild_id"
            m = object_id
        else:
            object_id = user.id
            m = user.mention
            object_type = "user_id"
        if data := await self.bot.db.fetch(  # type: ignore  # noqa: F841
            """
            SELECT object_id
            FROM blacklisted
            WHERE object_id = $1
            """,
            object_id,
        ):
            await self.bot.db.execute(
                """
                DELETE FROM blacklisted
                WHERE object_id = $1
                """,
                object_id,
            )

            return await ctx.success(
                f"{'User' if object_type == 'user_id' else 'Guild'} {m} {str(user)} has been **unblacklisted**"
            )

        else:
            return await ctx.fail(
                f"{'User' if object_type == 'user_id' else 'Guild'} {m} isn't ** blacklisted**, maybe you meant to do `, reset`?"
            )


    @commands.command(
          name="testembed",
          brief="Sends a test embed to check how it looks",
          description="A simple command to test how the embed will look.",
      )
    async def testembed(self, ctx):
          # Create the embed
          embed = discord.Embed(
              title="**Help**",  # Title of the embed
              description="<:luma_info:1302336751599222865> **support: [/pomice](https://discord.gg/pomice)**\n<a:loading:1302351366584270899> **site: [greed](http://greed.wtf)**\n\n Use **,help [command name]** or select a category from the dropdown.",
              color=0x36393f,  # Embed color (you can change it)
          )

          # Set the author for the embed (bot's username and avatar)
          avatar_url = self.bot.user.display_avatar.url  # Safe way to get the bot's avatar

          embed.set_author(
              name=self.bot.user.name,  # Bot's name
              icon_url=avatar_url  # Bot's avatar URL
          )

          # Send the embed in the current channel
          await ctx.send(embed=embed)

    @commands.command(
        name="mutuals",
        brief="Shows a list of servers you share with the bot or another user",
        example=",mutuals @lim or ,mutuals 123456789012345678",
        aliases=["mutualguilds"],
    )
    @commands.is_owner()
    async def mutuals(self, ctx, user: discord.User = None):
        # Default to the author if no user is mentioned
        user = user or ctx.author
        
        # If the user is provided by ID or mention, fetch the user object
        if isinstance(user, discord.User):
            target_user = user
        else:
            try:
                # Attempt to fetch the user by their ID (for both mentioned users and provided IDs)
                target_user = await self.bot.fetch_user(user)
            except discord.NotFound:
                await ctx.send(f"Could not find user with ID `{user}`.")
                return
            except discord.HTTPException as e:
                await ctx.send(f"An error occurred while fetching the user: {str(e)}.")
                return
        
        # Get a list of guilds the bot is in where the user is a member
        mutual_guilds = []
        for guild in self.bot.guilds:
            if target_user in guild.members:  # Check if the user is in the guild
                mutual_guilds.append(guild)

        if not mutual_guilds:
            await ctx.send(f"{target_user.mention} has no mutual servers with me.")
            return

        # Build the embed
        embed = discord.Embed(
            title=f"{target_user.name}'s Mutual Servers",
            description=f"Here are the servers {target_user.name} shares with me:",
            color=0x3498db,  # You can customize this color
        )

        # Add a field for each mutual server
        for guild in mutual_guilds:
            embed.add_field(name=guild.name, value=f"ID: {guild.id}", inline=False)

        # Send the embed
        await ctx.send(embed=embed)



    @blacklist.command(name="list", aliases=["show", "view"], hidden=True)
    @commands.is_owner()
    async def blacklist_list(self, ctx):
        """View blacklisted users"""

        if data := await self.bot.db.fetch(
            """
            SELECT *
            FROM blacklisted
            """
        ):
            num = 0
            page = 0
            users = []
            for table in data:
                if table["object_type"] == "guild_id":
                    m = table["object_id"]
                else:
                    m = (await self.bot.fetch_user(table[0])).mention
                note = table[1]
                num += 1
                users.append(f"`{num}` {m} ({note})")

            embeds = []
            users = [m for m in discord.utils.as_chunks(users, 10)]

            for lines in users:
                page += 1
                embed = discord.Embed(
                    title="Blacklist",
                    description="\n".join(lines),
                    color=self.bot.color,
                )

                embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar)

                embed.set_footer(
                    text=f"Page {page}/{len(users)} ({len(data[0])} entries)"
                )

                embeds.append(embed)
            if len(data[0]) < 10:
                await ctx.send(embed=embed)

            else:
                await ctx.paginate(embeds)

        else:
            return await ctx.fail("Nobody is **blacklisted**")




    @commands.command(hidden=True)
    @commands.is_owner()
    async def doc(self, ctx):
        bot_avatar_url = self.bot.user.avatar.url if self.bot.user.avatar.url else self.bot.user.default_avatar.url
        x = discord.Embed(title="Documentation guide", color=0x2b2d31)
        
        x.set_thumbnail(url=bot_avatar_url)

        x.add_field(name="**Important Information**", value=(
            "> [Initial Setup](https://docs.greed.bot/settings/setup)\n"
            "> [Reskin](https://docs.greed.bot/settings/Reskin)\n"
            "> [Custom Context](https://docs.greed.bot/settings/Context)"
        ), inline=False)

        x.add_field(name="**Security Setup**", value=(
            "> [Antinuke](https://docs.greed.bot/securitysetup/antinuke)\n"
            "> [Automod Filter](https://docs.greed.bot/securitysetup/automod) \n"
            "> [Fake Permissions](https://docs.greed.bot/securitysetup/Fake-Permissions)\n"
            "> [Enabling/Disabling Commands](https://docs.greed.bot/securitysetup/Command-Toggle)"
        ), inline=False)

        x.add_field(name="**Server Setup**", value=(
            "> [Autoresponders](https://docs.greed.bot/serversetup/Autoresponders)\n"
            "> [Booster Roles](https://docs.greed.bot/serversetup/Booster-Messages)\n"
            "> [Booster Messages](https://docs.greed.bot/serversetup/Booster-Roles)\n"
            "> [Lock Setup](https://docs.greed.bot/serversetup/Lock-Setup)\n"
            "> [Pagination](https://docs.greed.bot/serversetup/Pagination)\n"
            "> [Reaction Roles](https://docs.greed.bot/serversetup/Reaction-Roles)\n"
            "> [Starboard](https://docs.greed.bot/serversetup/Starboard)\n"
            "> [Vanity Roles](https://docs.greed.bot/serversetup/Vanity-Roles)\n"
            "> [VoiceMaster](https://docs.greed.bot/serversetup/VoiceMaster)\n"
            "> [Webhook Creation](https://docs.greed.bot/serversetup/Webhooks-Creation)"
        ), inline=False)

        x.add_field(name="**Socials**", value=(
            "> [Pinterest](https://docs.greed.bot/socials/Pinterest)\n"
            "> [TikTok](https://docs.greed.bot/socials/TikTok)\n"
            "> [Twitter](https://docs.greed.bot/socials/Twitter)\n"
            "> [YouTube Shorts](https://docs.greed.bot/socials/Youtube-Shorts)"
        ), inline=False)

        x.add_field(name="**Utilitys**", value=(
            "> [Embed Builder](https://docs.greed.bot/serversetup/Embeds)\n"
            "> [Variables](https://docs.greed.bot/tools/Variables)"
        ), inline=False)

        await ctx.send(embed=x)
        y = discord.Embed(
            description='<:greedinfo:1270587726080770049> When **greed** is added to a guild, **its self role** should be moved to the **top 5 roles**. Default prefix is set to `,`',
            color = 0x44ccf4
            )
        await ctx.send(embed = y)


    @commands.command(hidden=True)
    @commands.is_owner()
    async def tos(self, ctx):
        bot_avatar_url = self.bot.user.avatar.url if self.bot.user.avatar.url else self.bot.user.default_avatar.url
        x = discord.Embed(title="Terms of Service\n", color=0x2b2d31)
        
        x.set_thumbnail(url=bot_avatar_url)

        x.add_field(name="Disclaimer", value=(
            "> While this bot is provided free of charge, receiving a ban from a moderator for any of the reasons listed below will result in a **simultaneous blacklisting** from the use of Greed. "
        ), inline=False)
    
        x.add_field(name="Support Guidelines", value=(
            "> Our staff receives numerous inquiries regarding the bot's usage and support. Please be respectful, wait your turn, and you will receive the assistance you need."
        ), inline=False)

        x.add_field(name="Abuse Policy", value=(
            "> Any attempt to abuse our services will result in your server and account being blacklisted. This action will prevent you from adding the bot to any of your guilds or utilizing Greed's features."
        ), inline=False)

        y = discord.Embed(
            title="<:luma_info:1302336751599222865> Notifications & Access",
            description=(
                "> - React with <:check2:1302206610701287526> to **agree with our policy**\n> -"
                " React with <:topgg_ico_notifications:1302336130527793162> to receive **update notifications**"
            ),
            color=0x44ccf4
)

        
        await ctx.send(embed=x)
        await ctx.send(embed=y)




    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> discord.Guild:
        # Designated channel ID where the embed will be sent
        channel_id = 1302458572981932053  # Replace with your channel ID
        channel = self.bot.get_channel(channel_id)

        # Gather guild information
        owner = guild.owner
        member_count = guild.member_count
        
        # Create invite link
        invite = "No permissions to fetch invites"
        try:
            if guild.me.guild_permissions.manage_guild:
                invites = await guild.invites()
                if invites:
                    invite = invites[0].url
        except discord.Forbidden:
            pass

        # Create embed
        embed = discord.Embed(
            title=f"Joined a new server: {guild.name}",
            color=self.bot.color,
        )
        embed.add_field(name="owner", value=str(owner), inline=True)
        embed.add_field(name="member count", value=f"{guild.member_count} members")
        embed.set_thumbnail(url=self.bot.user.display_avatar)
        embed.add_field(name="invite", value=invite, inline=True)
        embed.set_footer(
                    text=f"greed joined a server | we are at {await self.bot.guild_count():,} servers"
                )

        # Send the embed to the designated channel
        if channel:
            await channel.send(embed=embed)

    

    @commands.command(
        name="updates",
        brief="Create an embed showing bot updates."
    )
    @commands.is_owner()  # Restrict to bot owner
    async def updates(self, ctx, channel: discord.TextChannel = None):
        """
        This command allows the bot owner to send an update message with an embed to a specified channel.
        The message and embed are sent via a webhook.
        """

        # Determine the target channel, defaulting to the current channel if none provided
        target_channel = channel or ctx.channel

        # Prompt the user to enter the description of the update
        await ctx.send(f"{self.static_message}\nPlease type the description of the update:")

        try:
            # Wait for the user's response
            msg = await self.bot.wait_for(
                "message",
                timeout=120.0,  # Timeout after 2 minutes
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel
            )

            # Create the embed using the user's input
            embed = discord.Embed(
                description=msg.content,
                color=self.bot.color  # Default color, can be customized
            )

            # Optionally, add a footer or timestamp
            embed.set_footer(text="Thanks for supporting the bot!")
            embed.timestamp = ctx.message.created_at

            # Create the webhook with aiohttp session
            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url(self.webhook_url, session=session)
                await webhook.send(self.static_message)
                await webhook.send(embed=embed)

            # Send confirmation to the user
            await ctx.success(f"Update successfully sent to {target_channel.mention}.")

        except TimeoutError:
            await ctx.warning("You took too long to respond. Please try the command again.")

    @commands.command(name="sync", hidden=True)
    @commands.is_owner()
    async def sync(self, ctx):
        await self.check_subs()
        await self.check_boosts()
        await self.bot.sync_all()
        await ctx.success("Synced boosters, donators, and all servers to their shards")


 

async def setup(bot):
    await bot.add_cog(Owner(bot))
