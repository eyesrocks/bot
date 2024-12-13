import discord
from discord import Embed, Message, Member, User, Object, AuditLogEntry, utils, VoiceState, Role, abc
from discord.ext.commands import Context
from datetime import datetime
from enum import Enum, auto
from typing import Union, Optional, Any
from loguru import logger
from rival_tools import ratelimit, lock
from _types import catch

change_type = Union[Role, AuditLogEntry]

def serialize(key: str, value: Any):
    if isinstance(value, list):
        return ", ".join(f"`{m}`" for m in value)
    if key in ["allow", "deny"]:
        return False
    return value

def get_channel_changes(before: Union[abc.GuildChannel, AuditLogEntry], after: Union[abc.GuildChannel, AuditLogEntry]):
    changes = {}
    if isinstance(before, abc.GuildChannel):
        attrs = before.__slots__
        b = {s: getattr(before, s) for s in attrs}
        a = {s: getattr(after, s) for s in attrs}
        changes = {s: a[s] for s in attrs if b[s] != a[s]}
    else:
        key = list(before.changes.before.keys())[0]
        if key in ["allow", "deny"]:
            b = before.changes.before[key]
            a = after.changes.after[list(after.changes.after.keys())[0]]
            changes = {k: v for k, v in a.items() if b[k] != v}
            target = next(t for t, v in before.target.overwrites if v == a)
    string = "\n".join(f"**{key}:** `{serialize(key, value)}`" for key, value in changes.items())
    if "overwrites" in a:
        target = next(t for t, v in after.overwrites if v == a["overwrites"])
    return target, string

def get_role_changes(before: change_type, after: change_type):
    added, removed = "", ""
    if isinstance(before, Role):
        if before.permissions != after.permissions:
            b = dict(before.permissions)
            a = dict(after.permissions)
        else:
            return None
    else:
        b = dict(before.changes.before.get("permissions"))
        a = dict(after.changes.after.get("permissions"))
    difference = {key: value for key, value in a.items() if b[key] != value}
    for k, v in difference.items():
        if v:
            added += f", `{k.replace('_', ' ')}`" if added else f"`{k.replace('_', ' ')}`"
        else:
            removed += f", `{k.replace('_', ' ')}`" if removed else f"`{k.replace('_', ' ')}`"
    string = f"**added:** {added}\n" if added else ""
    string += f"**removed:** {removed}" if removed else ""
    return string

class EventType(Enum):
    channel_create = auto()
    channel_delete = auto()
    channel_update = auto()
    category_channel_create = auto()
    category_channel_delete = auto()
    category_channel_update = auto()
    role_create = auto()
    role_delete = auto()
    role_update = auto()
    role_assign = auto()
    role_remove = auto()
    command_enable = auto()
    command_disable = auto()
    alias_create = auto()
    alias_delete = auto()
    ban = auto()
    kick = auto()
    time_out = auto()
    mention_everyone = auto()
    voicemaster_channel_create = auto()
    voicemaster_channel_delete = auto()
    voice_join = auto()
    voice_leave = auto()
    jail = auto()
    unjail = auto()
    strip = auto()
    fakeperms_add = auto()
    fakeperms_remove = auto()
    reaction_mute = auto()
    reaction_unmute = auto()
    image_mute = auto()
    image_unmute = auto()

