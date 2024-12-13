from tool.pinterest import Pinterest  # type: ignore
from discord.ext import commands
from discord import Embed, app_commands, Interaction, Message, File, HTTPException
from discord.ext.commands import Context, CommandError
from discord.utils import format_dt
from typing import Optional, Dict, List, Union
from contextlib import suppress
from datetime import datetime
from humanize import naturaltime

from cashews import cache
from asyncio import sleep
from roblox import AvatarThumbnailType, Client, UserNotFound, TooManyRequests
from roblox.users import User
from roblox.utilities.exceptions import BadRequest
from dataclasses import dataclass, field
from munch import DefaultMunch, Munch
from yt_dlp import DownloadError, YoutubeDL
from yarl import URL
from jishaku.functools import executor_function
import aiohttp
from loguru import logger
from re import search, compile
from io import BytesIO
from bs4 import BeautifulSoup
import tempfile
import os
import urllib.parse

@dataclass
class SearchResult:
    title: str
    link: str
    snippet: str

@dataclass
class TweetItem:
    url: str
    text: str
    footer: str

@dataclass
class Result:
    title: str
    url: str
    snippet: str
    highlight: str
    extended_links: List[SearchResult] = field(default_factory=list)



class GoogleScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0 Safari/537.36"
            )
        }

    async def search(self, query: str, num_pages: int = 3) -> list[SearchResult]:
        results = []
        
        for page in range(num_pages):
            start = page * 10
            url = URL.build(
                scheme="https",
                host="www.google.com",
                path="/search",
                query={
                    "q": query,
                    "start": str(start),
                    "safe": "active",
                    "num": "100"
                }
            )

            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        continue
                    content = await response.text()

            soup = BeautifulSoup(content, 'html.parser')
            search_divs = soup.find_all('div', class_=['g', 'tF2Cxc'])

            for div in search_divs:
                title_elem = div.find('h3')
                link_elem = div.find('a')
                snippet_elem = div.find('div', class_=['VwiC3b', 'yXK7lf'])

                if title_elem and link_elem:
                    title = title_elem.get_text()
                    link = link_elem.get('href')
                    snippet = snippet_elem.get_text() if snippet_elem else "No description available"

                    if link.startswith('/url?'):
                        link = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)['q'][0]

                    if link.startswith('http'):
                        results.append(SearchResult(
                            title=title,
                            link=link,
                            snippet=snippet
                        ))

        return results


class GoogleImages:
    def __init__(self):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0 Safari/537.36"
            )
        }

    async def search(self, query: str, num_pages: int = 5) -> list[str]:
        results = []
        
        for page in range(num_pages):
            url = URL.build(
                scheme="https",
                host="www.google.com",
                path="/search",
                query={
                    "q": query,
                    "tbm": "isch",
                    "safe": "active",
                    "start": str(page * 20)
                }
            )

            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        continue
                    content = await response.text()

            soup = BeautifulSoup(content, 'html.parser')
            for img in soup.find_all('img'):
                if src := img.get('src'):
                    if src.startswith('http') and not src.startswith('https://www.google.com'):
                        results.append(src)
        logger.info(results)
        return results[:100]
    
client = Client()

@dataclass
class Badge:
    id: int
    name: str
    description: str
    image_url: str

    @property
    def url(self) -> str:
        """Generate the URL for the badge on Roblox."""
        return f"https://www.roblox.com/info/roblox-badges#Badge{self.id}"


@dataclass
class Presence:
    status: str
    location: Optional[str]
    last_online: Optional[datetime]


