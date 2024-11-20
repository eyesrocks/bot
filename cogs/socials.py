from tool.pinterest import Pinterest  # type: ignore
from discord.ext import commands
from discord import Embed, app_commands, Interaction
from discord.ext.commands import Context, CommandError
from discord.utils import format_dt
from tool.pinpostmodels import Model  # type: ignore
from tuuid import tuuid
from typing import Optional
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
    async def roblox_command(self, interaction: Interaction, username: str):
        """Get information about a Roblox user."""
        ctx = await self.bot.get_context(interaction.message)
        with suppress(CommandError):
            user = await RobloxUserModel.convert(ctx, username)
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

async def setup(bot):
    await bot.add_cog(Socials(bot))
