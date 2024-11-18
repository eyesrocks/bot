from collections import defaultdict
from contextlib import suppress
from datetime import timedelta
from typing import Optional, Union

from asyncio import Lock, gather
from discord import (
    AuditLogAction,
    AuditLogEntry,
    Embed,
    Guild,
    Member,
    Object,
    Permissions,
    Role,
    User,
    utils,
)
from discord.ext.commands import (
    Cog,
    Context,
    check,
    command,
    has_permissions,
    hybrid_group,
    bot_has_permissions,
)
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
        if check == 0 and ctx.author.id != ctx.guild.owner_id:
            await ctx.fail("you aren't the guild owner or an antinuke admin")
            return False
        return True

    return check(predicate)


def get_action(e: Union[AuditLogAction, AuditLogEntry]) -> str:
    action_str = str(e).lower() if isinstance(e, AuditLogAction) else str(e.action).lower()
    if "webhook" in action_str:
        return "webhooks"
    return action_str.replace("create", "update").replace("delete", "update").split(".")[-1]


class AntiNuke(Cog):
    """A class that implements an anti-nuke system to protect a guild from malicious actions."""

    def __init__(self, bot):
        self.bot = bot
        self.locks = defaultdict(Lock)
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
            """
            CREATE TABLE IF NOT EXISTS antinuke_threshold (
                guild_id BIGINT PRIMARY KEY,
                bot_add BIGINT DEFAULT 0,
                role_update BIGINT DEFAULT 0,
                channel_update BIGINT DEFAULT 0,
                guild_update BIGINT DEFAULT 0,
                kick BIGINT DEFAULT 0,
                ban BIGINT DEFAULT 0,
                member_prune BIGINT DEFAULT 0,
                webhooks BIGINT DEFAULT 0
            )
            """
        )
        await self.make_cache()

    def serialize(self, data: dict):
        data.pop("guild_id", None)
        return data

    async def make_cache(self):
        rows = await self.bot.db.fetch(
            "SELECT guild_id, bot_add, role_update, channel_update, kick, ban, guild_update, member_prune, webhooks FROM antinuke"
        )
        thresholds = await self.bot.db.fetch("SELECT * FROM antinuke_threshold")
        self.thresholds = {
            r.guild_id: self.serialize(dict(r)) for r in thresholds
        }
        self.guilds = {r.guild_id: self.serialize(dict(r)) for r in rows}

    def make_reason(self, reason: str) -> str:
        return f"[ {self.bot.user.name} antinuke ] {reason}"

    async def get_thresholds(
        self, guild: Guild, action: Union[AuditLogAction, str]
    ) -> Optional[int]:
        if guild.id not in self.guilds:
            return 0

        action_key = get_action(action) if isinstance(action, AuditLogAction) else action
        threshold = self.thresholds[guild.id].get(action_key)

        if threshold is None:
            return 0
        return 0 if int(threshold) == 1 else int(threshold)

    async def do_ban(self, guild: Guild, user: Union[User, Member], reason: str):
        with suppress(TypeError):
            if hasattr(user, "top_role"):
                if user.top_role >= guild.me.top_role or user.id == guild.owner_id:
                    raise TypeError("Cannot ban this user")
            if await self.bot.glory_cache.ratelimited(f"punishment-{guild.id}-{user.id}", 1, 60) != 0:
                return
            await guild.ban(Object(user.id), reason=reason)
        return

    async def do_kick(self, guild: Guild, user: Union[User, Member], reason: str):
        async with self.locks[guild.id]:
            if hasattr(user, "top_role"):
                if user.top_role >= guild.me.top_role or user.id == guild.owner_id:
                    return False
            if await self.bot.glory_cache.ratelimited(f"punishment-{guild.id}-{user.id}", 1, 60) != 0:
                return
            await user.kick(reason=reason)
        return

    async def do_strip(self, guild: Guild, user: Member, reason: str):
        async with self.locks[guild.id]:
            if user.top_role >= guild.me.top_role or user.id == guild.owner_id:
                return False
            after_roles = [r for r in user.roles if not r.is_assignable()]
            if await self.bot.glory_cache.ratelimited(f"punishment-{guild.id}-{user.id}", 1, 60) != 0:
                return
            await user.edit(roles=after_roles, reason=reason)
        return True

    async def do_punishment(self, guild: Guild, user: Union[User, Member], reason: str):
        punishment = await self.bot.db.fetchval(
            "SELECT punishment FROM antinuke WHERE guild_id = $1", guild.id
        ) or "ban"

        if user.bot:
            await self.do_ban(guild, user, reason)
        elif punishment.lower() == "ban":
            await self.do_ban(guild, user, reason)
        elif punishment.lower() == "kick":
            await self.do_kick(guild, user, reason)
        else:
            await self.do_strip(guild, user, reason)

    async def check_entry(self, guild: Guild, entry: AuditLogEntry) -> bool:
        if entry.user is None:
            return False
        try:
            threshold = await self.get_thresholds(guild, entry.action)
        except Exception:
            threshold = 0

        is_whitelisted = await self.bot.db.fetchval(
            "SELECT user_id FROM antinuke_whitelist WHERE user_id = $1 AND guild_id = $2",
            entry.user.id,
            guild.id,
        )
        if is_whitelisted:
            return True

        if entry.user.id in [
            guild.owner_id,
            self.bot.user.id,
        ] + self.bot.owner_ids:
            return True

        if hasattr(entry.user, "top_role") and entry.user.top_role >= guild.me.top_role:
            return True

        rl = await self.bot.glory_cache.ratelimited(
            f"antinuke-{entry.user.id}-{guild.id}-{str(entry.action)}",
            threshold,
            60,
        )
        if rl == 0 and "bot" not in str(entry.action).lower() and "guild_update" not in str(entry.action).lower():
            return True
        else:
            logger.info(
                f"user {entry.user.name} passed the threshold of {threshold} with {entry.action}"
            )
        return False

    def check_guild(self, guild: Guild, action: Union[AuditLogAction, str]) -> bool:
        if guild.id not in self.guilds:
            return False
        action_key = get_action(action) if isinstance(action, AuditLogAction) else action
        return action_key in self.guilds[guild.id]

    async def get_audit(self, guild: Guild, action: AuditLogAction = None):
        try:
            if not guild.me.guild_permissions.view_audit_log:
                return None
            audit_logs = guild.audit_logs(
                limit=1,
                after=utils.utcnow() - timedelta(seconds=3),
                action=action,
            ) if action else guild.audit_logs(
                limit=1, after=utils.utcnow() - timedelta(seconds=3)
            )
            audit = [a async for a in audit_logs]
            if not audit:
                return None
            audit = audit[0]

            if audit.user_id == self.bot.user.id and "|" in audit.reason:
                user_id = int(audit.reason.split(" | ")[-1].strip())
                audit.user = self.bot.get_user(user_id)
                if audit.guild.id == 1237821518940209212:
                    logger.info(
                        f"user {audit.user} invoked an event for {audit.action} on {audit.target}"
                    )
            return audit
        except Exception:
            return None

    async def check_role(self, role: Role) -> bool:
        permissions = role.permissions
        return any([
            permissions.administrator,
            permissions.manage_guild,
            permissions.kick_members,
            permissions.ban_members,
            permissions.manage_roles,
            permissions.manage_channels,
            permissions.manage_webhooks,
        ])

    @Cog.listener("on_audit_log_entry_create")
    async def on_member_action(self, entry: AuditLogEntry):
        if not self.check_guild(entry.guild, entry.action):
            return

        reason_map = {
            AuditLogAction.kick: "User caught kicking members",
            AuditLogAction.member_prune: "User caught pruning members",
            AuditLogAction.ban: "User caught banning members",
        }

        reason = reason_map.get(entry.action)
        cleanup = entry.action == AuditLogAction.ban

        if not reason:
            return

        if entry.user_id == self.bot.user.id and "|" in entry.reason:
            user_id = int(entry.reason.split(" | ")[-1].strip())
            entry.user = self.bot.get_user(user_id)

        if not await self.check_entry(entry.guild, entry):
            await self.do_punishment(entry.guild, entry.user, self.make_reason(reason))
            if cleanup:
                await entry.guild.unban(Object(entry.target.id), reason=self.make_reason("Cleanup"))
            return

    @Cog.listener("on_member_update")
    async def dangerous_role_assignment(self, before: Member, after: Member):
        guild = after.guild
        if not guild.me.guild_permissions.view_audit_log:
            return
        if before.roles == after.roles or not self.check_guild(guild, "role_update"):
            return

        new_roles = [r for r in after.roles if r not in before.roles and r.is_assignable()]
        if not any(await self.check_role(r) for r in new_roles):
            return

        entry = await self.get_audit(guild, AuditLogAction.member_role_update)
        if not entry or await self.check_entry(guild, entry):
            return

        for r in new_roles:
            await after.remove_roles(r, reason=self.make_reason("User given roles with permissions"))
        await self.do_punishment(guild, entry.user, self.make_reason("User caught giving roles with permissions"))

    @Cog.listener("on_guild_role_update")
    async def role_update(self, before: Role, after: Role):
        guild = after.guild
        if not guild.me.guild_permissions.view_audit_log or not await self.check_role(after) or not self.check_guild(guild, "role_update"):
            return

        entry = await self.get_audit(guild, AuditLogAction.role_update)
        if not entry or await self.check_entry(guild, entry):
            return

        await after.edit(
            permissions=Permissions(before.permissions.value),
            reason=self.make_reason("Cleanup"),
        )
        await self.do_punishment(guild, entry.user, self.make_reason("User caught giving roles dangerous permissions"))

    @Cog.listener("on_guild_role_delete")
    async def role_delete(self, role: Role):
        guild = role.guild
        if not self.check_guild(guild, "role_update"):
            return

        entry = await self.get_audit(guild, AuditLogAction.role_delete)
        if not entry or await self.check_entry(guild, entry):
            return

        await role.clone(reason=self.make_reason("Cleanup"))
        await self.do_punishment(guild, entry.user, self.make_reason("User caught deleting roles"))

    @Cog.listener("on_guild_role_create")
    async def role_create(self, role: Role):
        guild = role.guild
        if not self.check_guild(guild, "role_update"):
            return

        entry = await self.get_audit(guild, AuditLogAction.role_create)
        if not entry or await self.check_entry(guild, entry):
            return

        await role.delete(reason=self.make_reason("Cleanup"))
        await self.do_punishment(guild, entry.user, self.make_reason("User caught creating roles"))

    @Cog.listener("on_guild_channel_create")
    async def channel_create(self, channel):
        guild = channel.guild
        if not self.check_guild(guild, "channel_update"):
            return

        entry = await self.get_audit(guild, AuditLogAction.channel_create)
        if not entry or await self.check_entry(guild, entry):
            return

        await channel.delete(reason=self.make_reason("Cleanup"))
        await self.do_punishment(guild, entry.user, self.make_reason("User caught creating channels"))

    @Cog.listener("on_guild_channel_delete")
    async def channel_delete(self, channel):
        guild = channel.guild
        if not self.check_guild(guild, "channel_update"):
            return

        entry = await self.get_audit(guild, AuditLogAction.channel_delete)
        if not entry or await self.check_entry(guild, entry):
            await channel.clone(reason=self.make_reason("Cleanup"))
            await self.do_punishment(guild, entry.user, self.make_reason("User caught deleting channels"))

    @Cog.listener("on_guild_channel_update")
    async def channel_update(self, before, after):
        guild = after.guild
        if not self.check_guild(guild, "channel_update"):
            return

        entry = await self.get_audit(guild, AuditLogAction.channel_update)
        if not entry or await self.check_entry(guild, entry):
            await after.edit(
                name=before.name,
                position=before.position,
                overwrites=before.overwrites,
                reason=self.make_reason("Cleanup"),
            )
            await self.do_punishment(guild, entry.user, self.make_reason("User caught updating channels"))

    @Cog.listener("on_webhook_update")
    async def webhooks(self, channel):
        guild = channel.guild
        if not self.check_guild(guild, "webhooks"):
            return

        entry = await self.get_audit(guild, AuditLogAction.webhook_create)
        if not entry or await self.check_entry(guild, entry):
            try:
                await entry.target.delete(reason=self.make_reason("Cleanup"))
            except Exception:
                pass
            await self.do_punishment(guild, entry.user, self.make_reason("User caught creating webhooks"))

    @Cog.listener("on_member_join")
    async def antibot(self, member: Member):
        guild = member.guild
        if not member.bot or not self.check_guild(guild, "bot_add"):
            return

        entry = await self.get_audit(guild, AuditLogAction.bot_add)
        if not entry or await self.check_entry(guild, entry):
            await member.ban(reason=self.make_reason("Cleanup"))
            await self.do_punishment(guild, entry.user, self.make_reason("User caught adding bots"))

    @Cog.listener("on_guild_update")
    async def change_guild(self, before: Guild, after: Guild):
        if not self.check_guild(after, "guild_update"):
            return

        entry = await self.get_audit(after, AuditLogAction.guild_update)
        if not entry or await self.check_entry(after, entry):
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
            await self.do_punishment(after, entry.user, self.make_reason("User caught updating the guild"))

    @hybrid_group(
        name="antinuke",
        brief="Protect your guild from nukers",
        with_app_command=True,
        example=",antinuke",
    )
    @bot_has_permissions(administrator=True)
    async def antinuke_group(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)

    @antinuke_group.command(
        name="enable",
        aliases=["e", "setup", "on"],
        brief="Enable all antinuke settings with a default threshold of 0",
        example=",antinuke enable",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_enable(self, ctx: Context):
        await self.bot.db.execute(
            """
            INSERT INTO antinuke (guild_id, bot_add, guild_update, channel_update, role_update, kick, ban, webhooks, member_prune, threshold)
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (guild_id) DO UPDATE SET
                bot_add = excluded.bot_add,
                guild_update = excluded.guild_update,
                channel_update = excluded.channel_update,
                role_update = excluded.role_update,
                webhooks = excluded.webhooks,
                kick = excluded.kick,
                ban = excluded.ban,
                member_prune = excluded.member_prune,
                threshold = excluded.threshold
            """,
            ctx.guild.id,
            True, True, True, True, True, True, True, True, 0,
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
        await ctx.success("antinuke is now **enabled**")

    @antinuke_group.command(
        name="disable",
        aliases=["off", "d", "reset"],
        brief="Disable all antinuke settings",
        example=",antinuke disable",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_disable(self, ctx: Context):
        await self.bot.db.execute("DELETE FROM antinuke WHERE guild_id = $1", ctx.guild.id)
        self.guilds.pop(ctx.guild.id, None)
        await ctx.success("antinuke is now **disabled**")

    @antinuke_group.command(
        name="punishment",
        aliases=["punish"],
        brief="Set a punishment a user will receive for breaking an antinuke rule",
        example=",antinuke punishment ban",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_punishment(self, ctx: Context, punishment: str):
        if punishment.lower() not in ["ban", "kick", "strip"]:
            await ctx.fail(
                "punishment not **recognized**, please use one of the following `ban`, `kick`, `strip`"
            )
            return
        await self.bot.db.execute(
            "UPDATE antinuke SET punishment = $1 WHERE guild_id = $2",
            punishment, ctx.guild.id,
        )
        await ctx.success(f"antinuke **punishment** set to `{punishment}`")

    @antinuke_group.command(
        name="whitelist",
        aliases=["wl"],
        brief="Whitelist or unwhitelist a user from being punished by antinuke",
        example=",antinuke whitelist @user",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_whitelist(self, ctx: Context, *, user: Union[User, Member]):
        exists = await self.bot.db.fetchval(
            "SELECT user_id FROM antinuke_whitelist WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, user.id,
        )
        if exists:
            await self.bot.db.execute(
                "DELETE FROM antinuke_whitelist WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id, user.id,
            )
            await ctx.success(f"Successfully **unwhitelisted** {user.mention}")
        else:
            await self.bot.db.execute(
                "INSERT INTO antinuke_whitelist (guild_id, user_id) VALUES($1, $2) ON CONFLICT(guild_id, user_id) DO NOTHING",
                ctx.guild.id, user.id,
            )
            await ctx.success(f"Successfully **whitelisted** {user.mention}")

    @antinuke_group.command(
        name="trust",
        aliases=["admin"],
        brief="Permit a user to use antinuke commands as an antinuke admin",
        example=",antinuke trust @user",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_trust(self, ctx: Context, *, user: Union[User, Member]):
        exists = await self.bot.db.fetchval(
            "SELECT user_id FROM antinuke_admin WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, user.id,
        )
        if exists:
            await self.bot.db.execute(
                "DELETE FROM antinuke_admin WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id, user.id,
            )
            await ctx.success(f"Successfully **untrusted** {user.mention}")
        else:
            await self.bot.db.execute(
                "INSERT INTO antinuke_admin (guild_id, user_id) VALUES($1, $2) ON CONFLICT(guild_id, user_id) DO NOTHING",
                ctx.guild.id, user.id,
            )
            await ctx.success(f"Successfully **trusted** {user.mention}")

    @antinuke_group.command(
        name="whitelisted",
        aliases=["whitelists", "wld"],
        brief="List all users that cannot be affected by antinuke",
        example=",antinuke whitelisted",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_whitelisted(self, ctx: Context):
        rows = await self.bot.db.fetch(
            "SELECT user_id FROM antinuke_whitelist WHERE guild_id = $1",
            ctx.guild.id,
        )
        if rows:
            users = [f"`{i + 1}` <@!{row.user_id}>" for i, row in enumerate(rows)]
            embed = Embed(title="Whitelists", color=self.bot.color)
            await self.bot.dummy_paginator(ctx, embed, users)

    @antinuke_group.command(
        name="trusted",
        aliases=["admins"],
        brief="List all users who are antinuke admins",
        example=",antinuke trusted",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_trusted(self, ctx: Context):
        rows = await self.bot.db.fetch(
            "SELECT user_id FROM antinuke_admin WHERE guild_id = $1",
            ctx.guild.id,
        )
        if rows:
            users = [f"`{i + 1}` <@!{row.user_id}>" for i, row in enumerate(rows)]
            embed = Embed(title="Admins", color=self.bot.color)
            await self.bot.dummy_paginator(ctx, embed, users)

    @antinuke_group.command(
        name="threshold",
        brief="Set the threshold until antinuke bans the user",
        example=",antinuke threshold kick 3",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_threshold(self, ctx: Context, action: str, threshold: int):
        if action not in self.modules:
            await ctx.fail("Invalid action provided")
            return

        exists = await self.bot.db.fetch(
            "SELECT * FROM antinuke_threshold WHERE guild_id = $1",
            ctx.guild.id,
        )
        if exists:
            await self.bot.db.execute(
                f"UPDATE antinuke_threshold SET {action} = $1 WHERE guild_id = $2",
                threshold, ctx.guild.id,
            )
        else:
            await self.bot.db.execute(
                f"INSERT INTO antinuke_threshold (guild_id, {action}) VALUES($1, $2)",
                ctx.guild.id, threshold,
            )
        await self.make_cache()
        thres = f" with a threshold of `{threshold}`" if threshold != 0 else ""
        await ctx.success(f"Successfully **set threshold** to `{threshold}` for **{action}**")

    async def get_users(self, ctx: Context, whitelisted: bool = False):
        query = "antinuke_admin" if not whitelisted else "antinuke_whitelist"
        rows = await self.bot.db.fetch(
            f"SELECT user_id FROM {query} WHERE guild_id = $1",
            ctx.guild.id,
        )
        users = [self.bot.get_user(row.user_id) for row in rows if self.bot.get_user(row.user_id)]
        users.append(ctx.guild.owner)
        return users

    async def find_threshold(self, guild: Guild, action: str):
        threshold = await self.get_thresholds(guild, action) or 0
        return action, threshold

    def format_module(self, module: str) -> str:
        module_formatted = module.replace("_", " ")
        return f"**anti [{module_formatted}]({self.bot.domain}):**"

    @antinuke_group.command(
        name="settings",
        aliases=["config"],
        brief="List your antinuke settings along with their thresholds",
        example=",antinuke settings",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_settings(self, ctx: Context):
        data = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke WHERE guild_id = $1",
            ctx.guild.id,
        )
        if not data:
            await ctx.fail("antinuke not **setup**")
            return

        try:
            thresholds = await gather(*[self.find_threshold(ctx.guild, a) for a in self.modules])
            thresholds = {a: t for a, t in thresholds}
        except Exception:
            thresholds = {m: 0 for m in self.modules}

        embed = Embed(title="Antinuke Settings", color=self.bot.color)
        description = f"**Punishment:** `{data.get('punishment', 'ban')}`\n"
        for key, value in data.items():
            if key == "guild_id" or key == "punishment":
                continue
            if key in self.modules:
                threshold = thresholds.get(key, 0)
                thres_msg = f" - limit: `{threshold}`" if threshold else ""
                state = self.bot.cogs["Automod"].get_state(bool(value))
                description += f"{self.format_module(key)} {state}{thres_msg}\n"

        embed.description = description
        whitelisted = await self.get_users(ctx, True)
        admins = await self.get_users(ctx, False)

        if whitelisted:
            embed.add_field(
                name="Whitelisted",
                value=", ".join(m.mention for m in whitelisted),
                inline=True,
            )
        if admins:
            embed.add_field(
                name="Admins",
                value=", ".join(m.mention for m in admins),
                inline=True,
            )
        await ctx.send(embed=embed)

    @antinuke_group.command(
        name="botadd",
        aliases=["bot", "ba", "bot_add"],
        brief="Toggle the anti bot add of antinuke",
        example=",antinuke bot_add true",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_bot_add(self, ctx: Context, state: bool):
        await self.antinuke_toggle(ctx, "bot_add", state)

    @antinuke_group.command(
        name="role",
        aliases=["roles", "role_update"],
        brief="Toggle the anti role update of antinuke",
        example=",antinuke role_update true",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_role_update(self, ctx: Context, state: bool):
        await self.antinuke_toggle(ctx, "role_update", state)

    @antinuke_group.command(
        name="channel",
        aliases=["channels", "channel_update"],
        brief="Toggle the anti channel update of antinuke",
        example=",antinuke channel_update true",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_channel_update(self, ctx: Context, state: bool):
        await self.antinuke_toggle(ctx, "channel_update", state)

    @antinuke_group.command(
        name="webhooks",
        brief="Toggle the anti webhooks of antinuke",
        example=",antinuke webhooks true",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_webhooks(self, ctx: Context, state: bool):
        await self.antinuke_toggle(ctx, "webhooks", state)

    @antinuke_group.command(
        name="guild",
        brief="Toggle the anti guild_update of antinuke",
        example=",antinuke guild_update true",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_guild_update(self, ctx: Context, state: bool):
        await self.antinuke_toggle(ctx, "guild_update", state)

    @antinuke_group.command(
        name="prune",
        aliases=["member_prune"],
        brief="Toggle the anti member_prune of antinuke",
        example=",antinuke member_prune true",
    )
    @trusted()
    async def antinuke_member_prune(self, ctx: Context, state: bool):
        await self.antinuke_toggle(ctx, "member_prune", state)

    @antinuke_group.command(
        name="kick",
        brief="Toggle the anti kick of antinuke",
        example=",antinuke kick true",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_kick(self, ctx: Context, state: bool):
        await self.antinuke_toggle(ctx, "kick", state)

    @antinuke_group.command(
        name="ban",
        brief="Toggle the anti ban of antinuke",
        example=",antinuke ban true",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_ban(self, ctx: Context, state: bool):
        await self.antinuke_toggle(ctx, "ban", state)

    async def antinuke_toggle(self, ctx: Context, module: str, state: bool):
        threshold = int(ctx.parameters.get("threshold", 0))

        if module not in self.modules:
            for m in self.modules:
                if module.lower() in m.lower():
                    module = m
                    break
            else:
                await ctx.fail(
                    f"Module not valid, please use `{ctx.prefix}antinuke modules` to view valid modules."
                )
                return

        exists = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke WHERE guild_id = $1",
            ctx.guild.id,
        )
        if not exists:
            await ctx.fail("antinuke not **setup**")
            return

        update_queries = {
            "bot_add": "UPDATE antinuke SET bot_add = $1 WHERE guild_id = $2",
            "role_update": "UPDATE antinuke SET role_update = $1 WHERE guild_id = $2",
            "channel_update": "UPDATE antinuke SET channel_update = $1 WHERE guild_id = $2",
            "guild_update": "UPDATE antinuke SET guild_update = $1 WHERE guild_id = $2",
            "kick": "UPDATE antinuke SET kick = $1 WHERE guild_id = $2",
            "ban": "UPDATE antinuke SET ban = $1 WHERE guild_id = $2",
            "member_prune": "UPDATE antinuke SET member_prune = $1 WHERE guild_id = $2",
            "webhooks": "UPDATE antinuke SET webhooks = $1 WHERE guild_id = $2",
        }

        query = update_queries.get(module)
        if query:
            await self.bot.db.execute(query, state, ctx.guild.id)
        else:
            await ctx.fail("Module is not recognized")
            return

        if await self.bot.db.fetchrow("SELECT * FROM antinuke_threshold WHERE guild_id = $1", ctx.guild.id):
            await self.bot.db.execute(
                f"UPDATE antinuke_threshold SET {module} = $1 WHERE guild_id = $2",
                threshold, ctx.guild.id,
            )
        else:
            await self.bot.db.execute(
                f"INSERT INTO antinuke_threshold (guild_id, {module}) VALUES($1, $2)",
                ctx.guild.id, threshold,
            )

        self.guilds[ctx.guild.id][module] = state
        status = "enabled" if state else "disabled"
        await self.make_cache()
        thres_msg = f" with a threshold of `{threshold}`" if threshold != 0 else ""
        await ctx.success(f"Successfully **{status}** `{module}`{thres_msg}")

    @antinuke_group.command(
        name="modules",
        aliases=["features", "events"],
        brief="Show antinuke modules",
        example=",antinuke modules",
    )
    @bot_has_permissions(administrator=True)
    @trusted()
    async def antinuke_modules(self, ctx: Context):
        embed = Embed(
            title="Antinuke Modules",
            color=self.bot.color,
            description=", ".join(self.modules),
        )
        await ctx.send(embed=embed)

    @command(name="hardban", aliases=["hb"], brief="Hardban a user", example=",hardban @user")
    @trusted()
    @has_permissions(ban_members=True)
    async def hardban(self, ctx: Context, user: User):
        res = await self.bot.db.fetchval(
            "SELECT user_id FROM hardban WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, user.id,
        )
        if res:
            confirm = await ctx.confirm("User is already hardbanned. Do you want to unhardban?")
            if confirm:
                await self.bot.db.execute(
                    "DELETE FROM hardban WHERE guild_id = $1 AND user_id = $2",
                    ctx.guild.id, user.id,
                )
                await ctx.guild.unban(Object(id=user.id), reason="User unhardbanned by trusted admin or owner")
                await ctx.success(f"Successfully **unhardbanned** {user.mention}")
        else:
            await self.bot.db.execute(
                "INSERT INTO hardban (guild_id, user_id) VALUES($1, $2)",
                ctx.guild.id, user.id,
            )
            await ctx.guild.ban(Object(id=user.id), reason="User hardbanned by trusted admin or owner")
            await ctx.success(f"Successfully **hardbanned** {user.mention}")

    @Cog.listener("on_member_join")
    async def hardban_listener(self, member: Member):
        res = await self.bot.db.fetchval(
            "SELECT user_id FROM hardban WHERE guild_id = $1 AND user_id = $2",
            member.guild.id, member.id,
        )
        if res:
            with suppress(Exception):
                await member.ban(reason="User hardbanned by trusted admin or owner")


async def setup(bot):
    await bot.add_cog(AntiNuke(bot))
