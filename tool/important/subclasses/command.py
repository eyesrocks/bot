import discord
import re
from dataclasses import dataclass
from discord.ext import commands
from discord.ext.commands import Context
import typing
from contextlib import suppress
from aiohttp import ClientSession as Session
from discord import GuildSticker
from discord.ext.commands.converter import GuildStickerConverter, GuildStickerNotFound
from typing import Optional, Union, List
import unicodedata
from loguru import logger
from fast_string_match import closest_match


@dataclass
class MultipleArguments:
    first: str
    second: str


DISCORD_ROLE_MENTION = re.compile(r"<@&(\d+)>")
DISCORD_ID = re.compile(r"(\d+)")
DISCORD_USER_MENTION = re.compile(r"<@?(\d+)>")
DISCORD_CHANNEL_MENTION = re.compile(r"<#(\d+)>")
DISCORD_MESSAGE = re.compile(
    r"(?:https?://)?(?:canary\.|ptb\.|www\.)?discord(?:app)?.(?:com/channels|gg)/(?P<guild_id>[0-9]{17,22})/(?P<channel_id>[0-9]{17,22})/(?P<message_id>[0-9]{17,22})"
)


class NonStrictMessage(commands.Converter):
    async def convert(self, ctx: Context, argument: str):
        if match := DISCORD_MESSAGE.match(argument):
            return match.group(3)
        return argument


def has_permissions(**permissions):
    """Check if the user has permissions to execute the command (fake permissions included)"""

    async def predicate(ctx: commands.Context):
        if isinstance(ctx, int):
            return [permission for permission, value in permissions.items() if value]
        if ctx.author.id in ctx.bot.owner_ids or ctx.author.guild_permissions.administrator:
            return True

        missing_permissions = [
            permission for permission in permissions
            if not getattr(ctx.author.guild_permissions, permission, False)
        ]

        if missing_permissions:
            mroles = [r.id for r in ctx.author.roles if r.is_assignable()]
            data = await ctx.bot.db.fetch(
                """SELECT role_id, perms FROM fakeperms WHERE guild_id = $1""",
                ctx.guild.id,
            )
            if data:
                for role_id, perms in data:
                    if role_id in mroles:
                        for perm in perms.split(","):
                            with suppress(ValueError):
                                missing_permissions.remove(perm.strip())

        if missing_permissions:
            raise commands.MissingPermissions(missing_permissions)
        return True

    return commands.check(predicate)


permissions = [
    "create_instant_invite", "kick_members", "ban_members", "administrator",
    "manage_channels", "manage_guild", "add_reactions", "view_audit_log",
    "priority_speaker", "stream", "read_messages", "manage_members",
    "send_messages", "send_tts_messages", "manage_messages", "embed_links",
    "attach_files", "read_message_history", "mention_everyone", "external_emojis",
    "view_guild_insights", "connect", "speak", "mute_members", "deafen_members",
    "move_members", "use_voice_activation", "change_nickname", "manage_nicknames",
    "manage_roles", "manage_webhooks", "manage_expressions", "use_application_commands",
    "request_to_speak", "manage_events", "manage_threads", "create_public_threads",
    "create_private_threads", "external_stickers", "send_messages_in_threads",
    "use_embedded_activities", "moderate_members", "use_soundboard", "create_expressions",
    "use_external_sounds", "send_voice_messages"
]

commands.has_permissions = has_permissions


@dataclass
class FakePermissionEntry:
    role: discord.Role
    permissions: Union[str, List[str]]


def validate_permissions(perms: Union[str, List[str]]):
    if isinstance(perms, str):
        perms = [perms]
    for p in perms:
        if p not in permissions:
            raise commands.CommandError(f"`{p}` is not a valid permission")
    return True


