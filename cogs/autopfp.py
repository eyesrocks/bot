from typing import Optional, Union, Literal, List, Dict, Any, Type
from pydantic import BaseModel
from discord.ext.commands import Cog, command, group, has_permissions
from discord.ext import tasks
from aiohttp import ClientSession as Session
from discord.ui import View, Select, Button, button
from discord import Color, Embed, Guild, Client, TextChannel, ButtonStyle, Interaction, Member, SelectOption
from orjson import loads, dumps
from asyncio import gather

from tool.important.subclasses.color import get_dominant_color
from tool.important.subclasses.context import Context
from tool.important.database import Record
from _types import get_error
from loguru import logger

class CategorySelect(Select):
    def __init__(self, categories: List[str], state: dict):
        options = [SelectOption(label=category) for category in categories]
        super().__init__(placeholder='Choose your categories..', min_values=1, max_values=len(options), options=options)
        self.state = state
    
    async def callback(self, interaction: Interaction):
        selected_categories = ', '.join(self.values)
        self.state['categories'] = self.values
        await interaction.response.send_message(f'You selected: {selected_categories}', ephemeral=True)
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
            await interaction.followup.send(f'Selected categories: {", ".join(selected_categories)}', ephemeral=True)
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
        async with Session() as session:
            async with session.get(f"https://cdn.rival.rocks/{endpoint}", params = {"category": category}) as response:
                _data = await response.json()
        _data["category"] = _data["category"].replace("gif", "").replace("photo", "")
        async with Session() as session:
            async with session.get(_data["url"]) as resp:
                avatar = await resp.read()
        dominant_color = await get_dominant_color(avatar)
        _data["dominant_color"] = dominant_color
        data = dumps(_data)
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
        return {a.category.lower(): a for a in avatars}
    
    async def send_avatars(self, channel: TextChannel, categories: List[str], avatars: Dict[str, AssetResponse]):
        message = None
        for category in categories:
