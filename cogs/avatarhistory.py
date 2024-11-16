from discord.ext.commands import Cog, command, group, CommandError
from discord import User, Member, Guild, Embed, File, Client, utils
from aiohttp import ClientSession
from typing import Union, Optional
from tool.important.subclasses.context import Context

class AvatarHistory(Cog):
    def __init__(self, bot: Client):
        self.bot = bot
        self.guild_id = 1301617147964821524

    async def get_data(self, user: User) -> tuple:
        async with ClientSession() as session:
            async with session.get(user.display_avatar.url) as response:
                data = await response.read()
                content_type = response.headers.get('Content-Type')
                if not content_type:
                    content_type = 'image/png'  # default fallback
        return data, content_type

    @Cog.listener("on_user_update")
    async def on_avatar_change(self, before: User, after: User):
        if before.display_avatar == after.display_avatar:
            return
        if before.guild.id != self.guild_id:
            return

        avatar, content_type = await self.get_data(after)
        await self.bot.db.execute(
            """INSERT INTO avatars (user_id, content_type, avatar, id) VALUES($1, $2, $3, $4)""",
            after.id, content_type, avatar, after.display_avatar.key
        )


    @command(name = "avatarhistory", aliases = ["avatars", "avh"], brief = "view past avatar changes with a user", example = ",avh @aiohttp")
    async def avatarhistory(self, ctx: Context, *, user: Optional[Union[User, Member]] = None):
        user = user or ctx.author
        rows = await self.bot.db.fetch("""SELECT id, avatar, content_type, ts FROM avatars WHERE user_id = $1 ORDER BY ts DESC""", user.id)
        if not rows:
            raise CommandError(f"no avatars have been **saved** for {user.mention}")
        title = f"{str(user)}'s avatars" if not str(user).endswith("s") else f"{str(user)}' avatars"
        embed = Embed(title=title).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        url = f"https://cdn.greed.wtf/avatars/{user.id}"
        embed.set_image(url=url)
        return await ctx.send(embed=embed)

    @command(name = "clearavatars", aliases = ["clavs", "clavh", "clearavh"], brief = "clear your avatar history")
    async def clearavatars(self, ctx: Context):
        await self.bot.db.execute("""DELETE FROM avatars WHERE user_id = $1""", ctx.author.id)
        return await ctx.success("cleared your **avatar history**")

async def setup(bot: Client):
    await bot.add_cog(AvatarHistory(bot))
