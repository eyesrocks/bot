from discord.ext.commands import Cog
from .player import CoffinPlayer, Context
from typing import cast
from wavelink import TrackEndEventPayload, TrackStartEventPayload
from contextlib import suppress
from discord import Client, HTTPException
class MusicEvents(Cog):
    def __init__(self, bot: Client):
        self.bot = bot

    @Cog.listener()
    async def on_wavelink_track_end(self, payload: TrackEndEventPayload):
        client = cast(CoffinPlayer, payload.player)
        if not client:
            return

        if client.queue:
            await client.play(client.queue.get())

    def is_privileged(self, ctx: Context):
        """Check whether the user is an Admin or DJ."""

        return (
            ctx.author in (ctx.voice_client.dj, ctx.voice_client.requester)
            or ctx.author.guild_permissions.kick_members
        )

    @Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackStartEventPayload) -> None:
        client = cast(CoffinPlayer, payload.player)
        track = payload.track

        if not client:
            return

        if client.context and track.source != "local":
            with suppress(HTTPException):
                await client.send_panel(track)

async def setup(bot: Client):
    await bot.add_cog(MusicEvents(bot))