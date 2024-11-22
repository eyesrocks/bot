from discord.ext.commands import Cog, command, Context, check, hybrid_group, bot_has_permissions, has_permissions
from discord import (
    AuditLogAction,
    AuditLogEntry,
    Member,
    Guild,
    User,
    Object,
    Role,
    utils,
    Embed,
    Permissions,
)
from asyncio import gather, Lock
from datetime import timedelta
from collections import defaultdict
from typing import Optional, Union
from contextlib import suppress
from loguru import logger


def trusted():
    async def predicate(ctx: Context):
        if ctx.author.id in ctx.bot.owner_ids:
            return True
        check = await ctx.bot.db.fetchval(
            "SELECT COUNT(*) FROM antinuke_admin WHERE guild_id = $1 and user_id = $2",
            ctx.guild.id,
            ctx.author.id,
        )
        if check == 0 and not ctx.author.id == ctx.guild.owner_id:
            await ctx.fail("you aren't the guild owner or an antinuke admin")
            return False
        return True

    return check(predicate)


def get_action(e: Union[AuditLogAction, AuditLogEntry]) -> str:
    if isinstance(e, AuditLogAction):
        if "webhook" in str(e).lower():
            return "webhooks"
        return (
            str(e)
            .split(".")[-1]
            .replace("create", "update")
            .replace("delete", "update")
        )

    else:
        if "webhook" in str(e.action).lower():
            return "webhooks"
        return (
            str(e.action)
            .replace("create", "update")
            .replace("delete", "update")
            .split(".")[-1]
        )