class Handler:
    def __init__(self, bot):
        self.bot = bot

    async def check_user(self, user: Union[Member, User, Object]):
        if isinstance(user, Object):
            try:
                user = self.bot.get_user(user.id) or await self.bot.fetch_user(user.id)
                if not user:
                    return "Unknown User"
            except discord.NotFound:
                return "Unknown User"
        return user.mention

    def get_parents(self, ctx: Context):
        return [c.name for c in ctx.command.parents]

    def get_kwargs(self, ctx: Context):
        kw = ctx.kwargs
        if len(ctx.args) > 2:
            d = [c for c in ctx.command.clean_params.keys() if c not in kw]
            for i, arg in enumerate(ctx.args[2:]):
                kw[d[i]] = arg
        ctx.kwargs = kw
        return ctx

    def voice_embed(self, ctx: Member, before: VoiceState, after: VoiceState, **kwargs):
        ts = utils.format_dt(datetime.now(), style="R")
        embed = Embed(color=self.bot.color)
        if kwargs.get("voicemaster", False):
            if after is None and len(before.members) == 1:
                embed.title = "vm channel deletion"
                embed.description = f"voicemaster channel was deleted due to **{str(ctx)}** leaving {ts}"
            elif after and (before is None or before.channel != after.channel):
                embed.title = "vm channel creation"
                embed.description = f"voicemaster channel was created for **{str(ctx)}** {ts}"
        else:
            if before.channel:
                if after.channel:
                    embed.title = "User changed voice channels"
                    embed.description = f"{ctx.mention} left **{before.channel.name}** and joined **{after.channel.name}** {ts}"
                else:
                    embed.title = "User left a voice channel"
                    embed.description = f"{ctx.mention} left **{before.channel.name}** {ts}"
            elif after.channel:
                embed.title = "User joined a voice channel"
                embed.description = f"{ctx.mention} joined **{after.channel.name}** {ts}"
        return embed

    async def get_embed(self, ctx: Union[Context, Message, AuditLogEntry], event: EventType):
        ts = utils.format_dt(datetime.now(), style="R")
        embed = Embed(color=self.bot.color)
        if isinstance(ctx, Context):
            ctx = self.get_kwargs(ctx)
            args = ctx.kwargs
            author_mention = ctx.author.mention if hasattr(ctx.author, 'mention') else "Unknown User"
            if event == EventType.jail:
                embed.title = "Member Jailed"
                embed.description = f"**Moderator:** {author_mention}\n> **Action:** jailed\n> **User:** {args['member'].mention}\n> **When:** {ts}"
            elif event == EventType.unjail:
                member = args.get("member")
                if isinstance(member, str) and member.lower() == "all":
                    embed.title = "members unjailed"
                    embed.description = f"{author_mention} **unjailed** all jailed members {ts}"
                else:
                    embed.title = "Member Unjailed"
                    embed.description = f"**Moderator:** {author_mention}\n> **Action:** unjailed\n> **User:** {args['member'].mention}\n> **When:** {ts}"
            elif event == EventType.fakeperms_add:
                embed.title = "Fake Permissions Added"
                embed.description = f"**Moderator:** {author_mention}\n**Action:** {args['entry'][0].mention} was given `{args['entry'][1]}`\n**When:** {ts}"
            elif event == EventType.fakeperms_remove:
                embed.title = "Fake Permissions Removed"
                embed.description = f"**Moderator:** {author_mention}\n**Action:** permissions removed from {args['role'].mention}\n**When:** {ts}"
            elif event == EventType.strip:
                embed.title = "Member stripped"
                embed.description = f"**Moderator:** {author_mention}\n> **Action:** `All roles removed`\n> **User:** {args['member'].mention}\n> **When:** {ts}"
            elif event == EventType.alias_create:
                embed.title = "Bot Settings Updated"
                embed.description = f"**Moderator:** {author_mention}\n> **Action:** Created an alias\n> **Command:** `{args['data'].command}`\n> **Alias Created:** `{args['data'].alias}`\n> **When:** {ts}"
            elif event == EventType.alias_delete:
                embed.title = "Bot Settings Updated"
                embed.description = f"**Moderator:** {author_mention}\n> **Action:** Deleted an alias\n> **Command:** `{args['command']}`\n> **Alias Deleted:** `{args['alias']}`\n> **When:** {ts}"
            elif event == EventType.command_disable:
                embed.title = "Bot Settings Updated"
                embed.description = f"**Moderator:** {author_mention}\n> **Action:** Disabled a command\n> **Command:** `{args['command']}`\n> **When:** {ts}"
            elif event == EventType.command_enable:
                embed.title = "Bot Settings Updated"
                embed.description = f"**Moderator:** {author_mention}\n> **Action:** Enabled a command\n> **Command:** `{args['command']}`\n> **When:** {ts}"
            elif event == EventType.ban:
                embed.title = "Member banned"
                embed.description = f"**Moderator:** {author_mention}\n> **Punishment:** `BANNED`\n> **User:** {str(args['user'])}\n> **When:** {ts}"
            elif event == EventType.kick:
                embed.title = "user kicked"
                embed.description = f"**Moderator:** {author_mention}\n> **Punishment:** `KICKED`\n> **User:** {str(args['user'])}\n> **When:** {ts}"
            elif event == EventType.time_out:
                embed.title = "Member Muted"
                embed.description = f"**Moderator:** {author_mention}\n> **User:** {str(args.get('user', 'member'))}\n> **Punishment:** member timeout\n> **When:** {ts}\n> **Timeout Duration:** {args['time']}"
            elif event == EventType.role_assign:
                embed.title = "Role(s) Assigned to user"
                roles = args.get("role", args.get("role_input"))
                r = ", ".join(role.mention for role in roles) if len(roles) > 1 else roles[0].mention
                e = f"{args['member'].mention}" if args.get("member") else ""
                embed.description = f"**Moderator:** {author_mention}\n> **Role(s):** {r}\n> **User:** {e}\n> **When:** {ts}"
            elif event == EventType.role_create:
                embed.title = "Role Created"
                embed.description = f"**Moderator:** {author_mention}\n> **Role:** {args['name']}\n> **When:** {ts}"
            elif event == EventType.role_update:
                embed.title = "Role Updated"
                role = args.get("args").roles[0] if args.get("args") else args.get("role")
                embed.description = f"**Moderator:** {author_mention}\n> Role: **{role.name}**\n> **Using:** {ctx.command.qualified_name}\n> **When:** {ts}" if role else "**Role information is unavailable**"
            elif event == EventType.category_channel_create:
                embed.title = "Category Created"
                embed.description = f"**Moderator:** {author_mention}\n> **Category:** {args['name']}\n> **How:** Created through Greeds `,category create` command\n> **When:** {ts}"
            elif event == EventType.category_channel_delete:
                embed.title = "Category Deleted"
                embed.description = f"**Moderator:** {author_mention}\n> **Category:** {args['category'].name}\n> **How:** Deleted through Greeds `,category delete` command\n> **When:** {ts}"
            elif event == EventType.category_channel_update:
                embed.title = "Category Deleted"
                embed.description = f"**Moderator:** {author_mention}\n> **Category:** {args['category'].name}\n> **Using:** {ctx.command.qualified_name}\n> **When:** {ts}"
            elif event == EventType.channel_create:
                embed.title = "Category Created"
                embed.description = f"**Moderator:** {author_mention}\n> **Channel:** {args['name']}\n> **How:** Created through Greeds `,channel create` command\n> **When:** {ts}"
            elif event == EventType.channel_delete:
                embed.title = "Channel Deleted"
                embed.description = f"**Moderator:** {author_mention}\n> **Channel:** {args['channel'].name}\n> **How:** Deleted through Greeds `,channel delete` command\n> **When:** {ts}"
            elif event == EventType.channel_update:
                embed.title = "Channel Updated"
                embed.description = f"**Moderator:** {author_mention}\n> **Channel:** {args['channel'].name}\n> **Using:** {ctx.command.qualified_name}\n> **When:** {ts}"
            elif event == EventType.reaction_mute:
                embed.title = "Reaction Mute"
                embed.description = f"**Moderator:** {author_mention}\n> **Target:** {args['member'].name}\n> **Using:** {ctx.command.qualified_name}\n> **When:** {ts}"
            elif event == EventType.reaction_unmute:
                embed.title = "Reaction UnMute"
                embed.description = f"**Moderator:** {author_mention}\n> **Target:** {args['member'].name}\n> **Using:** {ctx.command.qualified_name}\n> **When:** {ts}"
            elif event == EventType.image_mute:
                embed.title = "Image Mute"
                embed.description = f"**Moderator:** {author_mention}\n> **Target:** {args['member'].name}\n> **Using:** {ctx.command.qualified_name}\n> **When:** {ts}"
            elif event == EventType.image_unmute:
                embed.title = "Image UnMute"
                embed.description = f"**Moderator:** {author_mention}\n**Action:** permissions removed from {ctx.kwargs['role'].mention}\n**When:** {ts}"
            if embed.title is None:
                if ctx.author.name == "aiohttp":
                    logger.info(
                        f"{event} didnt get an embed {'yes' if event == EventType.ban else 'no'}"
                    )
                return None
        elif isinstance(ctx, Message):
            if event == EventType.mention_everyone:
                embed.title = "Mentioned Everyone"
                embed.description = f"**Moderator:** {ctx.author.mention}\n> **Action:** mentioned @everyone \n> **Where:** {ctx.channel.mention}\n> **When:** {ts}"
            else:
                return None
        elif isinstance(ctx, AuditLogEntry):
            if event == EventType.role_assign:
                if ctx.reason:
                    if ctx.reason.startswith(f"[ {self.bot.user.name} antinuke ]"):
                        reason = ctx.reason.split(f"[ {self.bot.user.name} antinuke ]")[-1]
                        title = "member stripped"
                        description = f"**Moderator:** {ctx.user.mention}\n> **User Stripped:** {await self.check_user(ctx.target)}\n> **Reason:** {reason}\n> **When:** {ts}"
                    else:
                        if ctx.user == self.bot.user:
                            return None
                        reason = ctx.reason
                        title = "Role Settings Changed"
                        description = f"**Moderator:** {ctx.user.mention}\n> **User Stripped:** {await self.check_user(ctx.target)}\n **Reason:** {reason}\n> **When:** {ts}"
                else:
                    if ctx.user == self.bot.user:
                        return
                    description = f"**Moderator:** {ctx.user.mention}\n> **User:** {str(ctx.target.mention)}\n> **Action:** Roles Updated\n> **How:** Roles updated through the guild settings\n> **When:** {ts}"
                    title = "Role Settings Changed"
                embed.title = title
                embed.description = description
            elif event == EventType.channel_create:
                if ctx.user == self.bot.user:
                    return None
                embed.title = "Channel Created"
                embed.description = f"**Moderator:** {ctx.user.mention}\n> **Channel:** `{await self.check_user(ctx.target)}`\n> **How:** Created through the guild settings\n> **When:** {ts}"
            elif event == EventType.channel_delete:
                if ctx.user == self.bot.user:
                    return None
                embed.title = "Channel Deleted"
                embed.description = f"**Moderator:** {ctx.user.mention}\n> **Channel:** `{str(ctx.before.name)}`\n> **How:** Deleted through guild settings\n> **When:** {ts}"
            elif event == EventType.channel_update:
                if ctx.user == self.bot.user:
                    return None
                try:
                    target, changes = get_channel_changes(ctx, ctx)
                    t = f" for {target.mention} "
                    m = f"\n{changes}"
                except Exception:
                    t = ""
                    m = ""
                embed.title = "Channel Updated"
                embed.description = f"**Moderator:** {ctx.user.mention}\n> **Channel:** {await self.check_user(ctx.target)}{t}\n> **When:**{ts}{m}"
            elif event == EventType.category_channel_create:
                if ctx.user == self.bot.user:
                    return None
                embed.title = "Category Created"
                embed.description = f"**Moderator:** {ctx.user.mention}\n> **Category:** {str(ctx.after.name)}\n> **When:** {ts}"
            elif event == EventType.category_channel_delete:
                if ctx.user == self.bot.user:
                    return None
                embed.title = "Category Deleted"
                embed.description = f"**Moderator:** {ctx.user.mention}\n> **Category:** {str(ctx.before.name)}\n> **When:** {ts}"
            elif event == EventType.category_channel_update:
                if ctx.user == self.bot.user:
                    return None
                embed.title = "Category Updated"
                embed.description = f"**Moderator:** {ctx.user.mention}\n> **Updated** {await self.check_user(ctx.target)}\n\n> **When** {ts}"
            elif event == EventType.ban:
                if ctx.reason:
                    if ctx.reason.startswith(f"[ {self.bot.user.name} antinuke ]"):
                        reason = ctx.reason.split(f"[ {self.bot.user.name} antinuke ]")[-1]
                        title = "Member Banned"
                        description = f"**Moderator:** {ctx.user.mention}\n> **User Punished:** {await self.check_user(ctx.target)}\n> **Punishment:** `member banned`\n> **Reason:** {reason}\n> **When:** {ts}"
                    else:
                        if ctx.user == self.bot.user:
                            return None
                        reason = ctx.reason or "no reason provided"
                        title = "Member Banned"
                        description = f"**Moderator:** {ctx.user.mention}\n> **User Punished:** {await self.check_user(ctx.target)}\n> **Punishment:** `member banned`\n> **Reason:** {reason}\n> **When:** {ts}"
                else:
                    reason = ctx.reason or "no reason provided"
                    title = "Member Banned"
                    description = f"**Moderator:** {ctx.user.mention}\n> **User Punished:** {await self.check_user(ctx.target)}\n> **Punishment:** `member banned`\n> **When:** {ts}"
                embed.title = title
                embed.description = description
            elif event == EventType.kick:
                if ctx.reason:
                    if ctx.reason.startswith(f"[ {self.bot.user.name} antinuke ]"):
                        reason = ctx.reason.split(f"[ {self.bot.user.name} antinuke ]")[-1]
                        title = "Member Kicked"
                        description = f"**Moderator:** {ctx.user.mention}\n> **User Punished:** {await self.check_user(ctx.target.id)}\n> **Punishment:** `member kicked`\n> **Reason:** {reason}\n> **When:** {ts}"
                    else:
                        if ctx.user == self.bot.user:
                            return None
                        reason = ctx.reason or "no reason provided"
                        title = "Member Kicked"
                        description = f"**Moderator:** {ctx.user.mention}\n> **User Punished:** {await self.check_user(ctx.target)}\n> **Punishment:** `member kicked`\n> **Reason:** {reason}\n> **When:** {ts}"
                else:
                    if ctx.user == self.bot.user:
                        return None
                    reason = ctx.reason or "no reason provided"
                    title = "Member Kicked"
                    description = f"**Moderator:** {ctx.user.mention}\n> **User Punished:** {await self.check_user(ctx.target)}\n> **Punishment:** `member kicked`\n> **When:** {ts}"
                embed.title = title
                embed.description = description
            elif event == EventType.time_out:
                if ctx.changes.after.timed_out_until != None:
                    time = f"\n> **Expiration:** {discord.utils.format_dt(ctx.changes.after.timed_out_until, style = 'R')}"
                else:
                    time = ""
                if ctx.reason:
                    if ctx.user == self.bot.user:
                        if ctx.reason.startswith("muted by the"):
                            embed.title = "Auto Mod Punishment"
                            embed.description = f"**User Punished**: {await self.check_user(ctx.target)}\n> **Punishment:** `member timed out`\n> **Reason:** {ctx.reason}\n> **When:** {ts}{time}"
                    else:
                        if ctx.changes.after.timed_out_until == None:
                            embed.title = "Member Untimed Out"
                        else:
                            embed.title = "Member Timed Out"
                        embed.description = f"**Moderator:** {str(ctx.user)}\n> **User Punished**: {await self.check_user(ctx.target)}\n> **Action:** `member timeout`\n> **Reason:** {ctx.reason}\n> **When:** {ts}{time}"
                else:
                    if ctx.changes.after.timed_out_until == None:
                        embed.title = "Member Untimed Out"
                        u = False
                    else:
                        embed.title = "Member Timed Out"
                        u = True
                    reason = f"> **Reason:** {ctx.reason}" + "\n" if ctx.reason else ""
                    embed.description = f"**Moderator:** {str(ctx.user)}\n> **User Punished**: {await self.check_user(ctx.target)}\n> **Punishment:** `member untimed out`\n{reason}> **When:** {ts}{time}"
            else:
                return None
        if embed.description == None:
            return
        embed.description = f"> {embed.description}"
        return embed

    async def handle_log(
        self, ctx: Union[Context, Message, AuditLogEntry]
    ) -> Optional[EventType]:
        if isinstance(ctx, Message):
            if ctx.mention_everyone:
                return EventType.mention_everyone
        elif isinstance(ctx, Context):
            command_name = ctx.command.qualified_name
            if command_name == "role":
                return EventType.role_assign
            elif command_name.startswith("role"):
                parents = self.get_parents(ctx)
                if ctx.command.name == "delete":
                    return EventType.role_delete
                elif "all" in parents and "cancel" not in command_name:
                    return EventType.role_assign
                else:
                    return EventType.role_update
            elif command_name == "command disable":
                return EventType.command_disable
            elif command_name == "command enable":
                return EventType.command_enable
            elif command_name == "alias add":
                return EventType.alias_create
            elif command_name == "alias remove":
                return EventType.alias_delete
            elif command_name == "ban":
                return EventType.ban
            elif command_name == "kick":
                return EventType.kick
            elif command_name == "reactionmute":
                role = discord.utils.get(ctx.guild.roles, name="rmute")
                member = ctx.kwargs.get("member")
                if role in member.roles:
                    return EventType.reaction_mute
                else:
                    return EventType.reaction_unmute
            elif command_name == "imagemute":
                role = discord.utils.get(ctx.guild.roles, name="imute")
                if role in ctx.kwargs.get("member").roles:
                    return EventType.image_mute
                else:
                    return EventType.image_unmute
            elif command_name == "mute":
                return EventType.time_out
            elif command_name == "fakepermissions add":
                return EventType.fakeperms_add
            elif command_name == "fakepermissions remove":
                return EventType.fakeperms_remove
            elif command_name == "jail":
                return EventType.jail
            elif command_name == "unjail":
                return EventType.unjail
            elif command_name == "strip":
                return EventType.strip
            elif command_name.startswith("channel"):
                if ctx.command.name == "delete":
                    return EventType.channel_delete
                elif ctx.command.name in ("duplicate", "create"):
                    return EventType.channel_create
                else:
                    return EventType.channel_update
            elif command_name.startswith("category"):
                if ctx.command.name == "delete":
                    return EventType.category_channel_delete
                elif ctx.command.name in ("create", "duplicate"):
                    return EventType.category_channel_create
                else:
                    return EventType.category_channel_update
        elif isinstance(ctx, AuditLogEntry):
            if ctx.reason and ctx.reason.startswith("invoked by"):
                return None
            action = int(ctx.action.value)
            if action == 10:
                if str(ctx.target.type) == "category":
                    return EventType.category_channel_create
                else:
                    return EventType.channel_create
            elif action == 11:
                if str(ctx.target.type) == "category":
                    return EventType.category_channel_update
                else:
                    return EventType.channel_update
            elif action == 12:
                if str(ctx.target.type) == "category" or str(ctx.changes.before.type) == "category":
                    return EventType.category_channel_delete
                else:
                    return EventType.channel_delete
            elif action in (13, 14, 15):
                if str(ctx.target.type) == "category":
                    return EventType.category_channel_update
                else:
                    return EventType.channel_update
            elif action == 30:
                return EventType.role_create
            elif action == 31:
                return EventType.role_update
            elif action == 32:
                return EventType.role_delete
            elif action == 24 and hasattr(ctx.changes.before, "timed_out_until"):
                return EventType.time_out
            elif action == 20:
                return EventType.kick
            elif action == 22:
                return EventType.ban
            elif action == 25:
                if len(ctx.changes.before.roles) != len(ctx.changes.after.roles):
                    return EventType.role_assign
        return None

    @lock("logs:{c.guild.id}")
    async def do_log(self, c: Union[Context, Message, AuditLogEntry, Member], **kwargs):
        with catch(Exception, False, True):
            if kwargs:
                embed = self.voice_embed(c, kwargs["before"], kwargs["after"])
            else:
                _type = await self.handle_log(c)
                if _type is None:
                    return
                embed = await self.get_embed(c, _type)
            if embed:
                @ratelimit("modlogs:{c.guild.id}", 3, 5, True)
                async def do_message(c: Union[Context, Message, AuditLogEntry, Member], embed: Embed):
                    channel_id = await self.bot.db.fetchval(
                        """SELECT channel_id FROM moderation_channel WHERE guild_id = $1""",
                        c.guild.id,
                    )
                    if channel_id:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await channel.send(embed=embed)
                await do_message(c, embed)
