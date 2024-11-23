import discord
import datetime
import os
import sys
import random
import asyncio
from discord.ext import commands
from tool.important import Context  # type: ignore
from jishaku.codeblocks import codeblock_converter
from discord import User, Member, Guild
from typing import Union
from typing import Optional
from loguru import logger


class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_id = 1301617147964821524
        self.cooldowns = {}
        self.cooldown_time = 3

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

    @commands.group(name="donator", invoke_without_command=True)
    @commands.is_owner()
    async def donator(self, ctx: Context, *, member: Member | User):
        if await self.bot.db.fetchrow(
            """SELECT * FROM donators WHERE user_id = $1""", member.id
        ):
            await self.bot.db.execute(
                """DELETE FROM donators WHERE user_id = $1""", member.id
            )
            m = f"removed **donator** from {member.mention}"
        else:
            await self.bot.db.execute(
                """INSERT INTO donators (user_id, ts) VALUES($1, $2)""",
                member.id,
                datetime.datetime.now(),
            )
            m = f"**Donator permissions** has been applied to {member.mention}"
        return await ctx.success(m)

    @donator.command(name="check")
    @commands.is_owner()
    async def donator_check(self, ctx: Context, member: Member | User):
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

    @commands.command(name="reset", description="reset term agreement process")
    async def reset(self, ctx: Context, *, member: discord.Member = None):
        if member:
            if ctx.author.id not in self.bot.owner_ids:
                return
            await self.bot.db.execute(
                """DELETE FROM terms_agreement WHERE user_id = $1""", member.id
            )
            return await ctx.success(
                f" {member.mention}'s **Agreement policy** has been **reset**"
            )
        await self.bot.db.execute(
            "DELETE FROM terms_agreement WHERE user_id = $1", ctx.author.id
        )
        return await ctx.success("**Agreement policy** has been **reset**")

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
        await guild.leave()
        await ctx.success(f"Left **{guild.name}** (`{guild.id}`)")

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

    @commands.command(hidden=True)
    @commands.is_owner()
    async def sql(self, ctx, *, query: str):
        from jishaku.codeblocks import codeblock_converter as cc

        parts = query.split(" | ")
        query = parts[0]
        if len(parts) == 2:
            parts[1].split()  # type: ignore

        if "select" in query.lower():
            method = "fetch"
        else:
            method = "execute"
        await ctx.invoke(
            self.bot.get_command("eval"),
            argument=cc(f"""await bot.db.{method}(f'{query.split(' || ')[0]}')"""),
        )

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
              description="<:luma_info:1302336751599222865> **support: [/pomice](https://discord.gg/pomice)**\n<a:loading:1302351366584270899> **site: [greed](http://greed.my)**\n\n Use **,help [command name]** or select a category from the dropdown.",
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

    @commands.hybrid_command(name="changepfp", aliases=["setpfp"], hidden=True)
    @commands.is_owner()
    async def changepfp(self, ctx, url):
        """Change the bot's pfp"""

        session = await self.bot.session.get(url)
        await self.bot.user.edit(avatar=await session.read())
        await ctx.success(f"Changed the bot's pfp to **[image]({url})**")



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
        invite = None
        invites = await guild.invites()
        if invites:
            invite = invites[0].url  # Take the first invite link
        else:
            invite = "No invites available."

        # Create embed
        embed = discord.Embed(
            title=f"Joined a new server: {guild.name}",
            color=discord.Color.blue(),
        )
        embed.add_field(name="owner", value=str(owner), inline=True)
        embed.add_field(name="users", value=member_count, inline=True)
        embed.add_field(name="invite", value=invite, inline=True)

        # Send the embed to the designated channel
        if channel:
            await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Owner(bot))
