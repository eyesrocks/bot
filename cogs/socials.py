from tool.pinterest import Pinterest  # type: ignore
from discord.ext import commands
from discord import Embed, app_commands, Interaction
from discord.ext.commands import Context, CommandError
from discord.utils import format_dt
from tool.pinpostmodels import Model  # type: ignore
from tuuid import tuuid
from typing import Optional, Union
from contextlib import suppress
from datetime import datetime
from typing import List, Optional

from cashews import cache
from datetime import datetime
from typing import List, Optional

from roblox import AvatarThumbnailType, Client, UserNotFound, TooManyRequests
from roblox.users import User
from roblox.utilities.exceptions import BadRequest
from typing_extensions import Self
from contextlib import suppress
from dataclasses import dataclass, field
from munch import Munch

from yarl import URL

import aiohttp
from lxml import html

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
    highlight: str = "No highlight available"
    extended_links: List[SearchResult] = field(default_factory=list)

class GoogleScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0 Safari/537.36"
            )
        }

    async def search(self, query: str) -> List[Result]:
        """
        Fetch search results for a query and format them into Result objects.
        """
        url = URL.build(
            scheme="https",
            host="www.google.com",
            path="/search",
            query={"q": query}
        )

        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch results: {response.status}")

                content = await response.text()

        tree = html.fromstring(content)
        results = []

        for result in tree.xpath('//div[@class="tF2Cxc"]')[:30]:
            title = result.xpath('.//h3/text()')
            link = result.xpath('.//a/@href')
            snippet = result.xpath('.//div[@class="VwiC3b"]/text()')

            if title and link:
                results.append(Result(
                    title=title[0],
                    url=link[0],
                    snippet=snippet[0] if snippet else "No description available"
                ))

        return results

    def aggregate_results(
        self,
        search_results: List[SearchResult],
        tweet_items: List[TweetItem]
    ) -> List[Result]:
        """
        Combine `SearchResult` and `TweetItem` into unified `Result` objects.
        """
        aggregated = []

        for sr in search_results[:30]:
            aggregated.append(Result(
                title=sr.title,
                url=sr.link,
                snippet=sr.snippet,
                extended_links=[]
            ))

        # Include all TweetItems
        for tweet in tweet_items[:30]:
            aggregated.append(Result(
                title=tweet.text,
                url=tweet.url,
                snippet=tweet.footer,
                highlight="Tweet content"
            ))

        return aggregated

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
        return await self.original.get_follower_count()

    async def following_count(self) -> int:
        """Fetch the count of users the user is following."""
        return await self.original.get_following_count()

    async def friend_count(self) -> int:
        """Fetch the count of friends."""
        return await self.original.get_friend_count()

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
        except (UserNotFound, BadRequest):
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

        await ctx.send(embed=embed)

    @commands.command(
        name="google",
        aliases=["search"],
        brief="Search Google for a query.",
        example=",google discord.py",
    )
    async def google(self, ctx: Context, *, query: str):
        """Search Google for a query."""
        async with ctx.typing():
            scraper = GoogleScraper()
            results = await scraper.search(query)

            if not results:
                return await ctx.send("No results found.")

            embed = Embed(
                title=f"Google Search Results for {query}",
                description="\n\n".join(
                    f"[{result.title}]({result.link})\n{result.snippet}"
                    for result in results
                ),
            )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Socials(bot))
