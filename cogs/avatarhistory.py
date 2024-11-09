from discord.ext.commands import Cog, command, group
from discord import User, Member, Guild, Embed, File, Client
from aiohttp import ClientSession


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
        if not (guild := self.bot.get_guild(self.guild_id)):
            return await self.bot.unload_extension("cogs.avatarhistory")

        if guild not in before.mutual_guilds:
            return

        if before.display_avatar == after.display_avatar:
            return

        avatar, content_type = await self.get_data(after)
        await self.bot.db.execute("""INSERT INTO avatars (user_id, content_type, avatar, id) VALUES($1, $2, $3, $4)""", before.id, content_type, avatar, after.display_avatar.key)

async def setup(bot: Client):
    await bot.add_cog(AvatarHistory(bot))
