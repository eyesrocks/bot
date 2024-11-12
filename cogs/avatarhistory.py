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
        return data, response.headers['Content-Type']


    @Cog.listener("on_user_update")
    async def on_avatar_change(self, before: User, after: User):
        if before.display_avatar == after.display_avatar:
            return

        avatar, content_type = await self.get_data(after)
        await self.bot.db.execute("""INSERT INTO avatars (user_id, content_type, avatar, id) VALUES($1, $2, $3, $4)""", before.id, content_type, avatar, after.display_avatar.key)


    @command(name = "avatarhistory", aliases = ["avatars", "avh"], brief = "view past avatar changes with a user", example = ",avh @aiohttp")
    async def avatarhistory(self, ctx: Context, *, user: Optional[Union[User, Member]] = None):
        user = user or ctx.author
        rows = await self.bot.db.fetch("""SELECT id, avatar, content_type, ts FROM avatars WHERE user_id = $1 ORDER BY ts DESC""", user.id)
        if not rows:
            raise CommandError(f"no avatars have been **saved** for {user.mention}")
        embeds = []
        title = f"{str(user)}'s avatars" if not str(user).endswith("s") else f"{str(user)}' avatars"
        for i, row in enumerate(rows, start=1):
            embed = Embed(title=title).set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
            url = f"attachment://avatar_{i}.{row['content_type'].split('/')[-1]}"
            embed.set_image(url=url)
            embed.url = url
            embed.set_footer(text=f"Avatar {i}/{len(rows)}")
            embed.description = f"changed {utils.format_dt(row['ts'], style='R')}"
            embeds.append((embed, row['avatar'], row['content_type']))
        
        from io import BytesIO
        files = [File(fp=BytesIO(avatar), filename=f"avatar_{i}.{content_type.split('/')[-1]}") for i, (_, avatar, content_type) in enumerate(embeds, start=1)]
        embeds = [embed for embed, _, _ in embeds]
        
        return await ctx.alternative_paginate(embeds, files=files)

    @command(name = "clearavatars", aliases = ["clavs", "clavh", "clearavh"], brief = "clear your avatar history")
    async def clearavatars(self, ctx: Context):
        await self.bot.db.execute("""DELETE FROM avatars WHERE user_id = $1""", ctx.author.id)
        return await ctx.success("cleared your **avatar history**")

async def setup(bot: Client):
    await bot.add_cog(AvatarHistory(bot))
