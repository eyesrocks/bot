from typing import Optional, Union, Literal, List, Dict, Any, Type
from pydantic import BaseModel
from discord.ext.commands import Cog, command, group, has_permissions
from discord.ext import tasks
from aiohttp import ClientSession as Session
from discord.ui import View, Select, Button, button
from discord import Color, Embed, Guild, Client, TextChannel, ButtonStyle, Interaction, Member, SelectOption
from orjson import loads, dumps
from asyncio import gather, Lock
from collections import defaultdict
from tuuid import tuuid

from tool.worker import offloaded
from tool.important.subclasses.context import Context
from tool.important.database import Record
from _types import get_error
from loguru import logger

LAST_POSTED = {}

@offloaded
def get_dominant_color(image: bytes) -> str:
    from colorgram_rs import get_dominant_color as _get_dominant_color
    try: 
        color_hex = _get_dominant_color(image)
    except Exception: 
        color_hex = "000001"
    return f"#{color_hex}"

class CategorySelect(Select):
    def __init__(self, categories: List[str], state: dict):
        options = [SelectOption(label=category) for category in categories]
        super().__init__(placeholder='Choose your categories..', min_values=1, max_values=len(options), options=options)
        self.state = state
    
    async def callback(self, interaction: Interaction):
        selected_categories = ', '.join(self.values)
        self.state['categories'] = self.values
        self.view.stop()

class CategorySelectView(View):
    def __init__(self, categories: List[str], state: dict):
        super().__init__()
        self.add_item(CategorySelect(categories, state))

class CategoryButton(Button):
    def __init__(self, categories: List[str], state: dict, author: Member):
        super().__init__(label="Select Categories", style=ButtonStyle.primary)
        self.categories = categories
        self.state = state
        self.author = author
    
    async def callback(self, interaction: Interaction):
        if interaction.user.id is not self.author.id:
            return await interaction.response.send_message("you are not the invoker of this command", ephemeral = True)
        view = CategorySelectView(self.categories, self.state)
        await interaction.response.send_message('Select a category:', view=view, ephemeral=True)
        
        await view.wait()
        
        selected_categories = self.state.get('categories', [])
        if selected_categories:
            await interaction.followup.send(f'You Selected: {", ".join(selected_categories)}', ephemeral=True)
        else:
            await interaction.followup.send('No categories were selected.', ephemeral=True)
        self.view.stop()

class CategoryView(View):
    def __init__(self, categories: List[str], state: dict, author: Member):
        super().__init__()
        self.add_item(CategoryButton(categories, state, author))

class AssetResponse(BaseModel):
    url: Optional[str] = None
    category: Optional[str] = None
    filename: Optional[str] = None
    extension: Optional[str] = None
    id: Optional[int] = None
    dominant_color: Optional[str] = None

    @classmethod
    async def from_category(cls: Type["AssetResponse"], endpoint: str, category: str) -> "AssetResponse":
        while True:
            async with Session() as session:
                async with session.get(f"https://cdn.rival.rocks/{endpoint}", params = {"category": category, "yes": tuuid()}) as response:
                    _data = await response.json()
            _data["category"] = _data["category"].replace("gif", "").replace("photo", "")
            if _data["url"] == LAST_POSTED.get(_data["category"]):
                continue
            async with Session() as session:
                async with session.get(_data["url"]) as resp:
                    avatar = await resp.read()
            break
        dominant_color = await get_dominant_color(avatar)
        _data["dominant_color"] = dominant_color
        data = dumps(_data)
        LAST_POSTED[_data["category"]] = _data["url"]
        del _data
        return cls.parse_raw(data)
    
    def to_embed(self, guild: Guild) -> Embed:
        if vanity := guild.vanity_url_code:
            server = f" • /{vanity}"
        else:
            server = ""
        embed = Embed(color = Color.from_str(self.dominant_color))
        embed.set_image(url = self.url)
        category = self.category.replace("Roadmen", "Gangster").replace("Egirl", "E-Girl")
        embed.set_footer(text = f"New {self.category} Avatar • ID: {self.id}{server}")
        return embed
    