class FakePermissionConverter(commands.Converter):
    async def convert(self, ctx: Context, argument: str) -> Optional[FakePermissionEntry]:
        args = [arg.strip() for arg in re.split(r'[ ,]', argument, 1)]
        if len(args) != 2:
            raise commands.CommandError("please include a `,` between arguments")
        args[0] = await Role().convert(ctx, args[0])
        perms = [p.strip().replace(" ", "_").lower() for p in args[1].split(",")]
        validate_permissions(perms)
        return FakePermissionEntry(role=args[0], permissions=perms)


class Argument(commands.Converter):
    async def convert(self, ctx: Context, argument: str) -> Optional[MultipleArguments]:
        args = [arg.strip() for arg in re.split(r'[ ,]', argument, 1)]
        if len(args) != 2:
            raise commands.CommandError("please include a `,` between arguments")
        return MultipleArguments(first=args[0], second=args[1])


class Location(commands.Converter):
    async def convert(self, ctx: Context, argument: str):
        async with ctx.typing():
            response = await ctx.bot.session.get(
                "https://api.weatherapi.com/v1/timezone.json",
                params=dict(key="0c5b47ed5774413c90b155456223004", q=argument),
            )
            if response.status == 200:
                data = await response.json()
                return data.get("location")
            raise commands.CommandError(f"Location **{argument}** not found")


class Emoji(commands.EmojiConverter):
    async def convert(self, ctx: "Context", argument: str) -> Optional[Union[discord.Emoji, discord.PartialEmoji]]:
        try:
            return await super().convert(ctx, argument)
        except commands.EmojiNotFound:
            try:
                unicodedata.name(argument)
            except Exception:
                try:
                    unicodedata.name(argument[0])
                except Exception:
                    raise commands.EmojiNotFound(argument)
            return argument


class Sticker(GuildStickerConverter):
    async def convert(self, ctx: "Context", argument: str) -> Optional[GuildSticker]:
        if argument.isnumeric():
            try:
                return await super().convert(ctx, argument)
            except GuildStickerNotFound:
                raise
        return await super().convert(ctx, argument)


class TextChannel(commands.TextChannelConverter):
    async def convert(self, ctx: Context, argument: str):
        argument = argument.replace(" ", "-")
        try:
            return await super().convert(ctx, argument)
        except Exception:
            pass
        if match := DISCORD_ID.match(argument):
            return ctx.guild.get_channel(int(match.group(1)))
        if match := DISCORD_CHANNEL_MENTION.match(argument):
            return ctx.guild.get_channel(int(match.group(1)))
        channel = discord.utils.find(
            lambda m: argument.lower() in m.name.lower(),
            ctx.guild.text_channels,
        )
        if channel:
            return channel
        raise discord.ext.commands.errors.ChannelNotFound(f"channel `{argument}` not found")


class CategoryChannel(commands.TextChannelConverter):
    async def convert(self, ctx: Context, argument: str):
        try:
            return await super().convert(ctx, argument)
        except Exception:
            pass
        if match := DISCORD_ID.match(argument):
            return ctx.guild.get_channel(int(match.group(1)))
        if match := DISCORD_CHANNEL_MENTION.match(argument):
            return ctx.guild.get_channel(int(match.group(1)))
        channel = discord.utils.find(
            lambda m: argument.lower() in m.name.lower(),
            ctx.guild.categories,
        )
        if channel:
            return channel
        raise discord.ext.commands.errors.ChannelNotFound(f"channel `{argument}` not found")


class VoiceChannel(commands.TextChannelConverter):
    async def convert(self, ctx: Context, argument: str):
        try:
            return await super().convert(ctx, argument)
        except Exception:
            pass
        if match := DISCORD_ID.match(argument):
            return ctx.guild.get_channel(int(match.group(1)))
        if match := DISCORD_CHANNEL_MENTION.match(argument):
            return ctx.guild.get_channel(int(match.group(1)))
        channel = discord.utils.find(
            lambda m: argument.lower() in m.name.lower(),
            ctx.guild.voice_channels,
        )
        if channel:
            return channel
        raise discord.ext.commands.errors.ChannelNotFound(f"channel `{argument}` not found")


