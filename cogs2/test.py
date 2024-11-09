from discord.ext import commands
from discord import User, Asset, Member, Embed, File, Message  # type: ignore
from discord.ext.commands import (  # type: ignore
	Cog,
	Context,
	check,
	hybrid_group,
)
import orjson
from tool.important.services import get_bing_results
from bs4 import BeautifulSoup
from aiomisc.backoff import asyncretry
from itertools import chain
from lxml import html
# from DataProcessing import ServiceManager
import lxml
from httpx import AsyncClient
from rival_tools import timeit
from aiofiles import open as async_open
from discord.ext import commands  # ftype: ignore
from typing import Any
from rival_tools import thread, lock, ratelimit  # type: ignore
from tool.worker import offloaded
from tool.pinterest import Pinterest  # type: ignore
from tool.pinpostmodels import Model  # type: ignore
from PIL import Image  # type: ignore
import imagehash as ih  # type: ignore
from io import BytesIO
from logging import getLogger
from tool.worker import offloaded
from tool.rival import GoogleSearchResponse
from voice import Whisper
from typing import Union, Optional  # type: ignore
from asyncio.subprocess import PIPE  # type: ignore
from aiohttp import ClientSession  # type: ignore
from contextlib import suppress  # type: ignore
import os  # type: ignore
import string  # type: ignore
import random  # type: ignore
from aiomisc.backoff import asyncretry  # type: ignore
import datetime  # type: ignore
import asyncio  # type: ignore
import aiohttp  # type: ignore
import discord  # type: ignore
# from tool.important.services.TikTok.client import tiktok_video1, tiktok_video2  # type: ignore
from discord.utils import chunk_list  # type: ignore
from rust_chart_generator import create_chart  # type: ignore
from tool.expressions import YOUTUBE_WILDCARD  # type: ignore
from tool.important.services.Twitter import Tweet, from_id
import humanize  # type: ignore
from cogs.information import get_instagram_user  # type: ignore
from tuuid import tuuid  # type: ignore
import io  # type: ignore
from tool.important.services.Eros import PostResponse  # type: ignore
# from tool.processing.media import MediaHandler  # type: ignore
from cashews import cache  # type: ignore
from aiohttp import ClientSession as Session  # type: ignore
import re
from loguru import logger
from voice import save_file



class Premium(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.prefix = ";"




    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # If the message is from a bot, ignore it to prevent infinite loops
        if message.author.bot:
            return


        # Check if the bot is mentioned in the message
        if self.bot.user in message.mentions:
            author_mention = message.author.mention
            embed = discord.Embed(
                color=0xffffff,  
                description=f"{author_mention}: Guild Prefix is set to **{self.bot.prefix}**"
            )
            # Send the embed as a reply to the message
            await message.channel.send(embed=embed)



    @commands.command()
    async def hello(self, ctx):
        """A simple command to say hello"""
        await ctx.send("Hello! I am a custom bot with cogs!")

    @commands.command()
    async def ping(self, ctx):
        """A command to check if the bot is alive"""
        await ctx.send("Pong!")





async def setup(bot):
    await bot.add_cog(Premium(bot))