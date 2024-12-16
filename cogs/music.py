from tool.greed import Greed  # type: ignore
from humanize import naturaldelta
from datetime import timedelta
from typing import Optional, Union, Literal
from tool import expressions as regex
import discord
import pomice
import asyncio
import async_timeout
import random
import orjson
import traceback
from discord.ext import tasks, commands
from discord.ext.commands import Context
from tuuid import tuuid
from loguru import logger
from contextlib import suppress
from enum import Enum

class LoopMode(Enum):
    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"

play_emoji = "<:greed_play:1207661064096063599>"
skip_emoji = "<:greed_skip:1207661069938589716>"
pause_emoji = "<:greed_pause:1207661063093620787>"
replay_emoji = "<:greed_replay:1207661068856598528>"
queue_emoji = "<:greed_queue:1207661066620764192>"

class Player(pomice.Player):    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bound_channel: Optional[discord.TextChannel] = None
        self._current_message: Optional[discord.Message] = None
        self._current_track: Optional[pomice.Track] = None
        self._context: Optional[commands.Context] = None
        self._waiting: bool = False
        self._loop_mode: LoopMode = LoopMode.OFF
        self._volume: int = 65
        self._active_filters: set[str] = set()
        self.queue = asyncio.Queue()

    @property
    def current(self) -> Optional[pomice.Track]:
        """The currently playing track."""
        return self._current_track

    @current.setter 
    def current(self, value: Optional[pomice.Track]):
        self._current_track = value

    @property
    def context(self) -> Optional[commands.Context]:
        """The context of the player's invocation."""
        return self._context

    @context.setter
    def context(self, value: Optional[commands.Context]):
        self._context = value

    @property
    def bound_channel(self) -> Optional[discord.TextChannel]:
        """The text channel the player is bound to."""
        if not self._bound_channel and self.guild:
            try:
                if self.channel and self.channel.category:
                    self._bound_channel = next(
                        (c for c in self.channel.category.text_channels 
                         if c.permissions_for(self.guild.me).send_messages), 
                        None
                    )
                if not self._bound_channel:
                    self._bound_channel = next(
                        (c for c in self.guild.text_channels 
                         if c.permissions_for(self.guild.me).send_messages),
                        None
                    )
            except Exception as e:
                logger.error(f"Error finding bound channel: {e}")
        return self._bound_channel

    @bound_channel.setter
    def bound_channel(self, value: Optional[discord.TextChannel]):
        self._bound_channel = value

    @property 
    def loop(self) -> str:
        """The current loop mode."""
        return self._loop_mode.value

    @loop.setter
    def loop(self, value: Union[str, LoopMode, bool]):
        if isinstance(value, bool):
            self._loop_mode = LoopMode.TRACK if value else LoopMode.OFF
        elif isinstance(value, str):
            try:
                self._loop_mode = LoopMode(value.lower())
            except ValueError:
                self._loop_mode = LoopMode.OFF
        elif isinstance(value, LoopMode):
            self._loop_mode = value
        else:
            self._loop_mode = LoopMode.OFF

    async def _update_now_playing_message(self, track: pomice.Track):
        """Update the now playing message with track info."""
        if not self.bound_channel:
            logger.error("No bound channel for now playing message")
            return

        try:
            if self._current_message:
                with suppress(discord.HTTPException):
                    await self._current_message.delete()

            embed = discord.Embed(color=0x2B2D31)
            embed.description = f"> **Now playing** [**{track.title}**]({track.uri})"
            
            if track.track_type == pomice.TrackType.YOUTUBE:
                embed.set_image(url=track.thumbnail)
            else:
                embed.set_thumbnail(url=track.thumbnail)
            
            self._current_message = await self.bound_channel.send(embed=embed, view=MusicInterface(self.bot))

        except Exception as e:
            logger.error(f"Failed to update now playing message: {e}")
            self._bound_channel = None

    async def play(self, track: pomice.Track) -> Optional[bool]:
        """Play a track with error handling."""
        try:
            self._current_track = track
            
            if not self.bound_channel:
                raise ValueError("No bound channel available")

            # Ensure we call the parent class play method BEFORE updating message
            result = await super().play(track)
            
            # Only update the now playing message if the track started playing
            if result is not False:
                await self._update_now_playing_message(track)
                
            return result

        except Exception as e:
            logger.error(f"Error playing track: {e}")
            if self.context:
                await self.context.fail(f"Could not play **[{track.title}]({track.uri})**")
            
            if not self.queue.empty():
                try:
                    self.queue._queue = [t for t in self.queue._queue if t != track]
                    if self.queue._queue:
                        next_track = self.queue._queue[0] 
                        await self.play(next_track)
                    else:
                        await self.teardown()
                except Exception as e:
                    logger.error(f"Error handling queue: {e}")
            return None

    async def insert(self, track: pomice.Track, *, filter: bool = True, bump: bool = False) -> bool:
        """Insert a track into the queue with optional metadata filtering."""
        try:
            if filter and track.info.get("sourceName") == "youtube":
                async with self.bot.session.get(
                    "https://metadata-filter.vercel.app/api/youtube",
                    params={"track": track.title}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        track.title = data["data"].get("track", track.title)

            if bump:
                self.queue._queue.insert(0, track)
            else:
                await self.queue.put(track)
            return True

        except Exception as e:
            logger.error(f"Failed to insert track: {e}")
            return False

    async def next_track(self, ignore_playing: bool = False) -> Optional[pomice.Track]:
        """Get and play the next track in queue."""
        if not ignore_playing and (self.is_playing or self._waiting):
            return None

        self._waiting = True
        try:
            track = None
            
            # Handle loop modes
            if self._loop_mode == LoopMode.TRACK and self.current:
                track = self.current
            else:
                try:
                    async with async_timeout.timeout(300):
                        if not self.queue.empty():
                            track = await self.queue.get()
                            if self._loop_mode == LoopMode.QUEUE:
                                await self.queue.put(track)
                except asyncio.TimeoutError:
                    await self.teardown()
                    return None

            if track:
                # Actually play the track
                play_result = await self.play(track)
                if play_result is not False:
                    return track
                else:
                    logger.error(f"Failed to play track {track.title}")
                    return await self.next_track(ignore_playing=True)
            else:
                await self.teardown()
                return None

        except Exception as e:
            logger.error(f"Error in next_track: {e}")
            return None
        finally:
            self._waiting = False

    async def teardown(self):
        """Safely clean up player resources."""
        try:
            # Clear queue
            self.queue._queue.clear()
            
            # Reset filters
            await self.reset_filters()
            
            # Destroy player if it exists
            if self.guild and self.guild.id in self._node._players:
                await self.destroy()
            
            # Clean up message
            if self._current_message:
                with suppress(discord.HTTPException):
                    await self._current_message.delete()
                    
            # Reset state
            self._current_track = None
            self._current_message = None
            self._waiting = False
            self._loop_mode = LoopMode.OFF
            self._active_filters.clear()
            
        except Exception as e:
            logger.error(f"Error in teardown: {e}")

    @property
    def waiting(self) -> bool:
        return self._waiting

    @waiting.setter
    def waiting(self, value: bool):
        self._waiting = value

    @property
    def get_percentage(self) -> int:
        pos_seconds = self.position // 1000 if self.position else 0
        total_seconds = self.current.length // 1000 if self.current else 1
        return min(int((pos_seconds / total_seconds) * 100), 100)

    @property
    def progress(self) -> str:
        bar = "██"
        empty = "  "
        filled = self.get_percentage // 10
        return bar * filled + empty * (10 - filled)

    @property
    def volume_bar(self) -> str:
        filled_slots = self.volume // 10
        return "<a:CatJam:1304239102257922148>" * filled_slots + "<a:CatJam:1304239102257922148>" * (10 - filled_slots)
 

    async def get_tracks(
        self,
        query: str,
        *,
        ctx: Optional[commands.Context] = None,
        search_type: Optional[pomice.SearchType] = None,
    ) -> list[pomice.Track]:
        """Get tracks with context saving."""
        if ctx:
            self.context = ctx
        return await super().get_tracks(
            query=query, 
            ctx=ctx, 
            search_type=search_type or pomice.SearchType.scsearch
        )

    async def clear_queue(self):
        while not self.queue.empty():
            await self.queue.get()

    async def remove_track(self, track: pomice.Track):
        self.queue._queue = [t for t in self.queue._queue if t != track]

    async def skip(self):
        """Skip current track."""
        if self.is_paused:
            await self.set_pause(False)
        if self.loop == "track":
            await self.seek(self.current.length)
        else:
            await self.stop()

    async def set_loop(self, state: Union[str, bool]):
        """Set loop state."""
        self.loop = state

    async def add_filter(self, filter_type: str, fast_apply: bool = True) -> None:
        """Add a filter safely."""
        try:
            if isinstance(filter_type, str):
                if filter_type in self.filters:
                    raise pomice.FilterTagAlreadyInUse(filter_type)
                await super().add_filter(filter_type, fast_apply)
                self.filters.add(filter_type)
            else:
                # Handle filter objects (e.g. Timescale, Equalizer)
                filter_name = filter_type.__class__.__name__.lower()
                if filter_name in self.filters:
                    raise pomice.FilterTagAlreadyInUse(filter_name)
                await super().add_filter(filter_type, fast_apply)
                self.filters.add(filter_name)
        except Exception as e:
            logger.error(f"Error adding filter {filter_type}: {e}")
            raise

    async def remove_filter(self, filter_type: str, fast_apply: bool = True) -> None:
        """Remove a filter safely."""
        try:
            filter_name = filter_type.lower()
            if filter_name not in self.filters:
                raise pomice.FilterTagNotInUse(filter_name)
            await super().remove_filter(filter_name, fast_apply)
            self.filters.remove(filter_name)
        except Exception as e:
            logger.error(f"Error removing filter {filter_type}: {e}")
            raise

    def __repr__(self) -> str:
        return f"<Player guild={self.guild.id} connected={self.is_connected} playing={self.is_playing}>"

def fmtseconds(seconds: Union[int, float], unit: str = "microseconds") -> str:
    return naturaldelta(timedelta(seconds=seconds), minimum_unit=unit)

# Retrieve or connect a player
async def get_player(
    interaction: discord.Interaction,
    *,
    connect: bool = True,
    check_connected: bool = True,
) -> Optional[Player]:
    if not hasattr(interaction.client, "node"):
        raise commands.CommandError("The **Lavalink** node hasn't been **initialized** yet")

    user_voice = interaction.user.voice
    bot_voice = interaction.guild.me.voice

    if not user_voice:
        if check_connected:
            raise commands.CommandError("You're not **connected** to a voice channel")
        return None

    if bot_voice and bot_voice.channel != user_voice.channel:
        raise commands.CommandError("I'm **already** connected to another voice channel")

    player = interaction.client.node.get_player(interaction.guild.id)
    if not player or not bot_voice:
        if not connect:
            if interaction.voice_client:
                await interaction.voice_client.disconnect()
                return None
            raise commands.CommandError("I'm not **connected** to a voice channel")
        await user_voice.channel.connect(cls=Player, self_deaf=True)
        player = interaction.client.node.get_player(interaction.guild.id)
        player.bound_channel = interaction.channel
        await interaction.voice_client.set_volume(65)

    return player

# Enqueue a track or playlist
async def enqueue(bot: Greed, interaction: discord.Interaction, query: str):
    try:
        player = await get_player(interaction)
    except Exception as e:
        traceback.print_exc()
        await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
        return

    if not player or player.channel.id != interaction.voice_client.channel.id:
        return await interaction.response.send_message("You are not in the voice channel with the bot", ephemeral=True)

    try:
        result = await interaction.voice_client.node.get_tracks(query=query, search_type=pomice.SearchType.scsearch)
    except pomice.TrackLoadError:
        match = regex.SOUNDCLOUD_TRACK_URL.match(query) or regex.SOUNDCLOUD_PLAYLIST_URL.match(query)
        if match:
            try:
                result = await player.node.get_tracks(query=f"ytsearch:{match.group('slug')}", search_type=pomice.SearchType.scsearch)
            except Exception:
                return await interaction.response.send_message("Could not find that track", ephemeral=True)
        else:
            result = None
    except (TypeError, KeyError):
        return await interaction.response.send_message("Music Node is currently rate-limited...", ephemeral=True)

    if not result:
        return await interaction.response.send_message("No **results** were found", ephemeral=True)

    if isinstance(result, pomice.Playlist):
        for track in result.tracks:
            await player.insert(track, filter=False)
        return await interaction.response.send_message(
            f"Added **{Plural(result.track_count):track}** from [**{result.name}**]({result.uri}) to the queue",
            ephemeral=True,
        )

    track = result[0]
    await player.insert(track)
    if player.is_playing:
        return await interaction.response.send_message(
            f"Added [**{track.title}**]({track.uri}) to the queue",
            ephemeral=True,
        )
    await player.next_track()
    if player.is_playing:
        return await interaction.response.send_message(
            f"**Now playing** [**{track.title}**]({track.uri})",
            ephemeral=True,
        )

    return await interaction.response.send_message("No voice client found", ephemeral=True)

# Play music
async def play(bot: Greed, interaction: discord.Interaction):
    player = bot.node.get_player(interaction.guild.id)
    if player:
        await player.set_pause(False)
        requester = player.current.requester if player.current else None
        if requester == interaction.user:
            embed = discord.Embed(description="**Resumed** this track", color=0x2D2B31)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await update_buttons(interaction, paused=False)
            return
    embed = discord.Embed(description="**Resumed** this track", color=0x2D2B31)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await update_buttons(interaction, paused=False)

# Pause music
async def pause(bot: Greed, interaction: discord.Interaction):
    player = bot.node.get_player(interaction.guild.id)
    if player:
        if player.current and player.current.requester != interaction.user:
            return
        await player.set_pause(True)
        embed = discord.Embed(description="**Paused** this track", color=0x2D2B31)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await update_buttons(interaction, paused=True)

# Skip music
async def skip(bot: Greed, interaction: discord.Interaction):
    player = bot.node.get_player(interaction.guild.id)
    if player:
        if player.current and player.current.requester != interaction.user:
            return
        await player.skip()
        embed = discord.Embed(description="**Skipped** this track", color=0x2D2B31)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Replay music
async def replay(bot: Greed, interaction: discord.Interaction):
    player = bot.node.get_player(interaction.guild.id)
    if player:
        if player.loop:
            await player.set_loop(False)
            description = "**No longer looping** the queue"
        else:
            await player.set_loop(True)
            description = "Now **looping** the queue"
        embed = discord.Embed(description=description, color=0x2D2B31)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Update music control buttons
async def update_buttons(interaction: discord.Interaction, paused: bool):
    view = MusicInterface(interaction.client)
    for child in view.children:
        if isinstance(child, discord.ui.Button):
            if paused and child.custom_id == "music:play":
                child.style = discord.ButtonStyle.blurple
                child.emoji = play_emoji
                child.custom_id = "music:play"
            elif not paused and child.custom_id == "music:pause":
                child.style = discord.ButtonStyle.gray
                child.emoji = pause_emoji
                child.custom_id = "music:pause"
    await interaction.edit_original_response(view=view)

# Chunk a list into smaller parts
def chunk_list(data: list, amount: int) -> list:
    return [list(chunk) for chunk in zip(*[iter(data)] * amount)]

# Define music interface view class
class MusicInterface(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=replay_emoji, custom_id="music:replay")
    async def replay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await replay(self.bot, interaction)

    @discord.ui.button(style=discord.ButtonStyle.gray, emoji=pause_emoji, custom_id="music:pause")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await pause(self.bot, interaction)

    @discord.ui.button(style=discord.ButtonStyle.blurple, emoji=play_emoji, custom_id="music:play")
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await play(self.bot, interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=skip_emoji, custom_id="music:skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await skip(self.bot, interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=queue_emoji, custom_id="music:queue")
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.bot.node.get_player(interaction.guild.id)
        if player and player.queue._queue:
            queue = [f"[{t.title}]({t.uri})" for t in player.queue._queue[:5]]
            description = "\n".join(queue)
        else:
            description = "No tracks found in queue"
        embed = discord.Embed(description=description, color=self.bot.color)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Plural:
    def __init__(self, value: int, bold: bool = False, code: bool = False):
        self.value = value
        self.bold = bold
        self.code = code

    def __format__(self, format_spec: str) -> str:
        return self.do_plural(format_spec)

    def do_plural(self, format_spec: str) -> str:
        v = len(self.value) if isinstance(self.value, list) else self.value
        formatted = f"**{v:,}**" if self.bold else f"`{v:,}`" if self.code else f"{v:,}"
        singular, _, plural = format_spec.partition("|")
        plural = plural or f"{singular}s"
        return f"{formatted} {plural if abs(v) != 1 else singular}"

def shorten(value: str, length: int = 20) -> str:
    return value[:length-2] + ".." if len(value) > length else value

def format_duration(duration: int, ms: bool = True) -> str:
    total_seconds = duration // 1000 if ms else duration
    seconds = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = (total_seconds // 3600) % 24
    parts = []
    if hours:
        parts.append(f"{hours:02d}")
    parts.append(f"{minutes:02d}")
    parts.append(f"{seconds:02d}")
    return ":".join(parts) if parts else "00:00"



class MusicError(commands.CommandError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message)
        self.kwargs = kwargs

async def auto_disconnect(bot: Greed, player: Player):
    await asyncio.sleep(60)
    if player.is_paused or not player.is_playing and not player.current and not player.queue._queue:
        await player.teardown()

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_autodisconnect.start()

    def cog_unload(self):
        self.music_autodisconnect.cancel()


    async def check_node(self):
        logger.info("Initializing LavaLink Node Pool....")
        spotify = self.bot.config.get("spotify")
        self.bot.node = await pomice.NodePool().create_node(
            bot=self.bot,
            host="[2602:fa48:0:3:9edc:71ff:fec7:cbc0]",
            port=2333,
            password="youshallnotpass1",
            identifier=f"MAIN{tuuid()}",
            spotify_client_id=spotify.get("client_id") if spotify else "d15ca7286e354306b231ca1fa918fc04",
            spotify_client_secret=spotify.get("client_secret") if spotify else "d5ec1357581b443c879f1e4d3d0e5608",
            apple_music=True,
        )
        logger.info("Created LavaLink Node Pool Connection")
        
    async def get_player(
        self, ctx: Context, *, connect: bool = True, check_connected: bool = True
    ) -> Optional[Player]:
        """Get or create a player instance for a guild."""
        try:
            if not hasattr(self.bot, "node"):
                await self.check_node()
                
            if check_connected and not ctx.author.voice:
                if not check_connected:
                    return None
                raise commands.CommandError("You must be in a voice channel")

            if (
                ctx.guild.me.voice 
                and ctx.guild.me.voice.channel 
                and ctx.author.voice
                and ctx.guild.me.voice.channel != ctx.author.voice.channel
            ):
                raise commands.CommandError("Already connected to different voice channel")

            player = self.bot.node.get_player(ctx.guild.id)
            
            if not player and not ctx.guild.me.voice:
                if not connect:
                    if ctx.voice_client:
                        return await ctx.voice_client.disconnect()
                    raise commands.CommandError("Not connected to voice channel")
                    
                try:
                    channel = ctx.author.voice.channel
                    player = await channel.connect(cls=Player, self_deaf=True)
                    if not player:
                        raise commands.CommandError("Failed to create player")
                        
                    # Initialize player attributes after connection
                    if hasattr(player, "__post_init__"):
                        player.__post_init__()
                        
                    player.bound_channel = ctx.channel
                    await player.set_volume(65)
                    
                except Exception as e:
                    if ctx.voice_client:
                        await ctx.voice_client.disconnect()
                    raise commands.CommandError(f"Failed to connect: {str(e)}")

            return player

        except Exception as e:
            logger.error(f"Error getting player: {e}")
            raise commands.CommandError(str(e))

    @tasks.loop(minutes=5)
    async def music_autodisconnect(self):
        """Safely check and disconnect inactive players."""
        try:
            if not hasattr(self.bot, "node"):
                await self.check_node()
                return

            for player in list(self.bot.node.players.values()):
                if isinstance(player, Player):
                    if not player.is_playing and player.is_paused:
                        await player.teardown()
        except Exception as e:
            logger.error(f"Error in autodisconnect: {e}")

    @commands.Cog.listener()
    async def on_pomice_track_end(self, player: pomice.Player, track: pomice.Track, reason: str):
        await player.next_track()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, reaction: discord.RawReactionActionEvent):
        data = await self.bot.redis.get(f"lfnp:{reaction.message_id}")
        if data:
            data = orjson.loads(data)
            if str(reaction.emoji) == str(data.get("up")):
                await self.bot.db.execute(
                    """INSERT INTO lastfm_likes (user_id, track, artist) VALUES($1, $2, $3) ON CONFLICT DO NOTHING""",
                    reaction.user_id,
                    data["track"],
                    data["artist"],
                )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, reaction: discord.RawReactionActionEvent):
        data = await self.bot.redis.get(f"lfnp:{reaction.message_id}")
        if data and str(reaction.emoji) == str(orjson.loads(data).get("up")):
            data = orjson.loads(data)
            await self.bot.db.execute(
                """DELETE FROM lastfm_likes WHERE user_id = $1 AND track = $2 AND artist = $3""",
                reaction.user_id,
                data["track"],
                data["artist"],
            )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel and self.bot.user in before.channel.members:
            player = self.bot.node.get_player(member.guild.id)
            if player and player.channel and len(player.channel.members) == 1:
                with suppress(Exception):
                    await player.teardown()
        if member.id != self.bot.user.id:
            return
        player = self.bot.node.get_player(member.guild.id) if hasattr(self.bot, "node") else None
        if player and not after.channel:
            await player.teardown()


    async def get_tracks(self, ctx: Context, player: Optional[Player], query: str, search_type: Optional[pomice.SearchType] = None):
        if not hasattr(self.bot, "node"):
            raise commands.CommandError("The Lavalink node hasn't been initialized yet")
            
        try:
            if player:
                return await player.get_tracks(query=query, ctx=ctx, search_type=search_type)
            else:
                return await self.bot.node.get_tracks(query=query, ctx=ctx, search_type=search_type)
        except Exception:
            search_type = pomice.SearchType.scsearch
            if player:
                return await player.get_tracks(query=query, ctx=ctx, search_type=search_type)
            else:
                return await self.bot.node.get_tracks(query=query, ctx=ctx, search_type=search_type)

    @commands.command(name="playing", aliases=["current", "nowplaying", "np"], brief="Show current playing song", example=",playing")
    async def playing(self, ctx: Context, member: Optional[discord.Member] = None):
        player: Player = await self.get_player(ctx, connect=False, check_connected=False)
        if player and player.current:
            embed = discord.Embed(title="Song", color=0x2B2D31)
            embed.description = (
                f"**Playing:** [**{shorten(player.current.title, 23)}**]({player.current.uri})\n"
                f"> **Time:** `{format_duration(player.position)}/{format_duration(player.current.length)}`\n"
                f"> **Progress:** `{player.get_percentage}%`\n"
                f"> ```{player.progress}```"
            )
            if player.current.thumbnail:
                embed.set_thumbnail(url=player.current.thumbnail)
            await ctx.send(embed=embed, view=MusicInterface(self.bot))
        else:
            await ctx.fail("no current track playing")

    async def handle_attachment(self, ctx: Context) -> Optional[str]:
        if ctx.message.attachments:
            for attachment in ctx.message.attachments:
                if attachment.filename.endswith(".mp3"):
                    return attachment.proxy_url
                else:
                    return await ctx.fail("Only **MP3's** can be played")
        return None

    @commands.command(name="play", aliases=["queue", "q", "p"], example=",play juice wrld", brief="Play a song")
    async def play_command(self, ctx: Context, *, query: Optional[str] = None):
        if not ctx.author.voice:
            return await ctx.fail("you aren't in a voice channel")
        if query is None: 
            if ctx.invoked_with in ("play", "p"):
                query = await self.handle_attachment(ctx)
                if not query:
                    return await ctx.send_help(ctx.command.qualified_name)
        player: Player = await self.get_player(ctx)
        if not query:
            player = self.bot.node.get_player(ctx.guild.id)
            if not player.current:
                return await ctx.fail("There isn't an active **track**")
            embeds = []
            if player.current:
                embed = discord.Embed(title=f"Queue for {player.channel.name}", color=0x2B2D31)
                embed.description = (
                    f"**Duration:** `{format_duration(player.position)}/{format_duration(player.current.length)}`\n"
                    f"> **Playing:** [**{shorten(player.current.title, 23)}**]({player.current.uri})\n"
                    f"> **Requested by:** {player.current.requester.mention if player.current.requester else ''}\n"
                )
                embeds.append(embed)
            for track in player.queue._queue:
                embed = embed.copy()
                embed.description += f"**Duration:** `00:00/{format_duration(track.length)}`\n> [**{shorten(track.title, 23)}**]({track.uri}) - {track.requester.mention if track.requester else ''}\n"
                embeds.append(embed)
            return await ctx.paginate(embeds)
        
        if isinstance(query, str) and query.lower() in ["-liked", "--liked", "liked"]:
            results, errors = [], []
            likes = await self.bot.db.fetch(
                "SELECT track, artist FROM lastfm_likes WHERE user_id = $1", ctx.author.id
            )
            for track, artist in likes:
                search_query = f"{track} by {artist}"
                try:
                    tracks = await self.get_tracks(ctx, player, search_query)
                    if tracks:
                        await player.insert(tracks[0], filter=False, bump=ctx.parameters.get("bump"))
                        results.append(f"[**{tracks[0].title}**]({tracks[0].uri})")
                    else:
                        errors.append(f"Failed to insert {search_query}")
                except Exception:
                    pass
            if results:
                await self.bot.paginate(ctx, discord.Embed(title="Tracks Queued", color=self.bot.color), results, 10)
        else:
            tracks = await self.get_tracks(ctx, player, query, pomice.SearchType.ytsearch)
            if not tracks:
                tracks = await self.get_tracks(ctx, player, query, pomice.SearchType.scsearch)
                if not tracks:
                    return await ctx.fail("No **results** were found")
            if isinstance(tracks, pomice.Playlist):
                for track in tracks.tracks:
                    if query.capitalize() in ["-bump", "--bump", "bump"]:
                        await player.insert(track, filter=False, bump=True)
                    await player.insert(track, filter=False, bump=False)
                await ctx.success(
                    f"Added **{Plural(tracks.track_count):track}** from [**{tracks.name}**]({tracks.uri}) to the queue",
                    emoji=queue_emoji,
                )
                if not player.is_playing and not player.is_paused:
                    await player.next_track()
            else:
                track = tracks[0]
                await player.insert(track, bump=ctx.parameters.get("bump"))
                if player.is_playing:
                    await ctx.success(
                        f"Added [**{track.title}**]({track.uri}) to the queue",
                        emoji=queue_emoji,
                    )
                else:
                    await player.next_track()
        
        if ctx.parameters.get("shuffle") and player.queue._queue:
            random.shuffle(player.queue._queue)
            await ctx.message.add_reaction("🔀")
        if not player.is_playing and player.queue._queue:
            await player.next_track()
        if player.bound_channel and player.bound_channel != ctx.channel:
            await ctx.message.add_reaction("✅")

    @commands.command(name="remove", aliases=["rmv"], brief="Remove a song from the queue", example=",remove 3")
    async def remove(self, ctx: Context, track: int):
        player: Player = await self.get_player(ctx, connect=False)
        if 1 <= track <= len(player.queue._queue):
            removed = player.queue._queue.pop(track - 1)
            await ctx.success(f"Removed [**{removed.title}**]({removed.uri}) from the queue")
        else:
            await ctx.fail(f"Track position `{track}` is invalid (`1`/`{len(player.queue._queue)}`)")

    @commands.command(name="shuffle", aliases=["mix"], brief="Shuffle the queue", example=",shuffle")
    async def shuffle(self, ctx: Context):
        player: Player = await self.get_player(ctx, connect=False)
        if player.queue._queue:
            random.shuffle(player.queue._queue)
            await ctx.message.add_reaction("🔀")
        else:
            await ctx.fail("There aren't any **tracks** in the queue")

    @commands.command(name="skip", aliases=["next", "sk"], brief="Skip the current song", example=",skip")
    async def skip(self, ctx: Context):
        player: Player = await self.get_player(ctx, connect=False)
        if player.is_playing:
            await ctx.success("**Skipped** this song")
            await player.skip()
        else:
            await ctx.fail("There isn't an active **track**")

    @commands.command(name="loop", aliases=["repeat", "lp"], brief="Toggle looping", example=",loop queue")
    async def loop(self, ctx: Context, option: Optional[str] = None):
        player: Player = await self.get_player(ctx, connect=False)
        
        if option is None:
            return await ctx.send("Please specify a loop option: `track`, `queue`, or `off`")
            
        option = option.lower()
        if option not in ["track", "queue", "off"]:
            return await ctx.fail("You can choose from `track`, `queue`, or `off`")
            
        valid = {
            "off": not player.loop,
            "track": player.is_playing,
            "queue": bool(player.queue._queue),
        }
        
        if not valid.get(option, False):
            return await ctx.fail(f"Cannot set loop to `{option}`")
            
        await player.set_loop(option if option != "off" else False)
        emoji = "✅" if option == "off" else "🔂" if option == "track" else "🔁"
        await ctx.message.add_reaction(emoji)

    @commands.command(name="pause", brief="Pause the current song", example=",pause")
    async def pause(self, ctx: Context):
        player: Player = await self.get_player(ctx, connect=False)
        if player.is_playing and not player.is_paused:
            await ctx.success("**Paused** this song")
            await player.set_pause(True)
        elif player.is_paused:
            await ctx.fail("The player is already paused")
        else:
            await ctx.fail("There isn't an active **track**")

    @commands.command(name="resume", aliases=["rsm"], brief="Resume a paused song", example=",resume")
    async def resume(self, ctx: Context):
        player: Player = await self.get_player(ctx, connect=False)
        if player.is_playing and player.is_paused:
            await ctx.success("**Resumed** the song")
            await player.set_pause(False)
        else:
            await ctx.fail("There isn't an active **track**")

    @commands.command(name="volume", aliases=["vol", "v"], brief="Adjust the volume", example=",volume 50")
    async def volume(self, ctx: Context, percentage: int = 65):
        percentage = min(percentage, 100)
        player: Player = await self.get_player(ctx, connect=False)
        await player.set_volume(percentage)
        embed = discord.Embed(
            color=self.bot.color,
            title="Volume Level",
            description=f"{player.volume_bar}"
        )
        await ctx.send(embed=embed)

    @commands.command(name="disconnect", aliases=["dc", "stop"], brief="Disconnect from voice channel", example=",disconnect")
    async def disconnect(self, ctx: Context):
        player: Player = await self.get_player(ctx, connect=False)
        await player.teardown()
        await ctx.success("**Disconnected** from the voice channel")

    @commands.group(
        name="presets",
        aliases=["eq", "equalizer", "preset"],
        invoke_without_command=True,
    )
    async def presets(self, ctx):
        await ctx.send_help(ctx.command.qualified_name)

    @presets.command(name="list", aliases=["ls"], brief="List available presets", example=",presets list")
    async def presets_list(self, ctx: Context):
        player: Player = await self.get_player(ctx)
        presets = [
            "vaporwave",
            "nightcore",
            "boost",
            "metal",
            "flat",
            "piano",
        ]
        embed = discord.Embed(title="Available Presets", color=0x2B2D31)
        embed.description = "\n".join(presets)
        await ctx.send(embed=embed)

    @presets.command(name="vaporwave", brief="Apply the vaporwave preset", example=",presets vaporwave")
    async def vaporwave(self, ctx: Context):
        player: Player = await self.get_player(ctx)
        try:
            vaporwave = pomice.Timescale.vaporwave()
            await player.add_filter(vaporwave, fast_apply=True)
            await ctx.success("Applied the **vaporwave** preset")
        except pomice.FilterTagAlreadyInUse as e:
            await ctx.warning(f"That filter is already in use")

    @presets.command(name = "nightcore", brief = "Apply the vaporwave preset", example = ",presets vaporwave")
    async def nightcore(self, ctx: Context):
        player: Player = await self.get_player(ctx)
        try:
            preset = pomice.Timescale.nightcore()
            await player.add_filter(preset, fast_apply=True)
            await ctx.success("Applied the **nightcore** preset")
        except pomice.FilterTagAlreadyInUse as e:
            await ctx.warning(f"That filter is already in use")

    @presets.command(name="boost", brief="Apply the boost preset", example=",presets boost")
    async def boost(self, ctx: Context):
        player: Player = await self.get_player(ctx)
        try:
            boost = pomice.Equalizer.boost()
            await player.add_filter(boost, fast_apply=True)
            await ctx.success("Applied the **boost** preset")
        except pomice.FilterTagAlreadyInUse as e:
            await ctx.warning(f"That filter is already in use")

    @presets.command(name="metal", brief="Apply the metal preset", example=",presets metal")
    async def metal(self, ctx: Context):
        player: Player = await self.get_player(ctx)
        try:
            metal = pomice.Equalizer.metal()
            await player.add_filter(metal, fast_apply=True)
            await ctx.success("Applied the **metal** preset")
        except pomice.FilterTagAlreadyInUse as e:
            await ctx.warning(f"That filter is already in use")

    @presets.command(name="flat", brief="Apply the flat preset", example=",presets flat")
    async def flat(self, ctx: Context):
        player: Player = await self.get_player(ctx)
        try:
            flat = pomice.Equalizer.flat()
            await player.add_filter(flat, fast_apply=True)
            await ctx.success("Applied the **flat** preset")
        except pomice.FilterTagAlreadyInUse as e:
            await ctx.warning(f"That filter is already in use")

    @presets.command(name="piano", brief="Apply the piano preset", example=",presets piano")
    async def piano(self, ctx: Context):
        player: Player = await self.get_player(ctx)
        try:
            piano = pomice.Equalizer.piano()
            await player.add_filter(piano, fast_apply=True)
            await ctx.success("Applied the **piano** preset")
        except pomice.FilterTagAlreadyInUse as e:
            await ctx.warning(f"That filter is already in use")

    @presets.command(name="indian", brief="Apply the indian preset", example=",presets indian")
    async def indian(self, ctx: Context):
        player: Optional[Player] = await self.get_player(ctx)
        if not player:
            return await ctx.fail("No player found to apply the **indian** preset.")

        try:
            await ctx.invoke(self.boost)
            await ctx.invoke(self.vaporwave)

            if player.queue and player.queue._queue:
                player.queue._queue.clear()

            if player.is_playing:
                await player.skip()

            await ctx.invoke(self.play_command, query="light up sketchers")
            player.loop = "track"
 
            await ctx.success("Applied the **indian** preset successfully.")
        except Exception as e:
            await ctx.fail(f"Failed to apply the **indian** preset: {str(e)}")

    @presets.command(name="remove", aliases=["off"], brief="Remove a preset from the current player", example=",presets remove vaporwave")
    async def remove_preset(self, ctx: Context, preset: str):
        player: Player = await self.get_player(ctx)
        presets = [
            "vaporwave",
            "nightcore",
            "boost",
            "metal",
            "flat",
            "piano",
        ]
        if preset not in presets:
            return await ctx.warning(f"`{preset}` is not a valid preset")
        try:
            await player.remove_filter(preset, fast_apply=True)
            await ctx.success(f"Removed the **{preset}** preset")
        except pomice.FilterTagNotInUse as e:
            await ctx.warning(f"That filter is not in use")
async def setup(bot):
    await bot.add_cog(Music(bot))