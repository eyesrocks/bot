import discord
from discord.ext import commands
import sqlite3
import logging
from discord import Embed
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
from cogs2.voice import Whisper
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

# Set up logging
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("error.log"), logging.StreamHandler()]
)

class Donators(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = '/root/greed/premium.sql'  # Path to your SQLite database

        # Ensure the database table is created when the cog is initialized
        self._initialize_db()

    def _connect_db(self):
        """Helper function to connect to the SQLite database."""
        return sqlite3.connect(self.db)

    def _initialize_db(self):
        """Initialize the database schema (create tables if not exists)."""
        conn = self._connect_db()
        cursor = conn.cursor()

        # Create a table for whitelisted users if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS whitelisted_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT NOT NULL
        );
        """)
        
        conn.commit()
        conn.close()





    async def send_white_embed(self, ctx, title: str, description: str):
        """Helper function to send an embed with white color."""
        embed = Embed(title=title, description=description, color=discord.Color.from_rgb(255, 255, 255))
        await ctx.send(embed=embed)

    def is_donator(self, ctx):
        """Check if the user is a donator."""
        conn = self._connect_db()
        cursor = conn.cursor()

        # Check if the user is in the whitelisted_users table (donators)
        cursor.execute("SELECT user_id FROM whitelisted_users WHERE user_id = ?", (ctx.author.id,))
        result = cursor.fetchone()  # Use fetchone() for a single result
        conn.close()
        
        if result:
            logging.debug(f"User {ctx.author.name} is a donator.")
            return True
        else:
            logging.debug(f"User {ctx.author.name} is NOT a donator.")
            return False

    @commands.command(name='donators')
    async def donators(self, ctx):
        """Command to show all donators."""
        conn = self._connect_db()
        cursor = conn.cursor()

        try:
            # Query all whitelisted users (donators)
            cursor.execute("SELECT user_id, username FROM whitelisted_users")
            rows = cursor.fetchall()

            if rows:
                donators_text = ""
                for user_row in rows:
                    user_id, username = user_row
                    user = self.bot.get_user(user_id)  # Fetch the user object by ID
                    
                    if user:
                        donators_text += f"{user.mention}\n"  # Format as "username#discriminator"
                    else:
                        donators_text += f"User with ID {user_id} not found\n"  # In case the user is not cached
                
                # If there is a long list of donators, you can break it up into multiple embeds.
                await self.send_white_embed(ctx, "Donators List", f"Here is the list of all donators:\n{donators_text}")
            else:
                await self.send_white_embed(ctx, "No Donators", "There are no donators at the moment.")
        except Exception as e:
            logging.error(f"Error in donators command: {e}")
            await self.send_white_embed(ctx, "Error", f"An error occurred while fetching donators: {str(e)}")
        finally:
            conn.close()

    @commands.command(name='dtest')
    async def donator_test(self, ctx):
        """Donator-only command for testing."""
        if not self.is_donator(ctx):
            await self.send_white_embed(ctx, "Access Denied", "You must be a donator to use this command.")
            return

        # Command logic for donators
        await self.send_white_embed(ctx, "Donator Test", "Congratulations, you are a donator! This command is restricted to donators only.")




    async def make_transcription(self, message: discord.Message):
        """Transcribe voice messages."""
        if len(message.attachments) > 0:
            for attachment in message.attachments:
                if attachment.is_voice_message() is True:
                    filepath = await download_file(attachment.url)  # Assuming download_file function exists
                    return await do_transcribe(filepath)  # Assuming do_transcribe is your transcription function

    @commands.Cog.listener("on_message")
    async def on_voice_message(self, message: discord.Message):
        """Triggered when a message is received."""
        if not message.guild:
            return
        if message.author.bot:
            return

        # Check if auto-transcription is enabled for this server
        conn = self._connect_db()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM auto_transcribe WHERE guild_id = ?", (message.guild.id,))
        auto_transcribe = cursor.fetchone()

        if not auto_transcribe:
            conn.close()
            return
        
        if text := await self.make_transcription(message):
            embed = discord.Embed(description=text, color=0xffffff).set_author(
                name=message.author.display_name,
                icon_url=message.author.display_avatar.url,
            )
            return await message.reply(embed=embed)
        
        conn.close()

    @commands.command(
        name="transcribe",
        brief="Return the text from a voice message",
        example=",transcribe [audio_reply]",
    )
    async def transcribe(self, ctx: commands.Context, message: Optional[Message] = None):
        """Command to transcribe voice messages."""
        
        # **Check if the user is a donator** before proceeding
        if not self.is_donator(ctx.author.id):
            return await ctx.send("You must be a donator to use this command.")
        
        if not message:
            if not ctx.message.reference:
                messages = [
                    message
                    async for message in ctx.channel.history(limit=50)
                    if len(message.attachments) > 0
                    and message.attachments[0].is_voice_message()
                ]

                if len(messages) == 0:
                    return await ctx.send("Please reply to a message or provide a message to transcribe.")
                else:
                    message = messages[0]

                    msg = await ctx.send(
                        embed=discord.Embed(
                            color=0xffffff,
                            description=f"<a:loading:1302351366584270899> {ctx.author.mention}: **Transcribing this message...**",
                        )
                    )
                    text = await self.make_transcription(message)

            else:
                message = await self.bot.fetch_message(
                    ctx.channel, ctx.message.reference.message_id
                )

                msg = await ctx.send(
                    embed=discord.Embed(
                        color=0xffffff,
                        description=f"<a:loading:1302351366584270899> {ctx.author.mention}: **Transcribing this message...**",
                    )
                )

                text = await self.make_transcription(message)

        else:
            text = await self.make_transcription(message)

        if text is None:
            return await ctx.send(f"**Failed to transcribe** [**this message**]({message.jump_url})")

        return await msg.edit(
            embed=discord.Embed(description=text, color=0xffffff).set_author(
                name=message.author.display_name,
                icon_url=message.author.display_avatar.url,
            )
        )



# Setup the cog
async def setup(bot):
    await bot.add_cog(Donators(bot))