@dataclass
class RobloxUserModel:
    id: int
    name: str
    display_name: str
    description: str
    is_banned: bool
    created_at: datetime
    original: User = field(repr=False)

    @property
    def url(self) -> str:
        """Generate the profile URL for the Roblox user."""
        return f"https://www.roblox.com/users/{self.id}/profile"

    @cache(ttl=3600, key="avatar_url:{self.id}")
    async def avatar_url(self) -> Optional[str]:
        """Fetch the user's avatar URL."""
        thumbnails = await client.thumbnails.get_user_avatar_thumbnails(
            users=[self.id],
            type=AvatarThumbnailType.full_body,
            size=(420, 420),
        )
        return thumbnails[0].image_url if thumbnails else None

    @cache(ttl=3600, key="badges:{self.id}")
    async def badges(self) -> List[Badge]:
        """Fetch a list of the user's badges."""
        badges = await self.original.get_roblox_badges()
        return [
            Badge(
                id=badge.id,
                name=badge.name,
                description=badge.description,
                image_url=badge.image_url,
            )
            for badge in badges
        ]

    async def follower_count(self) -> int:
        """Fetch the count of followers."""
        try:
            return await self.original.get_follower_count()
        except TooManyRequests:
            raise CommandError("The Roblox API rate limit has been exceeded. Please try again later.")


    async def following_count(self) -> int:
        """Fetch the count of users the user is following."""
        try:
            return await self.original.get_following_count()
        except TooManyRequests:
            raise CommandError("The Roblox API rate limit has been exceeded. Please try again later.")

    async def friend_count(self) -> int:
        """Fetch the count of friends."""
        try:
            return await self.original.get_friend_count()
        except TooManyRequests:
            raise CommandError("The Roblox API rate limit has been exceeded. Please try again later.")

    async def presence(self) -> Optional[Presence]:
        """Fetch the presence status of the user."""
        presence = await self.original.get_presence()
        return Presence(
            status=presence.user_presence_type.name,
            location=presence.last_location,
            last_online=presence.last_online,
        ) if presence else None

    @cache(ttl=3600, key="names:{self.id}")
    async def names(self) -> List[str]:
        """Fetch the username history of the user."""
        names = []
        with suppress(BadRequest):
            async for name in self.original.username_history():
                names.append(str(name))
        return names

    @classmethod
    async def fetch(cls, username: str) -> Optional["RobloxUserModel"]:
        """Fetch a Roblox user by their username."""
        try:
            user = await client.get_user_by_username(username, expand=True)
        except (UserNotFound, BadRequest, app_commands.errors.CommandInvokeError):
            return None
        except TooManyRequests:
            raise CommandError("The Roblox API rate limit has been exceeded. Please try again later.")

        if isinstance(user, User):
            return cls(
                id=user.id,
                name=user.name,
                display_name=user.display_name,
                description=user.description,
                is_banned=user.is_banned,
                created_at=user.created,
                original=user,
            )
        return None

    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> "RobloxUserModel":
        """Convert a username argument into a RobloxUserModel."""
        async with ctx.typing():
            if user := await cls.fetch(argument):
                return user
        raise CommandError("No **Roblox user** found with that name!")