class AutoPFP(Cog):
    def __init__(self, bot: Client):
        self.bot = bot
        self.last_posted = {}
        self.locks = defaultdict(Lock)
        self.avatar_categories = ['girl', 'smoking', 'besties', 'animals', 'egirl', 'cars', 'edgy', 'random', 'anime', 'nike', 'female', 'aesthetic', 'hellokitty', 'roadmen', 'faceless', 'guns', 'cartoon', 'jewellry', 'shoes', 'male', 'money', 'body', 'drill', 'food', 'soft']
        self.banner_categories = ['random', 'anime', 'imsg', 'mix']

    async def cog_load(self):
        await self.bot.db.execute("""CREATE TABLE IF NOT EXISTS autopfp (guild_id BIGINT NOT NULL, channel_id BIGINT NOT NULL, categories TEXT[] NOT NULL, PRIMARY KEY(guild_id, channel_id));""")
        self.auto_assets.start()

    async def cog_unload(self):
        self.auto_assets.stop()

    async def get_avatar(self, category: str, return_category: Optional[bool] = False) -> Union[Dict[str, AssetResponse], AssetResponse]:
        response = await AssetResponse.from_category("autopfp", category)
        if return_category is True:
            return {f"{category}": response}
        else:
            return response


    async def get_banners(self) -> Dict[str, AssetResponse]:
        banners = await gather(*[AssetResponse.from_category("autobanner", c) for c in self.banner_categories])
        return {b.category.lower(): b for b in banners}

    async def get_avatars(self) -> Dict[str, AssetResponse]:
        avatars = await gather(*[AssetResponse.from_category("autopfp", c) for c in self.avatar_categories])
        data = {a.category.lower(): a for a in avatars}
        if not self.last_posted:
            self.last_posted = {k: v.url for k, v in data.items()}
        else:
            for key, value in data.items():
                while True:
                    if self.last_posted.get(key, "") == value.url:
                        new = await AssetResponse.from_category("autopfp", key)
                        if new.url == self.last_posted.get(key):
                            continue
                        else:
                            data[key] = new
                            break
                    else:
                        break
            self.last_posted = {k: v.url for k, v in data.items()}
            return data
            





    async def send_avatars(self, channel: TextChannel, categories: List[str], avatars: Dict[str, AssetResponse]):
        if await self.bot.glory_cache.ratelimited(f"autopfp:{channel.id}", 1, 250) != 0:
            return
        async with self.locks[channel.id]:
            message = None
            for category in categories:
                embeds = [avatars[c].to_embed(channel.guild) for c in categories if avatars.get(c)]
                urls = []
                new_embeds = []
                for embed in embeds:
                    if embed.image.url not in urls:
                        urls.append(embed.image.url)
                        new_embeds.append(embed)
                    
                if channel.permissions_for(channel.guild.me).send_messages:
                    message = await channel.send(embeds = new_embeds[:10])
        return message
    
    @tasks.loop(minutes = 5)
    async def auto_assets(self):
        rl = await self.bot.glory_cache.ratelimited("autopfp", 1, 280)
        if rl != 0:
            return
        return await self.do_assets()
            
    async def do_assets(self):
        posted = []
        try:
            avatars = await self.get_avatars()
            logger.info(f"avatars: {avatars}\nlast_posted: {LAST_POSTED}")
            rows = await self.bot.db.fetch("""SELECT guild_id, channel_id, categories FROM autopfp WHERE guild_id = ANY($1::bigint[])""", [g.id for g in self.bot.guilds])
            for row in rows:
                async with self.locks["autopfp"]:
                    if row.channel_id in posted:
                        continue
                    if not (guild := self.bot.get_guild(row.guild_id)):
                        continue
                    if not (channel := guild.get_channel(row.channel_id)):
                        continue
                    await self.send_avatars(channel, row.categories, avatars)
                    posted.append(row.channel_id)
        except Exception as e:
            logger.info(f"error in auto_assets: {get_error(e)}")


    @group(name = "autopfp", brief = "setup automatic profile pictures being sent into channels", invoke_without_command = True)
    async def autopfp(self, ctx: Context):
        return await ctx.send_help(ctx.command)
    
    @autopfp.command(name = "add", aliases = ["create", "set", "a", "c", "s"], brief = "add a channel for profile pictures to be sent into", example = ",autopfp add #nigga")
    @has_permissions(manage_guild = True)
    async def autopfp_add(self, ctx: Context, *, channel: TextChannel):
        state = {}
        view = CategoryView(self.avatar_categories, state, ctx.author)
        message = await ctx.send(embed = Embed(color = self.bot.color, description = f"set the categories for {channel.mention}"), view = view)
        await view.wait()
        if categories := state.get("categories"):
            await self.bot.db.execute("""INSERT INTO autopfp (guild_id, channel_id, categories) VALUES($1, $2, $3) ON CONFLICT(guild_id, channel_id) DO UPDATE SET categories = excluded.categories""", ctx.guild.id, channel.id, categories)
            return await message.edit(embed = Embed(color = self.bot.color, description = f"set the categories of {channel.mention} to {', '.join(c for c in categories)}"), view = None)
        else:
            return await message.edit(embed = Embed(color = self.bot.color, description = "you did not select any **categories**"), View = None)
        
    @autopfp.command(name = "remove", aliases = ["delete", "del", "d", "rem", "r"], brief = "remove an autopfp channel", example = ",autopfp remove #nigga")
    @has_permissions(manage_guild = True)
    async def autopfp_remove(self, ctx: Context, *, channel: TextChannel):
        await self.bot.db.execute("""DELETE FROM autopfp WHERE guild_id = $1 AND channel_id = $2""", ctx.guild.id, channel.id)
        return await ctx.success(f"successfully removed the autopfp channel {channel.mention}")
    
    @autopfp.command(name = "clear", aliases = ["reset", "cl"], brief = "reset all auto pfp configurations")
    @has_permissions(manage_guild = True)
    async def autopfp_clear(self, ctx: Context):
        await self.bot.db.execute("""DELETE FROM autopfp WHERE guild_id = $1""", ctx.guild.id)
        return await ctx.success("successfully reset all auto pfp configurations")
    
    @autopfp.command(name = "list", aliases = ["view", "show", "ls"], brief = "get a list of all auto pfp channels")
    @has_permissions(manage_guild = True)
    async def autopfp_list(self, ctx: Context):
        embed = Embed(title = "Auto PFP Channels")
        data = await self.bot.db.fetch("""SELECT channel_id, categories FROM autopfp WHERE guild_id = $1""", ctx.guild.id)
        def get_row(record: Record) -> str:
            if not (channel := ctx.guild.get_channel(record.channel_id)):
                return f"`{record.channel_id}` (deleted channel)"
            categories = [f"`{c}`" for c in record.categories]
            return f"{channel.mention} ({', '.join(categories)})"
        rows = [get_row(row) for row in data]
        return await self.bot.dummy_paginator(ctx, embed, rows)
    

async def setup(bot: Client):
    await bot.add_cog(AutoPFP(bot))

    
    