class AntiNuke(Cog):
    """A class that implements an anti-nuke system to protect a guild from malicious actions."""

    def __init__(self, bot):
        self.bot = bot
        self.locks = defaultdict(Lock)
        self.punishments = {}
        self.guilds = {}
        self.thresholds = {}
        self.modules = [
            "bot_add",
            "role_update",
            "channel_update",
            "guild_update",
            "kick",
            "ban",
            "member_prune",
            "webhooks",
        ]

    async def cog_load(self):
        await self.bot.db.execute(
            """CREATE TABLE IF NOT EXISTS antinuke_threshold (guild_id BIGINT PRIMARY KEY, bot_add BIGINT DEFAULT 0, role_update BIGINT DEFAULT 0, channel_update BIGINT DEFAULT 0, guild_update BIGINT DEFAULT 0, kick BIGINT DEFAULT 0, ban BIGINT DEFAULT 0, member_prune BIGINT DEFAULT 0, webhooks BIGINT DEFAULT 0)"""
        )
        await self.make_cache()

    def serialize(self, data: dict):
        data.pop("guild_id")
        return data

    async def make_cache(self):
        rows = await self.bot.db.fetch(
            """SELECT guild_id, bot_add, role_update, channel_update, kick, ban, guild_update, member_prune, webhooks FROM antinuke"""
        )
        self.thresholds = {
            r.guild_id: self.serialize(dict(r))
            for r in await self.bot.db.fetch("""SELECT * FROM antinuke_threshold""")
        }
        self.guilds = {r.guild_id: self.serialize(dict(r)) for r in rows}

    def make_reason(self, reason: str) -> str:
        return f"[ {self.bot.user.name} antinuke ] {reason}"

    async def get_thresholds(
        self, guild: Guild, action: AuditLogAction | str
    ) -> Optional[int]:
        if guild.id in self.guilds:
            if isinstance(action, AuditLogAction):
                _ac = get_action(action)
                threshold = await self.bot.db.fetchval(
                    f"""SELECT {_ac} FROM antinuke_threshold WHERE guild_id = $1""",
                    guild.id,
                )
                if threshold is not None:
                    return int(threshold) if int(threshold) != 1 else 0  # Check and return 0 if threshold is 1

                if _ac in self.thresholds[guild.id]:
                    thres = self.thresholds[guild.id].get(_ac)
                    return thres if thres != 1 else 0 # Check and return 0 if threshold is 1

            else:
                if action in self.thresholds[guild.id]:
                    thres = self.thresholds[guild.id].get(action, 0)
                    return thres if thres != 1 else 0 # Check and return 0 if threshold is 1
        return 0

    async def do_ban(self, guild: Guild, user: User | Member, reason: str):
        with suppress(TypeError):  # async with self.locks[guild.id]:
            if hasattr(user, "top_role"):
                if user.top_role >= guild.me.top_role:
                    raise TypeError("User's role is higher than mine")
                if user.id == guild.owner_id:
                    raise TypeError("User was the Owner")
            if await self.bot.glory_cache.ratelimited(f"punishment-{guild.id}-{user.id}", 1, 60) != 0:
                return
            await guild.ban(Object(user.id), reason=reason)
        #       logger.info(f"successfully banned {user.name} with ban entry {b}")
        return

    async def do_kick(self, guild: Guild, user: User | Member, reason: str):
        async with self.locks[guild.id]:
            if hasattr(user, "top_role"):
                if user.top_role.position >= guild.me.top_role.position:
                    return False
                if user.id == guild.owner_id:
                    return False
            if await self.bot.glory_cache.ratelimited(f"punishment-{guild.id}-{user.id}", 1, 60) != 0:
                return
            await user.kick(reason=reason)
        return

    async def do_strip(self, guild: Guild, user: Member, reason: str):
        async with self.locks[guild.id]:
            if user.top_role >= guild.me.top_role:
                return False
            if user.id == guild.owner_id:
                return False
            after_roles = [r for r in user.roles if not r.is_assignable()]
            if await self.bot.glory_cache.ratelimited(f"punishment-{guild.id}-{user.id}", 1, 60) != 0:
                return
            await user.edit(roles=after_roles, reason=reason)  # , atomic=False)
        return True

    async def do_punishment(self, guild: Guild, user: User | Member, reason: str):
        punishment = await self.bot.db.fetchval(
            """SELECT punishment FROM antinuke WHERE guild_id = $1""", guild.id
        )

        if punishment is None:
            punishment = "ban"
        if user.bot:
            await self.do_ban(guild, user, reason)
        elif punishment.lower() == "ban":
            await self.do_ban(guild, user, reason)
        elif punishment.lower() == "kick":
            await self.do_kick(guild, user, reason)
        else:
            await self.do_strip(guild, user, reason)
        return

    async def check_entry(self, guild: Guild, entry: AuditLogEntry):
        if entry.user is not None:
            try:
                threshold = await self.get_thresholds(guild, entry.action)
            except Exception:
                threshold = 0
            if await self.bot.db.fetchval(
                "SELECT user_id FROM antinuke_whitelist WHERE user_id = $1 AND guild_id = $2",
                entry.user.id,
                guild.id,
            ):
                return True
            if (
                entry.user.id == guild.owner_id
                or entry.user.id == self.bot.user.id
                or entry.user.id in self.bot.owner_ids
                or (hasattr(entry.user, "top_role") and entry.user.top_role >= guild.me.top_role)
            ):
                return True
            rl = await self.bot.glory_cache.ratelimited(
                f"antinuke-{entry.user.id}-{entry.guild.id}-{str(entry.action)}",
                threshold,
                60,
            )
            if (
                rl == 0
                and "bot" not in str(entry.action).lower()
                and "guild_update" not in str(entry.action).lower()
            ):
                return True
            else:
                logger.info(
                    f"user {entry.user.name} passed the threshold of {threshold} with {entry.action}"
                )
        return False

    def check_guild(self, guild: Guild, action: AuditLogAction | str):
        if guild.id in self.guilds:
            if isinstance(action, AuditLogAction):
                if get_action(action) in self.guilds[guild.id]:
                    return True
            else:
                if action in self.guilds[guild.id]:
                    return True
        return False

    async def get_audit(self, guild: Guild, action: AuditLogAction = None):
        try:
            if not guild.me.guild_permissions.view_audit_log:
                return None
            if action is not None:
                audit = [
                    a
                    async for a in guild.audit_logs(
                        limit=1,
                        after=utils.utcnow() - timedelta(seconds=3),
                        action=action,
                    )
                ][0]
            else:
                audit = [
                    a
                    async for a in guild.audit_logs(
                        limit=1, after=utils.utcnow() - timedelta(seconds=3)
                    )
                ][0]
            if audit.user_id == self.bot.user.id:
                if "|" in audit.reason:
                    audit.user = self.bot.get_user(
                        int(audit.reason.split(" | ")[-1].rstrip().lstrip())
                    )
                    if audit.guild.id == 1237821518940209212:
                        logger.info(
                            f"user {str(audit.user)} invoked an event for {audit.action} on {str(audit.target)}"
                        )
            return audit
        except Exception:
            return None

    async def check_role(self, role: Role) -> bool:
        if (
            role.permissions.administrator
            or role.permissions.manage_guild
            or role.permissions.kick_members
            or role.permissions.ban_members
            or role.permissions.manage_roles
            or role.permissions.manage_channels
            or role.permissions.manage_webhooks
        ):
            return True
        return False

    @Cog.listener("on_audit_log_entry_create")
    async def on_member_action(self, entry: AuditLogEntry):
        cleanup = None
        if self.check_guild(entry.guild, entry.action) is False:
            return
        if entry.action == AuditLogAction.kick:
            reason = self.make_reason("User caught kicking members")
        elif entry.action == AuditLogAction.member_prune:
            reason = self.make_reason("User caught pruning members")
        elif entry.action == AuditLogAction.ban:
            cleanup = True
            reason = self.make_reason("User caught banning members")
        else:
            return
        if entry.user_id == self.bot.user.id:
            if "|" in entry.reason:
                entry.user = self.bot.get_user(
                    int(entry.reason.split(" | ")[-1].rstrip().lstrip())
                )
        if await self.check_entry(entry.guild, entry) is not True:
            await self.do_punishment(entry.guild, entry.user, reason)
            if cleanup is not None:
                await entry.guild.unban(
                    Object(entry.target.id), reason=self.make_reason("Cleanup")
                )
            return  # await self.do_punishment(entry.guild, entry.user, reason)


    @Cog.listener("on_member_update")
    async def dangerous_role_assignment(self, before: Member, after: Member):
        if not before.guild.me.guild_permissions.view_audit_log:
            return
        guild = after.guild
        if before.roles == after.roles:
            return
        if self.check_guild(guild, "role_update") is not True:
            return
        new_roles = [
            r for r in after.roles if r not in before.roles and r.is_assignable()
        ]
        punish = False
        for r in new_roles:
            if await self.check_role(r) is not False:
                punish = True
        if punish is False:
            return
        entry = await self.get_audit(guild, AuditLogAction.member_role_update)
        if entry is None:
            return
        if after.guild.me.top_role.position > after.top_role.position:
            if await self.check_entry(guild, entry) is not True:
                for r in new_roles:
                    await after.remove_roles(
                        r, reason=self.make_reason("User given roles with permissions")
                    )
                return await self.do_punishment(
                    before.guild,
                    entry.user,
                    self.make_reason("User caught giving roles with permissions"),
                )

    @Cog.listener("on_guild_role_update")
    async def role_update(self, before: Role, after: Role):
        if not before.guild.me.guild_permissions.view_audit_log:
            return
        if await self.check_role(after) is not True:
            return
        if self.check_guild(after.guild, "role_update") is not True:
            return
        entry = await self.get_audit(after.guild, AuditLogAction.role_update)
        if entry is None:
            return
        if await self.check_entry(after.guild, entry) is not True:
            await after.edit(
                permissions=Permissions(before.permissions.value),
                reason=self.make_reason("Cleanup"),
            )
            return await self.do_punishment(
                before.guild,
                entry.user,
                self.make_reason("User caught giving roles dangerous permissions"),
            )

    @Cog.listener("on_guild_role_delete")
    async def role_delete(self, role: Role):
        if self.check_guild(role.guild, "role_update") is not True:
            return
        entry = await self.get_audit(role.guild, AuditLogAction.role_delete)
        if entry is None:
            return
        if await self.check_entry(role.guild, entry) is not True:
            await role.clone(reason=self.make_reason("Cleanup"))
            return await self.do_punishment(
                role.guild, entry.user, self.make_reason("User caught deleting roles")
            )

    @Cog.listener("on_guild_role_create")
    async def role_create(self, role: Role):
        if self.check_guild(role.guild, "role_update") is not True:
            return
        entry = await self.get_audit(role.guild, AuditLogAction.role_create)
        if entry is None:
            return
        if await self.check_entry(role.guild, entry) is not True:
            await role.delete(reason=self.make_reason("Cleanup"))
            return await self.do_punishment(
                role.guild, entry.user, self.make_reason("User caught creating roles")
            )

    @Cog.listener("on_guild_channel_create")
    async def channel_create(self, channel):
        guild = channel.guild
        if self.check_guild(guild, "channel_update") is not True:
            return
        entry = await self.get_audit(guild, AuditLogAction.channel_create)
        if entry is None:
            return
        if await self.check_entry(guild, entry) is not True:
            await channel.delete(reason=self.make_reason("Cleanup"))
            return await self.do_punishment(
                guild, entry.user, self.make_reason("User caught creating channels")
            )

    @Cog.listener("on_guild_channel_delete")
    async def channel_delete(self, channel):
        guild = channel.guild
        if self.check_guild(guild, "channel_update") is not True:
            return
        entry = await self.get_audit(guild, AuditLogAction.channel_delete)
        if entry is None:
            return
        if await self.check_entry(guild, entry) is not True:
            await channel.clone(reason=self.make_reason("Cleanup"))
            return await self.do_punishment(
                guild, entry.user, self.make_reason("User caught deleting channels")
            )

    @Cog.listener("on_guild_channel_update")
    async def channel_update(self, before, after):
        guild = after.guild
        if self.check_guild(guild, "channel_update") is not True:
            return
        entry = await self.get_audit(guild, AuditLogAction.channel_update)
        if entry is None:
            return
        if await self.check_entry(guild, entry) is not True:
            await after.edit(
                name=before.name,
                position=before.position,
                overwrites=before.overwrites,
                reason=self.make_reason("Cleanup"),
            )
            return await self.do_punishment(
                guild, entry.user, self.make_reason("User caught updating channels")
            )

    @Cog.listener("on_webhook_update")
    async def webhooks(self, channel):
        guild = channel.guild
        if self.check_guild(guild, "webhooks") is not True:
            return
        entry = await self.get_audit(guild, AuditLogAction.webhook_create)
        if entry is None:
            return
        if await self.check_entry(guild, entry) is not True:
            try:
                await entry.target.delete(reason=self.make_reason("Cleanup"))
            except Exception:
                pass
            return await self.do_punishment(
                guild, entry.user, self.make_reason("User caught creating webhooks")
            )

    @Cog.listener("on_member_join")
    async def antibot(self, member: Member):
        guild = member.guild
        if not member.bot:
            return
        if self.check_guild(guild, "bot_add") is not True:
            return
        entry = await self.get_audit(guild, AuditLogAction.bot_add)
        if entry is None:
            return
        if await self.check_entry(guild, entry) is not True:
            await member.ban(reason=self.make_reason("Cleanup"))
            return await self.do_punishment(
                guild, entry.user, self.make_reason("User caught adding bots")
            )

    @Cog.listener("on_guild_update")
    async def change_guild(self, before: Guild, after: Guild):
        if self.check_guild(after, "guild_update") is not True:
            return
        entry = await self.get_audit(after, AuditLogAction.guild_update)
        if entry is None:
            return
        if await self.check_entry(after, entry) is not True:
            if before.banner:
                await before.banner.read()
            await after.edit(
                name=before.name,
                description=before.description,
                icon=await before.icon.read() if before.icon else None,
                banner=await before.banner.read() if before.banner else None,
                splash=await before.splash.read() if before.splash else None,
                reason=self.make_reason("Cleanup"),
            )
            return await self.do_punishment(
                after, entry.user, self.make_reason("User caught updating the guild")
            )

    @hybrid_group(
        name="antinuke",
        aliases=["an"],
        brief="protect your guild from nukers",
        with_app_command=True,
        example=",antinuke",
    )
    @bot_has_permissions(administrator=True)
    async def antinuke(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command.qualified_name)

    @antinuke.command(
        name="enable",
        aliases=["e", "setup", "on"],
        brief="Enable all antinuke settings with a default threshold of 0",
        example=",antinuke enable",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_enable(self, ctx: Context):
        await self.bot.db.execute(
            """INSERT INTO antinuke (guild_id, bot_add, guild_update, channel_update, role_update, kick, ban, webhooks, member_prune, threshold) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) ON CONFLICT (guild_id) DO UPDATE SET bot_add = excluded.bot_add, guild_update = excluded.guild_update, role_update = excluded.role_update, channel_update = excluded.channel_update, webhooks = excluded.webhooks, kick = excluded.kick, ban = excluded.ban, member_prune = excluded.member_prune, threshold = excluded.threshold""",
            ctx.guild.id,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            0,
        )
        self.guilds[ctx.guild.id] = {
            "bot_add": True,
            "guild_update": True,
            "channel_update": True,
            "role_update": True,
            "kick": True,
            "ban": True,
            "webhooks": True,
            "member_prune": True,
            "threshold": 0,
        }
        return await ctx.success("antinuke is now **enabled**")

    @antinuke.command(
        name="disable",
        aliases=["off", "d", "reset"],
        brief="Disable all antinuke settings",
        example=",antinuke disable",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_disable(self, ctx: Context):
        await self.bot.db.execute(
            """DELETE FROM antinuke WHERE guild_id = $1""", ctx.guild.id
        )
        try:
            self.guilds.pop(ctx.guild.id)
        except Exception:
            pass
        return await ctx.success("antinuke is now **disabled**")

    @antinuke.command(
        name="punishment",
        aliases=["punish"],
        brief="Set a punishment a user will recieve for breaking an antinuke rule",
        example=",antinuke punishment ban",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_punishment(self, ctx: Context, punishment: str):
        if punishment.lower() not in ["ban", "kick", "strip"]:
            return await ctx.fail(
                "punishment not **recognizied**, please use one of the following `ban`, `kick`, `strip`"
            )
        await self.bot.db.execute(
            """UPDATE antinuke SET punishment = $1 WHERE guild_id = $2""",
            punishment,
            ctx.guild.id,
        )
        return await ctx.success(f"antinuke **punishment** set to `{punishment}`")

    @antinuke.command(
        name="whitelist",
        aliases=["wl"],
        brief="Whitelist or unwhitelist a user from being punished by antinuke",
        example=",antinuke whitelist @sudosql",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_whitelist(self, ctx: Context, *, user: User | Member):
        if await self.bot.db.fetchval(
            """SELECT user_id FROM antinuke_whitelist WHERE guild_id = $1 AND user_id = $2""",
            ctx.guild.id,
            user.id,
        ):
            await self.bot.db.execute(
                """DELETE FROM antinuke_whitelist WHERE guild_id = $1 AND user_id = $2""",
                ctx.guild.id,
                user.id,
            )
            return await ctx.success(f"successfully **unwhitelisted** {user.mention}")
        else:
            await self.bot.db.execute(
                """INSERT INTO antinuke_whitelist (guild_id, user_id) VALUES($1,$2) ON CONFLICT(guild_id,user_id) DO NOTHING""",
                ctx.guild.id,
                user.id,
            )
            return await ctx.success(f"successfully **whitelisted** {user.mention}")

    @antinuke.command(
        name="trust",
        aliases=["admin"],
        brief="Permit a user to use antinuke commands as an antinuke admin",
        example=",antinuke trust @sudosql",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_trust(self, ctx: Context, *, user: User | Member):
        if await self.bot.db.fetchval(
            """SELECT user_id FROM antinuke_admin WHERE guild_id = $1 AND user_id = $2""",
            ctx.guild.id,
            user.id,
        ):
            await self.bot.db.execute(
                """DELETE FROM antinuke_admin WHERE guild_id = $1 AND user_id = $2""",
                ctx.guild.id,
                user.id,
            )
            return await ctx.success(f"successfully **untrusted** {user.mention}")
        else:
            await self.bot.db.execute(
                """INSERT INTO antinuke_admin (guild_id, user_id) VALUES($1,$2) ON CONFLICT(guild_id,user_id) DO NOTHING""",
                ctx.guild.id,
                user.id,
            )
            return await ctx.success(f"successfully **trusted** {user.mention}")

    @antinuke.command(
        name="whitelisted",
        aliases=["whitelists", "wld"],
        brief="List all users that cannot be effected by antinuke",
        example=",antinuke whitelisted",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_whitelisted(self, ctx: Context):
        if rows := await self.bot.db.fetch(
            """SELECT user_id FROM antinuke_whitelist WHERE guild_id = $1""",
            ctx.guild.id,
        ):
            i = 0
            users = []
            for row in rows:
                i += 1
                users.append(f"`{i}` <@!{row.user_id}>")
            embed = Embed(title="Whitelists", color=self.bot.color)
            if len(users) > 0:
                return await self.bot.dummy_paginator(ctx, embed, users)

    @antinuke.command(
        name="trusted",
        aliases=["admins"],
        brief="List all users who are antinuke admins",
        example=",antinuke trusted",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_trusted(self, ctx: Context):
        if rows := await self.bot.db.fetch(
            """SELECT user_id FROM antinuke_admin WHERE guild_id = $1""", ctx.guild.id
        ):
            i = 0
            users = []
            for row in rows:
                i += 1
                users.append(f"`{i}` <@!{row.user_id}>")
            embed = Embed(title="Admins", color=self.bot.color)
            if len(users) > 0:
                return await self.bot.dummy_paginator(ctx, embed, users)

    @antinuke.command(
        name="threshold",
        brief="Set the threshold until antinuke bans the user",
        example=",antinuke threshold",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_threshold(self, ctx: Context, action: str, threshold: int):
        if action not in self.modules:
            return await ctx.fail("invalid action provided")
        if await self.bot.db.fetch(
            """SELECT * FROM antinuke_threshold WHERE guild_id = $1""", ctx.guild.id
        ):
            await self.bot.db.execute(
                f"""UPDATE antinuke_threshold SET {action} = $1 WHERE guild_id = $2""",
                threshold,
                ctx.guild.id,
            )
        else:
            await self.bot.db.execute(
                f"""INSERT INTO antinuke_threshold (guild_id, {action}) VALUES($1, $2)""",
                ctx.guild.id,
                threshold,
            )

        #            return await ctx.fail(f"antinuke not **setup**")
        await self.make_cache()
        return await ctx.success(
            f"antinuke **threshold** set to `{threshold}` for **{action}**"
        )

    async def get_users(self, ctx: Context, whitelisted: Optional[bool] = False):
        if whitelisted is False:
            users = [
                r.user_id
                for r in await self.bot.db.fetch(
                    """SELECT user_id FROM antinuke_admin WHERE guild_id = $1""",
                    ctx.guild.id,
                )
            ]
        else:
            users = [
                r.user_id
                for r in await self.bot.db.fetch(
                    """SELECT user_id FROM antinuke_whitelist WHERE guild_id = $1""",
                    ctx.guild.id,
                )
            ]
        _ = []
        for m in users:
            if user := self.bot.get_user(m):
                _.append(user)
        _.append(ctx.guild.owner)
        return _

    async def find_thres(self, guild: Guild, action: str):
        d = await self.get_thresholds(guild, action)
        if not d:
            d = 0
        return (action, d)

    def format_module(self, module: str):
        module = module.replace("_", " ")
        return f"**anti [{module}]({self.bot.domain}):**"

    @antinuke.command(
        name="settings",
        aliases=["config"],
        brief="List your antinuke settings along with their thresholds",
        example=",antinuke settings",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_settings(self, ctx: Context):
        data = await self.bot.db.fetchrow(
            """SELECT * FROM antinuke WHERE guild_id = $1""", ctx.guild.id
        )
        if not data:
            return await ctx.fail("antinuke not **setup**")
        try:
            thresholds = await gather(
                *[self.find_thres(ctx.guild, a) for a in self.modules]
            )
            thresholds = {a[0]: a[1] for a in thresholds}
        except Exception:
            thresholds = {a: 0 for a in self.modules}
        #        thresholds = await self.get_threshold(ctx.guild.id, {m: 0 for m in self.modules})
        embed = Embed(title="Antinuke Settings", color=self.bot.color)
        d = dict(data)
        d.pop("guild_id")
        description = f"**Punishment:** `{d.get('punishment','ban')}`\n"
        try:
            d.pop("punishment")
        except Exception:
            pass
        for k, v in d.items():
            if isinstance(v, tuple) or isinstance(k, tuple):
                logger.info(f"{k} - {v}")
                continue
            if k == "threshold":
                continue
            if k in self.modules:
                threshold = thresholds.get(k)
                #                if threshold == 0: threshold+=1
                if threshold:
                    threshold_message = f"- limit: `{threshold}`"
                else:
                    threshold_message = ""
            else:
                threshold_message = ""
            if isinstance(v, int):
                if v == 0:
                    v = self.bot.cogs["Automod"].get_state(False)
                    threshold_message = ""
                else:
                    v = self.bot.cogs["Automod"].get_state(True)
                description += f"{self.format_module(k)} {v}{threshold_message}\n"
            else:
                if k != "punishment":
                    v = self.bot.cogs["Automod"].get_state(bool(v))
                    #                    embed.add_field(
                    #                       name=k.replace("_", " "),
                    #                      value=(
                    #                         f"`enabled`{threshold_message}"
                    #                        if bool(v) == True
                    #                       else f"`disabled`{threshold_message}"
                    #                  ),
                    #                 inline=False,
                    #            )
                    description += f"{self.format_module(k)} {v}{threshold_message}\n"
        embed.description = description
        whitelisted = await self.get_users(ctx, True)
        admins = await self.get_users(ctx, False)
        if len(whitelisted) > 0:
            embed.add_field(
                name="Whitelisted",
                value=", ".join(m.mention for m in whitelisted),
                inline=True,
            )
        if len(admins) > 0:
            embed.add_field(
                name="Admins", value=", ".join(m.mention for m in admins), inline=True
            )
        return await ctx.send(embed=embed)

    @antinuke.command(
        name="botadd",
        aliases=["bot", "ba", "bot_add"],
        brief="Toggle the anti bot add of antinuke",
        example=",antinuke bot_add true",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_bot_add(self, ctx: Context, state: bool):
        return await self.antinuke_toggle(ctx, "bot_add", state)

    @antinuke.command(
        name="role",
        brief="toggle the anti role update of antinuke",
        aliases=["roles", "role_update"],
        parameters={
            "threshold": {
                "type": int,
                "required": False,
                "brief": "set the threshold until antinuke bans the user",
            }
        },
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_role_update(self, ctx: Context, state: bool):
        return await self.antinuke_toggle(ctx, "role_update", state)

    @antinuke.command(
        name="channel",
        aliases=["channels", "channel_update"],
        brief="toggle the anti channel update of antinuke",
        example=",antinuke channel true",
        parameters={
            "threshold": {
                "type": int,
                "required": False,
                "brief": "set the threshold until antinuke bans the user",
            }
        },
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_channel_update(self, ctx: Context, state: bool):
        return await self.antinuke_toggle(ctx, "channel_update", state)

    @antinuke.command(
        name="webhooks",
        brief="toggle the anti webhooks of antinuke",
        example=",antinuke webhooks true",
        parameters={
            "threshold": {
                "type": int,
                "required": False,
                "brief": "set the threshold until antinuke bans the user",
            }
        },
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_webhooks(self, ctx: Context, state: bool):
        return await self.antinuke_toggle(ctx, "webhooks", state)

    @antinuke.command(
        name="guild",
        brief="toggle the anti guild_update of antinuke",
        example=",antinuke guild true",
        parameters={
            "threshold": {
                "type": int,
                "required": False,
                "brief": "set the threshold until antinuke bans the user",
            }
        },
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_guild_update(self, ctx: Context, state: bool):
        return await self.antinuke_toggle(ctx, "guild_update", state)

    @antinuke.command(
        name="prune",
        brief="toggle the anti member_prune of antinuke",
        example=",antinuke member_prune true",
        aliases=["member_prune"],
        parameters={
            "threshold": {
                "type": int,
                "required": False,
                "brief": "set the threshold until antinuke bans the user",
            }
        },
    )
    @trusted()
    async def antinuke_member_prune(self, ctx: Context, state: bool):
        return await self.antinuke_toggle(ctx, "member_prune", state)

    @antinuke.command(
        name="kick",
        brief="toggle the anti kick of antinuke",
        example=",antinuke kick true",
        parameters={
            "threshold": {
                "type": int,
                "required": False,
                "brief": "set the threshold until antinuke bans the user",
            }
        },
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_kick(self, ctx: Context, state: bool):
        return await self.antinuke_toggle(ctx, "kick", state)

    @antinuke.command(
        name="ban",
        brief="toggle the anti ban of antinuke",
        example=",antinuke ban true",
        parameters={
            "threshold": {
                "type": int,
                "required": False,
                "brief": "set the threshold until antinuke bans the user",
            }
        },
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_ban(self, ctx: Context, state: bool):
        return await self.antinuke_toggle(ctx, "ban", state)

    async def antinuke_toggle(self, ctx: Context, module: str, state: bool):
        try:
            threshold = int(ctx.parameters.get("threshold", 0))
        except Exception:
            threshold = 0
        if module not in self.modules:
            for m in self.modules:
                if str(module).lower() in m.lower():
                    module = m
            if module not in self.modules:
                return await ctx.fail(
                    f"module not a valid feature, please do {ctx.prefix}antinuke modules to view valid modules"
                )
        if not await self.bot.db.fetchrow(
            """SELECT * FROM antinuke WHERE guild_id = $1""", ctx.guild.id
        ):
            return await ctx.fail("antinuke not **setup**")
        if module == "bot_add":
            await self.bot.db.execute(
                """UPDATE antinuke SET bot_add = $1 WHERE guild_id = $2""",
                state,
                ctx.guild.id,
            )
        elif module == "role_update":
            await self.bot.db.execute(
                """UPDATE antinuke SET role_update = $1 WHERE guild_id = $2""",
                state,
                ctx.guild.id,
            )
        elif module == "channel_update":
            await self.bot.db.execute(
                """UPDATE antinuke SET channel_update = $1 WHERE guild_id = $2""",
                state,
                ctx.guild.id,
            )
        elif module == "guild_update":
            await self.bot.db.execute(
                """UPDATE antinuke SET guild_update = $1 WHERE guild_id = $2""",
                state,
                ctx.guild.id,
            )
        elif module == "kick":
            await self.bot.db.execute(
                """UPDATE antinuke SET kick = $1 WHERE guild_id = $2""",
                state,
                ctx.guild.id,
            )
        elif module == "ban":
            await self.bot.db.execute(
                """UPDATE antinuke SET ban = $1 WHERE guild_id = $2""",
                state,
                ctx.guild.id,
            )
        elif module == "member_prune":
            await self.bot.db.execute(
                """UPDATE antinuke SET member_prune = $1 WHERE guild_id = $2""",
                state,
                ctx.guild.id,
            )
        elif module == "webhooks":
            await self.bot.db.execute(
                """UPDATE antinuke SET webhooks = $1 WHERE guild_id = $2""",
                state,
                ctx.guild.id,
            )
        else:
            return await ctx.fail("module is not recognized")
        self.guilds[ctx.guild.id][module] = state
        if state is True:
            status = "enabled"
        else:
            status = "disabled"
        if await self.bot.db.fetch(
            """SELECT * FROM antinuke_threshold WHERE guild_id = $1""", ctx.guild.id
        ):
            await self.bot.db.execute(
                f"""UPDATE antinuke_threshold SET {module} = $1 WHERE guild_id = $2""",
                threshold,
                ctx.guild.id,
            )
        else:
            await self.bot.db.execute(
                f"""INSERT INTO antinuke_threshold (guild_id, {module}) VALUES($1, $2)""",
                ctx.guild.id,
                threshold,
            )

        #            return await ctx.fail(f"antinuke not **setup**")
        await self.make_cache()
        if threshold == 0:
            thres = ""
        else:
            thres = f" with a threshold of `{threshold}`"
        await self.make_cache()
        return await ctx.success(f"successfully **{status}** `{module}`{thres}")

    @antinuke.command(
        name="modules",
        aliases=["features", "events"],
        brief="show antinuke modules",
        example=",antinuke modules",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_modules(self, ctx: Context):
        return await ctx.send(
            embed=Embed(
                title="antinuke modules",
                color=self.bot.color,
                description=", ".join(m for m in self.modules),
            )
        )

    @command(name="hardban", aliases=["hb"], brief="Hardban a user", example=",hardban @wurri")
    @trusted()
    @has_permissions(ban_members=True)
    async def hardban(self, ctx: Context, user: Union[User, Member]):
        res = await self.bot.db.fetchval(
            """SELECT user_id FROM hardban WHERE guild_id = $1 AND user_id = $2""",
            ctx.guild.id,
            user.id,
        )
        if res:
            confirm = await ctx.confirm("User is already hardbanned. Do you want to unhardban?")
            if confirm:
                await self.bot.db.execute(
                    """DELETE FROM hardban WHERE guild_id = $1 AND user_id = $2""",
                    ctx.guild.id,
                    user.id,
                )
                await ctx.guild.unban(Object(id=user.id), reason="User unhardbanned by trusted admin or owner")
                return await ctx.success(f"Successfully **unhardbanned** {user.mention}")
        else:
            await self.bot.db.execute(
                """INSERT INTO hardban (guild_id, user_id) VALUES($1, $2)""",
                ctx.guild.id,
                user.id,
            )
            await ctx.guild.ban(Object(id=user.id), reason="User hardbanned by trusted admin or owner")
            return await ctx.success(f"Successfully **hardbanned** {user.mention}")
        
    
    @Cog.listener("on_member_join")
    async def hardban_listener(self, member: Member):
        res = await self.bot.db.fetchval(
            """SELECT user_id FROM hardban WHERE guild_id = $1 AND user_id = $2""",
            member.guild.id,
            member.id,
        )
        if res:
            with suppress(Exception):
                await member.ban(reason="User hardbanned by trusted admin or owner")



async def setup(bot):
    return await bot.add_cog(AntiNuke(bot))