class User(commands.UserConverter):
    async def convert(self, ctx: Context, argument: str):
        argument = str(argument)
        if match := DISCORD_ID.match(argument):
            member = ctx.bot.get_user(int(match.group(1))) or await ctx.bot.fetch_user(int(match.group(1)))
        elif match := DISCORD_USER_MENTION.match(argument):
            member = ctx.bot.get_user(int(match.group(1))) or await ctx.bot.fetch_user(int(match.group(1)))
        else:
            member = discord.utils.find(
                lambda m: argument.lower() in (m.name.lower(), m.display_name.lower(), str(m).lower()),
                ctx.bot.users
            )
        if not member:
            raise commands.UserNotFound(argument)
        return member


class Member(commands.MemberConverter):
    async def convert(self, ctx: Context, argument: str):
        argument = str(argument)
        if match := DISCORD_ID.match(argument):
            member = ctx.guild.get_member(int(match.group(1)))
        elif match := DISCORD_USER_MENTION.match(argument):
            member = ctx.guild.get_member(int(match.group(1)))
        else:
            return await commands.MemberConverter().convert(ctx, argument)
        if not member:
            raise commands.MemberNotFound(argument)
        return member


class RolePosition(commands.CommandError):
    def __init__(self, message, **kwargs):
        self.message = message
        self.kwargs = kwargs
        super().__init__(self.message)


link = re.compile(
    r"https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/\/=]*(?:\.png|\.jpe?g|\.gif|\.jpg|))"
)


async def get_file_ext(url: str) -> str:
    file_ext1 = url.split("/")[-1].split(".")[1]
    return file_ext1.split("?")[0] if "?" in file_ext1 else file_ext1[:3]


class Image(commands.Converter):
    async def convert(self, ctx: Context, argument: str = None) -> Optional[bytes]:
        if argument is None:
            if not ctx.message.attachments:
                raise commands.BadArgument("No image was provided.")
            return await ctx.message.attachments[0].to_file()
        async with Session() as session:
            async with session.request("GET", argument) as response:
                data = await response.read()
        if not data:
            raise commands.BadArgument("No image was provided.")
        return data


class VoiceMessage(commands.Converter):
    async def convert(self, ctx: "Context", argument: str = None, fail: bool = True) -> typing.Optional[str]:
        if match := link.match(argument):
            return match.group()
        if fail:
            with suppress(Exception):
                await ctx.send_help(ctx.command.qualified_name)
            assert False

    @staticmethod
    async def search(ctx: "Context", fail: bool = True) -> typing.Optional[str]:
        async for message in ctx.channel.history(limit=50):
            if message.attachments:
                return message.attachments[0].url
        if fail:
            with suppress(Exception):
                await ctx.send_help(ctx.command.qualified_name)
            assert False


class Stickers(commands.Converter):
    async def convert(self, ctx: "Context", argument: str, fail: bool = True) -> typing.Optional[str]:
        if match := link.match(argument):
            return match.group()
        if fail:
            with suppress(Exception):
                await ctx.send_help(ctx.command.qualified_name)
            assert False

    @staticmethod
    async def search(ctx: "Context", fail: bool = True) -> typing.Optional[str]:
        if ctx.message.reference:
            return ctx.message.reference.resolved.stickers[0].url
        async for message in ctx.channel.history(limit=50):
            if message.stickers:
                return message.stickers[0].url
        if fail:
            with suppress(Exception):
                await ctx.send_help(ctx.command.qualified_name)
            assert False


