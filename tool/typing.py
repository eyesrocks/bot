import asyncio
import discord
from discord.ext import commands


def _typing_done_callback(fut: asyncio.Future) -> None:
    try:
        fut.exception()
    except (asyncio.CancelledError, Exception):
        pass


class Typing:
    def __init__(self, ctx: commands.Context) -> None:
        self.loop: asyncio.AbstractEventLoop = ctx._state.loop
        self.messageable: discord.Message = ctx.message
        self.command: commands.Command = ctx.command
        self.bot: commands.Bot = ctx.bot
        self.guild: discord.Guild = ctx.guild
        self.author: discord.Member = ctx.author
        self.channel: discord.TextChannel = ctx.channel
        self.ctx: commands.Context = ctx
        self.task: asyncio.Task[None] = None

    async def wrapped_typer(self) -> None:
        await self.channel.trigger_typing()

    def __await__(self):
        return self.wrapped_typer().__await__()

    async def do_typing(self) -> None:
        while True:
            await self.channel.trigger_typing()
            await asyncio.sleep(5)

    async def __aenter__(self) -> None:
        await self.channel.trigger_typing()
        self.task = self.loop.create_task(self.do_typing())
        self.task.add_done_callback(_typing_done_callback)

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc: BaseException,
        tb: asyncio.TracebackType,
    ) -> None:
        if self.task:
            self.task.cancel()