class Socials(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pinterest = Pinterest()
        self.services = {
            "youtube": compile(
             "(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?v=|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
            ),
            "SoundCloud": (
                r"(?:https?:\/\/)?(?:www\.)?soundcloud\.com\/(?P<username>[a-zA-Z0-9_-]+)\/(?P<slug>[a-zA-Z0-9_-]+)",
                r"(?:https?:\/\/)?(?:www\.)?soundcloud\.app\.goo\.gl\/([a-zA-Z0-9_-]+)",
                r"(?:https?:\/\/)?on\.soundcloud\.com\/([a-zA-Z0-9_-]+)"
            ),
            "tiktok": compile(
               r"(?:https?:\/\/)?(?:www\.|m\.)?(?:vm\.)?tiktok\.com\/(?:@[\w.-]+\/)?(?:video\/|t\/)?([a-zA-Z0-9-_]+)"
            ),
            "instagram": compile(
                r"(?:https?:\/\/)?(?:www\.|m\.)?instagram\.com\/(?:p|reels?)\/([a-zA-Z0-9-_]+)"
            ),
        }
        self.ytdl = YoutubeDL(
            {
                "format": "best",
                "quiet": True,
                "verbose": False,
                'merge_output_format': 'mp4',
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                },
            }
        )
        self._cooldown_mapping = commands.CooldownMapping.from_cooldown(
            1, 5, commands.BucketType.member
        )

    @executor_function
    def extract_data(self, url: Union[URL, str], **params) -> Optional[Munch]:
        data: Optional[Dict]
        try:
            data = self.ytdl.extract_info(
                url=str(url),
                download=False,
                **params,
            )
        except DownloadError:
            return

        if data:
            return DefaultMunch.fromDict(data)

    @commands.Cog.listener("on_message")
    async def check_service(self, message: Message):
        if message.author.bot or not message.guild or not message.content:
            return

        if not any(
            message.content.lower().startswith(prefix)
            for prefix in ("nigga", "greed", message.guild.me.display_name)
        ):
            return

        ctx = await self.bot.get_context(message)

        for service, pattern in self.services.items():
            try:
                if isinstance(pattern, tuple):
                    main_pattern, *short_patterns = pattern
                    for short_pattern in short_patterns:
                        if match := search(short_pattern, message.content):
                            async with self.bot.session.get(match.group()) as response:
                                message.content = str(response.url)
                                break
                    pattern = main_pattern

                if not (match := search(pattern, message.content)):
                    continue

                if bucket := self._cooldown_mapping.get_bucket(message):
                    if bucket.update_rate_limit():
                        break

                async with ctx.typing():
                    arguments = (
                        list(match.groupdict().values()) if match.groupdict() else [URL(match.group())]
                    )
                    self.bot.dispatch(f"{service.lower()}_request", ctx, *arguments)

                await sleep(1)

                if message.embeds and not message.mentions[1:]:
                    with suppress(HTTPException):
                        await message.delete()
                break
            except Exception as e:
                logger.error(f"{service} link: {e}")
                continue

    @commands.Cog.listener("on_youtube_request")
    async def on_youtube_request(self, ctx: Context, url: URL) -> Message:
        data = await self.extract_data(url)
        if not data:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(data.url) as response:
                    if response.status != 200:
                        return
                    buffer: bytes = await response.read()
        except Exception as e:
            return logger.error(f"Youtube request: {e}")
            
        embed = Embed(
            description=f"[{data.title}]({data.webpage_url})",
            url=url,
        )

        if author := data.get("uploader"):
            embed.set_author(name=author)

        likes, views = data.get("like_count"), data.get("view_count")
        if likes and views:
            embed.set_footer(text=f"{likes:,} likes | {views:,} views")

        try:
            async with ctx.typing():
                for attempt in range(3):  # Add retry logic
                    try:
                        await ctx.send(embed=embed, file=File(BytesIO(buffer), filename=f"{data.title}.{data.ext}"))
                        break
                    except (IndexError, ConnectionError) as e:
                        if attempt == 2:  # Last attempt
                            logger.error(f"Failed to send YouTube video after 3 attempts: {e}")
                            await ctx.error("Failed to process the YouTube video. Please try again later.")
                            return
                        await asyncio.sleep(1)  # Wait before retrying
        except Exception as e:
            logger.error(f"Error in YouTube request handler: {e}")
            await ctx.error("An error occurred while processing your request.")

    @commands.Cog.listener()
    async def on_instagram_request(self, ctx: Context, url: URL) -> Message:
        data = await self.extract_data(url)
        logger.info(data)
        if not data:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(data.url) as response:
                    if response.status != 200:
                        return
                    buffer: bytes = await response.read()
        except Exception as e:
            return logger.error(f"Instagram request: {e}")

        embed = Embed(
            description=f"[{data.title}]({data.webpage_url})",
            url=url,
        )

        if author := data.get("uploader"):
            embed.set_author(name=author, icon_url=data.thumbnail if data.thumbnail else None)

        embed.set_footer(text=f"uploaded {naturaltime(data.upload_date)}")

        await ctx.send(embed=embed, file=File(BytesIO(buffer), filename=f"{data.title}.{data.ext}"))
    @commands.Cog.listener()
    async def on_soundcloud_request(self, ctx, username, slug):
        
        url = f"https://soundcloud.com/{username}/{slug}"
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'logtostderr': True,
            'extract_flat': False,
            'no_warnings': True,
            'outtmpl': '%(title)s.%(ext)s'
        }
        
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info['title']
                final_file = f"{title}.mp3"
                
                embed = Embed(
                    title=title,
                    url=url,
                    description=f"Duration: {info.get('duration_string', 'Unknown')}"
                )
                
                if uploader := info.get('uploader'):
                    embed.set_author(
                        name=uploader,
                        icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                    )
                    
                if thumbnail := info.get('thumbnail'):
                    embed.set_thumbnail(url=thumbnail)
                    
                if views := info.get('view_count'):
                    embed.set_footer(text=f"{views:,} plays")

                await ctx.send(
                    embed=embed,
                    file=File(
                        fp=final_file,
                        filename=f"{title}.mp3",
                        description="voice-message",
                        spoiler=False
                    )
                )                
                if os.path.exists(final_file):
                    os.unlink(final_file)
                    
        except Exception as e:
            logger.error(f"SoundCloud request failed: {e}")
            await ctx.fail("That SoundCloud track could not be found!")

    def extract_soundcloud_url_parts(self, track: str) -> tuple[str, str]:
        """Extract username and slug from SoundCloud track URL or format string."""
        # Check if it's already a URL
        main_pattern, *short_patterns = self.services["SoundCloud"]
        
        # Try main pattern first
        if match := search(main_pattern, track):
            return match.group("username"), match.group("slug")
            
        # Try to resolve short URLs
        for pattern in short_patterns:
            if match := search(pattern, track):
                # Fetch the resolved URL
                short_url = track
                if not track.startswith(('http://', 'https://')):
                    short_url = f"https://{track}"
                    
                # Use a synchronous request here since we're in a sync method
                import requests
                try:
                    response = requests.get(short_url, allow_redirects=True)
                    if response.status_code == 200:
                        # Try to match the resolved URL
                        if resolved_match := search(main_pattern, response.url):
                            return resolved_match.group("username"), resolved_match.group("slug")
                except:
                    pass
        
        # If it's not a URL, assume it's in format "artist/track-name"
        if "/" in track:
            username, slug = track.split("/", 1)
            return username.strip(), slug.strip()
            
        raise commands.CommandError("Invalid SoundCloud track format. Use 'artist/track-name' or a valid SoundCloud URL.")

    @app_commands.command(
        name="soundcloud",
        description="Download a track from SoundCloud.",
    )
    @app_commands.describe(track="The SoundCloud track (artist/track-name or URL)")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(users=True, guilds=True)
    async def soundcloud_command(self, interaction: Interaction, track: str):
        """Download a track from SoundCloud."""
        await interaction.response.defer()
        
        try:
            username, slug = self.extract_soundcloud_url_parts(track)
            ctx = await Context.from_interaction(interaction)
            await self.on_soundcloud_request(ctx, username, slug)
        except Exception as e:
            logger.error(f"SoundCloud command failed: {e}")
            await interaction.followup.send("Failed to process that SoundCloud track!")

    @app_commands.command(
        name="roblox",
        description="Get information about a Roblox user.",
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(users=True, guilds=True)
    async def roblox_command(self, interaction: Interaction, username: str):
        """Get information about a Roblox user."""
        ctx = await Context.from_interaction(interaction)
        user = await RobloxUserModel.fetch(username)
        if user:
            await self.roblox(ctx, user)

            

    @commands.command(
        name="roblox",
        aliases=["rblx"],
        brief="Get information about a Roblox user.",
        example=",roblox yurrionsolos",
    )
    async def roblox(self, ctx: Context, user: RobloxUserModel):
        """Get information about a Roblox user."""
        async with ctx.typing():
            try:
                embed = Embed(
                    title=f"{user.display_name} ({user.name}) {'[BANNED]' if user.is_banned else ''}",
                    description=f"{user.description} \n\n{format_dt(user.created_at, 'R')}",
                    url=user.url,
                )

                if avatar_url := await user.avatar_url():
                    embed.set_thumbnail(url=avatar_url)

                if presence := await user.presence():
                    embed.add_field(
                        name="Presence",
                        value=(
                            f"Status: {presence.status}\n"
                            f"Location: {presence.location}\n"
                            f"Last Online: {format_dt(presence.last_online, 'R')}"
                        ),
                        inline=False,
                    )
                
                if badges := await user.badges():
                    embed.add_field(
                        name="Badges",
                        value="\n".join(
                            f"[{badge.name}]({badge.url})" for badge in badges
                        ),
                        inline=False,
                    )
                
                if names := await user.names():
                    embed.add_field(
                        name="Previous Names",
                        value="\n".join(names),
                        inline=False,
                    )

                embed.set_footer(
                    text=f"Followers: {await user.follower_count()} | Following: {await user.following_count()} | Friends: {await user.friend_count()}"
                )
            except TooManyRequests:
                return await ctx.fail("The Roblox API rate limit has been exceeded. Please try again later.")
            except Exception as e:
                return logger.error(f"Roblox command: {e}")
        await ctx.send(embed=embed)



    @commands.command(
        name = "google",
        aliases = ["g", "ddg", "search"],
        brief = "Search the web using Google.",
        example = ",google how to make a sandwich"
    )
    async def google(self, ctx: Context, *, query: str):
        """Search the web using Google."""
        async with ctx.typing():
            scraper = GoogleScraper()
            results = await scraper.search(query)

            if not results:
                return await ctx.fail("No results found for that query.")

            embeds = []
            for i in range(0, len(results), 3):
                embed = Embed(title=f"Search Results")
                for result in results[i:i+3]:
                    embed.add_field(
                        name=result.title,
                        value=f"[{result.snippet}]({result.link})",
                        inline=False
                    )
                    embed.set_footer(text=f"Page {i // 3 + 1}")
                embeds.append(embed)
        await ctx.paginate(embeds)

async def setup(bot):
    await bot.add_cog(Socials(bot))