class Attachment(commands.Converter):
    async def convert(self, ctx: "Context", argument: str, fail: bool = True) -> typing.Optional[str]:
        if match := link.match(argument):
            return match.group()
        if fail:
            with suppress(Exception):
                await ctx.send_help(ctx.command.qualified_name)
            assert False

    @staticmethod
    async def search(ctx: "Context", fail: bool = False) -> typing.Optional[str]:
        if ref := ctx.message.reference:
            logger.info(f"attachment search has a reference")
            if channel := ctx.guild.get_channel(ref.channel_id):
                if message := await channel.fetch_message(ref.message_id):
                    try:
                        return message.attachments[0].url
                    except Exception as e:
                        logger.info(f"attachment.search failed with {str(e)}")
        if ctx.message.attachments:
            logger.info("message attachments exist")
            return ctx.message.attachments[0].url
        if fail:
            with suppress(Exception):
                await ctx.send_help(ctx.command.qualified_name)
            assert False
        return None


class Message(commands.MessageConverter):
    async def convert(self, ctx: Context, argument: str):
        if "discord.com/channels/" in argument:
            guild_id, channel_id, message_id = argument.split("/channels/")[1].split("/")
            if guild := ctx.bot.get_guild(guild_id):
                if channel := guild.get_channel(channel_id):
                    return await channel.fetch_message(message_id)
        return await ctx.channel.fetch_message(argument)


class NonAssignedRole(commands.RoleConverter):
    async def convert(self, ctx: Context, arg: str):
        arguments = re.split(r'[ ,]', arg)
        roles = []
        for argument in arguments:
            argument = argument.strip()
            if match := DISCORD_ID.match(argument):
                role = ctx.guild.get_role(int(match.group(1)))
            elif match := DISCORD_ROLE_MENTION.match(argument):
                role = ctx.guild.get_role(int(match.group(1)))
            else:
                role = discord.utils.find(
                    lambda r: argument.lower() in r.name.lower(), ctx.guild.roles
                )
            if not role or role.is_default():
                raise commands.RoleNotFound(argument)
            roles.append(role)
        return roles


class Role(commands.RoleConverter):
    def __init__(self, assign: bool = True):
        self.assign = assign

    async def convert(self, ctx: Context, arg: str):
        arguments = re.split(r'[ ,]', arg)
        roles = []
        for argument in arguments:
            argument = argument.strip()
            role = None
            try:
                role = await super().convert(ctx, argument)
            except Exception:
                pass
            _roles = {r.name: r for r in ctx.guild.roles if r.is_assignable()}
            if role is None:
                if match := DISCORD_ID.match(argument):
                    role = ctx.guild.get_role(int(match.group(1)))
                elif match := DISCORD_ROLE_MENTION.match(argument):
                    role = ctx.guild.get_role(int(match.group(1)))
                else:
                    if match := closest_match(argument.lower(), list(_roles.keys())):
                        role = _roles.get(match)
                if not role or role.is_default():
                    raise commands.RoleNotFound(argument)
            if self.assign:
                if role < ctx.author.top_role or ctx.author.id == ctx.guild.owner_id:
                    if role <= ctx.guild.me.top_role or ctx.author.id in ctx.bot.owner_ids or ctx.author.id == ctx.guild.owner_id:
                        roles.append(role)
                    else:
                        raise RolePosition(f"{role.mention} is **above my role**")
                else:
                    m = "the same as your top role" if role == ctx.author.top_role and ctx.author != ctx.guild.owner else "above your top role"
                    raise RolePosition(f"{role.mention} is **{m}**")
            else:
                roles.append(role)
        return roles


class Command(commands.Command):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def invoke_command(self, ctx):
        await super().invoke(ctx)

    async def invoke(self, ctx: commands.Context, /):
        data = await ctx.bot.db.fetchrow(
            "SELECT * FROM disabled_commands WHERE guild_id = $1 AND command = $2",
            ctx.guild.id,
            ctx.command.qualified_name,
        )
        if data and data.status and data.whitelist and ctx.author.id in data.whitelist:
            return await self.invoke_command(ctx)
        elif data and data.status:
            return await ctx.reply("This command is disabled in this server.")
        return await self.invoke_command(ctx)


def Feature(*args, **kwargs):
    return commands.command(cls=Command, *args, **kwargs)
