from discord.ext.commands import (
    Cog,
    Context,
    CommandError,
    CheckFailure,  # type: ignore
    BotMissingPermissions,
)
from typing import Union
import discord
import traceback
from discord.ext import commands
from tool.aliases import (  # type: ignore
    handle_aliases,
    CommandAlias,  # type: ignore
)
from tool.snipe import SnipeError  # type: ignore
from tool.important.subclasses.command import RolePosition  # type: ignore
from tool.important.subclasses.parser import EmbedError  # type: ignore
from loguru import logger
from discord.errors import HTTPException
from tool.processing import codeblock  # type: ignore
from aiohttp.client_exceptions import (
    ClientConnectorError,
    ClientResponseError,
    ContentTypeError,
    ClientProxyConnectionError,
    ClientHttpProxyError,
)
from tool.exceptions import InvalidSubCommand
from cogs.economy import OverMaximum
from cogs.moderation import InvalidError


def multi_replace(text: str, to_replace: dict, once: bool = False) -> str:
    for r1, r2 in to_replace.items():
        if r1 in text:
            if once:
                text = text.replace(str(r1), str(r2), 1)
            else:
                text = text.replace(str(r1), str(r2))

    return text


def get_message(parameter: str) -> str:
    """
    Returns a grammatically correct message indicating a missing parameter.

    Args:
        parameter (str): The name of the missing parameter.

    Returns:
        str: A message indicating the missing parameter with correct grammar.
    """
    vowels = "aeiouAEIOU"
    article = (
        "an"
        if parameter[0] in vowels and parameter.lower() not in ("user", "member")
        else "a"
    )
    return f"Provide {article} **{parameter.title()}**"


class Errors(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.debug = False
        self.ignored = (
            commands.CommandNotFound,
            CheckFailure,
            OverMaximum,
            commands.DisabledCommand,
            commands.NotOwner
        )

        self.error_messages = {
            "member_not_found": "I couldn't find that **member**.",
            "user_not_found": "I couldn't find that **user**.",
            "role_not_found": "I couldn't find that **role**.",
            "channel_not_found": "I couldn't find that **channel**.",
            "emoji_not_found": "I couldn't find that **emoji**.",
            "missing_perms": "I am missing sufficient permissions!"
        }

    async def _check_ratelimit(self, ctx: Context, key: str, limit: int, cooldown: float) -> bool:
        """Unified rate limit checking"""
        return await self.bot.glory_cache.ratelimited(
            f"rl:{key}:{ctx.author.id}", limit, cooldown
        )

    def log_error(self, ctx: Context, error: Exception, level: str = "error") -> None:
        """Enhanced error logging with context"""
        exc = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        log_message = (
            f"Error: {type(error).__name__}\n"
            f"Guild: {ctx.guild.id} | Author: {ctx.author.id}\n"
            f"Command: {ctx.command}\n"
            f"Message: {ctx.message.content}\n"
            f"Error Details: {exc}"
        )
        getattr(logger, level)(log_message)

    async def handle_api_errors(self, ctx: Context, error: Exception) -> bool:
        """Handle common API-related errors"""
        if isinstance(error, (ClientProxyConnectionError, ClientHttpProxyError, ClientConnectorError)):
            if await self._check_ratelimit(ctx, "api_error", 1, 5):
                return True
            await ctx.warning("The **API** is currently unavailable. Please try again later.")
            return True
            
        if isinstance(error, ClientResponseError):
            if await self._check_ratelimit(ctx, "api_error", 1, 5):
                return True
            message = f"API Error: Status {error.status}"
            if error.message:
                message += f" - {error.message}"
            await ctx.warning(message)
            return True
            
        return False

    async def handle_discord_errors(self, ctx: Context, error: Exception) -> bool:
        """Handle Discord-specific errors"""
        if isinstance(error, HTTPException):
            if error.code in [50013, 50045, 60003]:
                if await self._check_ratelimit(ctx, "discord_error", 1, 5):
                    return True
                await ctx.warning(self._get_http_error_message(error))
                return True

        if isinstance(error, discord.NotFound):
            if await self._check_ratelimit(ctx, "not_found", 1, 5):
                return True
            await ctx.warning(self._get_not_found_message(error.code))
            return True

        return False

    def _get_http_error_message(self, error: HTTPException) -> str:
        """Get appropriate message for HTTP errors"""
        if error.code == 50013:
            return self.error_messages["missing_perms"]
        elif error.code == 50045:
            return "The provided asset is too large!"
        elif error.code == 60003:
            return "2FA authentication is required for this action."
        return f"An error occurred: {error.text}"

    def _get_not_found_message(self, code: str) -> str:
        """Get appropriate message for NotFound errors"""
        return {
            "10003": self.error_messages["channel_not_found"],
            "10007": self.error_messages["member_not_found"],
            "10008": "**Message** not found",
            "10011": self.error_messages["role_not_found"],
            "10013": self.error_messages["user_not_found"],
            "10014": self.error_messages["emoji_not_found"],
            "10015": "**Webhook** not found"
        }.get(code, "The requested resource was not found.")

    async def handle_exceptions(self, ctx: Context, exception: Exception) -> None:
        """Main error handler with improved flow control"""
        if isinstance(exception, self.ignored) or type(exception) in self.ignored:
            return

        if isinstance(exception, commands.CommandOnCooldown):
            if ctx.author.name == "aiohttp":
                await ctx.reinvoke()
            
            if not await self._check_ratelimit(ctx, "cooldown", 1, 5):
                await ctx.warning(f"Command is on a `{exception.retry_after:.2f}s` **cooldown**")
            return

        if await self.handle_api_errors(ctx, exception):
            return

        if await self.handle_discord_errors(ctx, exception):
            return

        if self.debug:
            self.log_error(ctx, exception)

        if not await self._check_ratelimit(ctx, "error", 3, 5):
            if isinstance(exception, CommandError):
                await ctx.warning(str(exception))
            else:
                await self.bot.send_exception(ctx, exception)

    @Cog.listener("on_command_error")
    async def on_error(self, ctx: Context, exception: Exception):
        try:
            await self.handle_exceptions(ctx, exception)
        except Exception as e:
            self.log_error(ctx, e)

    @commands.command(name="debug", hidden=True, brief="enable or disable debug mode")
    @commands.is_owner()
    async def set_debug(self, ctx: Context, state: bool):
        self.debug = state
        if state is True:
            m = "**Enabled** debug mode"
        else:
            m = "**Disabled** debug mode"
        return await ctx.success(m)


async def setup(bot):
    await bot.add_cog(Errors(bot))
