from discord.ext.commands import Cog
from .player import CoffinPlayer, Context
from typing import cast, Dict, List, Optional, Union
from wavelink import TrackEndEventPayload, TrackStartEventPayload
from contextlib import suppress
from discord import Client, HTTPException, Member, VoiceState
import aiohttp
import time
import hashlib
import asyncio
import logging
from discord.ext import tasks
from config import Authorization


class MusicEvents(Cog):
    def __init__(self, bot: Client):
        self.bot = bot
        self.lastfm_now_playing_users = {}
        self.lastfm_scrobble_timers = {}
        self.lastfm_api_key = Authorization.LastFM.api_key
        self.lastfm_api_secret = Authorization.LastFM.api_secret
        self.scrobble_task.start()

    def cog_unload(self):
        self.scrobble_task.cancel()

    @Cog.listener()
    async def on_wavelink_track_end(self, payload: TrackEndEventPayload):
        client = cast(CoffinPlayer, payload.player)
        if not client:
            return

        if client.guild.id in self.lastfm_now_playing_users:
            del self.lastfm_now_playing_users[client.guild.id]

        for user_id, timer_data in list(self.lastfm_scrobble_timers.items()):
            if timer_data.get("guild_id") == client.guild.id:
                del self.lastfm_scrobble_timers[user_id]

        if client.queue:
            await client.play(client.queue.get())

    def is_privileged(self, ctx: Context):
        """Check whether the user is an Admin or DJ."""

        return (
            ctx.author in (ctx.voice_client.dj, ctx.voice_client.requester)
            or ctx.author.guild_permissions.kick_members
        )

    async def get_lastfm_api_credentials(self):
        """Get LastFM API credentials from the database or environment"""
        if self.lastfm_api_key and self.lastfm_api_secret:
            return self.lastfm_api_key, self.lastfm_api_secret

    async def get_users_with_session_keys(
        self, guild_id: int
    ) -> Dict[int, Dict[str, str]]:
        """Get all users in a voice channel with LastFM session keys"""
        result = {}

        try:
            player = None
            for p in self.bot.voice_clients:
                if isinstance(p, CoffinPlayer) and p.guild.id == guild_id:
                    player = p
                    break

            if not player or not player.channel:
                return result

            members = player.channel.members

            members = [m for m in members if not m.bot]

            for member in members:
                session_data = await self.get_user_lastfm_session(member.id)
                if session_data:
                    result[member.id] = session_data

        except Exception as e:
            logging.error(f"Error getting users with session keys: {e}")

        return result

    async def get_user_lastfm_session(self, user_id: int) -> Optional[Dict[str, str]]:
        """Get LastFM session key and username for a user"""
        try:
            data = await self.bot.db.fetchrow(
                "SELECT username, session_key FROM lastfm.conf WHERE user_id = $1",
                user_id,
            )

            if data and data["session_key"]:
                return {
                    "username": data["username"],
                    "session_key": data["session_key"],
                }
        except Exception as e:
            logging.error(f"Error getting LastFM session for user {user_id}: {e}")

        return None

    async def update_lastfm_now_playing(
        self, guild_id: int, track_data: Dict[str, str]
    ):
        """Update now playing status for all users in the voice channel with LastFM session keys"""
        try:
            users_data = await self.get_users_with_session_keys(guild_id)
            if not users_data:
                return 0

            api_key, api_secret = await self.get_lastfm_api_credentials()
            if not api_key or not api_secret:
                logging.warning(
                    "LastFM API credentials not available, skipping now playing update"
                )
                return 0

            self.lastfm_now_playing_users[guild_id] = list(users_data.keys())

            current_time = int(time.time())
            for user_id, user_data in users_data.items():
                try:
                    duration = track_data.get("duration", 240)
                    scrobble_time = min(duration // 2, 240)

                    self.lastfm_scrobble_timers[user_id] = {
                        "guild_id": guild_id,
                        "track_data": track_data,
                        "scrobble_time": current_time + scrobble_time,
                        "session_key": user_data["session_key"],
                        "username": user_data["username"],
                    }
                except Exception as e:
                    logging.error(
                        f"Error setting up scrobble timer for user {user_id}: {e}"
                    )

            successful_updates = 0
            for user_id, user_data in users_data.items():
                try:
                    session_key = user_data["session_key"]
                    success = await self._send_lastfm_now_playing(
                        session_key, track_data, api_key, api_secret
                    )
                    if success:
                        successful_updates += 1
                except Exception as e:
                    logging.error(f"Error updating now playing for user {user_id}: {e}")

            logging.info(
                f"Updated LastFM now playing for {successful_updates}/{len(users_data)} users in guild {guild_id}"
            )
            return len(users_data)
        except Exception as e:
            logging.error(f"Error in update_lastfm_now_playing: {e}")
            return 0

    async def _send_lastfm_now_playing(
        self,
        session_key: str,
        track_data: Dict[str, str],
        api_key: str,
        api_secret: str,
    ):
        """Send now playing update to LastFM"""
        try:
            params = {
                "method": "track.updateNowPlaying",
                "artist": track_data["artist"],
                "track": track_data["track"],
                "api_key": api_key,
                "sk": session_key,
            }

            if "album" in track_data and track_data["album"]:
                params["album"] = track_data["album"]

            if "duration" in track_data and track_data["duration"]:
                params["duration"] = str(track_data["duration"])

            sig_content = "".join([f"{k}{params[k]}" for k in sorted(params.keys())])
            sig_content += api_secret
            api_sig = hashlib.md5(sig_content.encode()).hexdigest()
            params["api_sig"] = api_sig
            params["format"] = "json"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://ws.audioscrobbler.com/2.0/", data=params
                ) as resp:
                    if resp.status != 200:
                        response_text = await resp.text()
                        logging.error(
                            f"LastFM now playing update failed: {response_text}"
                        )
                        return False

                    return True

        except Exception as e:
            logging.error(f"Error updating LastFM now playing: {e}")
            return False

    async def _send_lastfm_scrobble(
        self,
        session_key: str,
        track_data: Dict[str, str],
        timestamp: int,
        api_key: str,
        api_secret: str,
    ):
        """Send scrobble to LastFM"""
        try:
            params = {
                "method": "track.scrobble",
                "artist": track_data["artist"],
                "track": track_data["track"],
                "timestamp": str(timestamp),
                "api_key": api_key,
                "sk": session_key,
            }

            if "album" in track_data and track_data["album"]:
                params["album"] = track_data["album"]

            sig_content = "".join([f"{k}{params[k]}" for k in sorted(params.keys())])
            sig_content += api_secret
            api_sig = hashlib.md5(sig_content.encode()).hexdigest()
            params["api_sig"] = api_sig
            params["format"] = "json"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://ws.audioscrobbler.com/2.0/", data=params
                ) as resp:
                    if resp.status != 200:
                        response_text = await resp.text()
                        logging.error(f"LastFM scrobble failed: {response_text}")
                        return False

                    return True

        except Exception as e:
            logging.error(f"Error scrobbling to LastFM: {e}")
            return False

    @tasks.loop(seconds=30)
    async def scrobble_task(self):
        """Task to check and process pending scrobbles"""
        current_time = int(time.time())

        for user_id, timer_data in list(self.lastfm_scrobble_timers.items()):
            if timer_data["scrobble_time"] <= current_time:
                api_key, api_secret = await self.get_lastfm_api_credentials()
                if api_key and api_secret:
                    try:
                        session_key = timer_data["session_key"]
                        track_data = timer_data["track_data"]
                        timestamp = int(time.time())

                        success = await self._send_lastfm_scrobble(
                            session_key, track_data, timestamp, api_key, api_secret
                        )

                        if success:
                            logging.info(
                                f"Successfully scrobbled track for user {user_id}"
                            )
                    except Exception as e:
                        logging.error(f"Error scrobbling track for user {user_id}: {e}")
                else:
                    logging.warning(
                        f"Cannot scrobble for user {user_id} - API credentials not available"
                    )

                del self.lastfm_scrobble_timers[user_id]

    @scrobble_task.before_loop
    async def before_scrobble_task(self):
        await self.bot.wait_until_ready()

    @Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackStartEventPayload) -> None:
        client = cast(CoffinPlayer, payload.player)
        track = payload.track

        if not client:
            return

        if client.context and track.source != "local":
            track_title = track.title
            if track.source.startswith("youtube"):
                track_title = await client.deserialize(track.title)

            artist = track.author
            title = track_title

            if " - " in track_title:
                parts = track_title.split(" - ", 1)
                artist = parts[0].strip()
                title = parts[1].strip()

            track_data = {
                "artist": artist,
                "track": title,
                "album": "",
                "duration": track.length // 1000,  # Convert ms to seconds
            }

            scrobbling_users_count = await self.update_lastfm_now_playing(
                client.guild.id, track_data
            )

            await client.send_panel(track, scrobbling_users_count)

    @Cog.listener()
    async def on_voice_state_update(
        self, member: Member, before: VoiceState, after: VoiceState
    ):
        if member.bot:
            return

        if before.channel != after.channel:
            if after.channel and not before.channel:
                try:
                    guild_id = after.channel.guild.id

                    player = None
                    for p in self.bot.voice_clients:
                        if isinstance(p, CoffinPlayer) and p.guild.id == guild_id:
                            player = p
                            break

                    if (
                        player
                        and player.channel
                        and player.channel.id == after.channel.id
                        and player.current
                    ):
                        session_data = await self.get_user_lastfm_session(member.id)
                        if session_data:
                            track = player.current

                            track_title = track.title
                            if track.source.startswith("youtube"):
                                track_title = await player.deserialize(track.title)

                            artist = track.author
                            title = track_title

                            if " - " in track_title:
                                parts = track_title.split(" - ", 1)
                                artist = parts[0].strip()
                                title = parts[1].strip()

                            track_data = {
                                "artist": artist,
                                "track": title,
                                "album": "",
                                "duration": track.length
                                // 1000,  # Convert ms to seconds
                            }

                            api_key, api_secret = (
                                await self.get_lastfm_api_credentials()
                            )
                            if api_key and api_secret:
                                await self._send_lastfm_now_playing(
                                    session_data["session_key"],
                                    track_data,
                                    api_key,
                                    api_secret,
                                )

                                if guild_id not in self.lastfm_now_playing_users:
                                    self.lastfm_now_playing_users[guild_id] = []

                                if (
                                    member.id
                                    not in self.lastfm_now_playing_users[guild_id]
                                ):
                                    self.lastfm_now_playing_users[guild_id].append(
                                        member.id
                                    )

                                current_time = int(time.time())
                                track_position = player.position // 1000
                                duration = track.length // 1000
                                remaining_time = duration - track_position

                                if remaining_time > 30:
                                    scrobble_time = min(remaining_time // 2, 240)
                                    self.lastfm_scrobble_timers[member.id] = {
                                        "guild_id": guild_id,
                                        "track_data": track_data,
                                        "scrobble_time": current_time + scrobble_time,
                                        "session_key": session_data["session_key"],
                                        "username": session_data["username"],
                                    }

                                await player.refresh_panel()
                except Exception as e:
                    logging.error(f"Error handling voice state update: {e}")

            elif before.channel and not after.channel:
                try:
                    guild_id = before.channel.guild.id

                    if (
                        guild_id in self.lastfm_now_playing_users
                        and member.id in self.lastfm_now_playing_users[guild_id]
                    ):
                        self.lastfm_now_playing_users[guild_id].remove(member.id)

                    if member.id in self.lastfm_scrobble_timers:
                        del self.lastfm_scrobble_timers[member.id]

                    player = None
                    for p in self.bot.voice_clients:
                        if isinstance(p, CoffinPlayer) and p.guild.id == guild_id:
                            player = p
                            break

                    if player:
                        await player.refresh_panel()
                except Exception as e:
                    logging.error(f"Error handling voice state update: {e}")


async def setup(bot: Client):
    await bot.add_cog(MusicEvents(bot))
