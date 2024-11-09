import discord
from discord.ext import commands
import sqlite3
import logging
from discord import Embed
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




# Set up logging
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("error.log"), logging.StreamHandler()]
)

class Owners(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = '/root/greed/premium.sql'

        # Set the server IDs and role IDs for the allowed servers/roles
        self.allowed_servers = [1301617147964821524]  # Replace with your allowed server IDs
        self.allowed_roles = [1301618675316559932]  # Replace with your allowed role IDs

        # Ensure the database table is created when the cog is initialized
        self._initialize_db()

    def _connect_db(self):
        """Helper function to connect to the SQLite database."""
        return sqlite3.connect(self.db)

    def _initialize_db(self):
        """Initialize the database schema (create tables if not exists)."""
        conn = self._connect_db()
        cursor = conn.cursor()

        # Create the table for whitelisted servers if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS whitelisted_servers (
            server_id INTEGER PRIMARY KEY
        );
        """)

        # Create the table for whitelisted users if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS whitelisted_users (
            user_id INTEGER PRIMARY KEY
        );
        """)
        
        conn.commit()
        conn.close()

    def is_allowed_server(ctx):
        """Check if the command is being used in an allowed server."""
        return ctx.guild.id in [1301617147964821524]  # List of allowed server IDs

    def has_allowed_role(ctx):
        """Check if the user has one of the allowed roles."""
        return any(role.id in [1301618675316559932] for role in ctx.author.roles)  # List of allowed role IDs

    async def send_white_embed(self, ctx, title: str, description: str):
        """Helper function to send an embed with white color."""
        embed = Embed(title=title, description=description, color=discord.Color.from_rgb(255, 255, 255))
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Triggered when the bot joins a new server."""
        conn = self._connect_db()
        cursor = conn.cursor()

        # Check if the server is whitelisted
        cursor.execute("SELECT * FROM whitelisted_servers WHERE server_id = ?", (guild.id,))
        result = cursor.fetchone()

        # If server is not whitelisted, the bot leaves
        if not result:
            embed = Embed(
                description="<:deny2:1302206609719824425> Your server is not whitelisted. Join [support](https://discord.gg/pomice) to get whitelisted.",
                color=discord.Color.from_rgb(255, 255, 255)  # White color
            )
            await guild.owner.send(embed=embed)  # Send the message to the server owner
            await guild.leave()  # Make the bot leave the server
        
        conn.close()

    @commands.command(name='whitelist')
    @commands.check(is_allowed_server)
    @commands.check(has_allowed_role)
    @commands.has_permissions(administrator=True)
    async def whitelist(self, ctx, server_id: int):
        """Command to whitelist a server. Only usable by admins and in allowed servers/roles."""
        conn = self._connect_db()
        cursor = conn.cursor()

        try:
            # Check if the server is already whitelisted
            cursor.execute("SELECT * FROM whitelisted_servers WHERE server_id = ?", (server_id,))
            result = cursor.fetchone()

            if result:
                await self.send_white_embed(ctx, "Server Already Whitelisted", f"Server ID {server_id} is already on the whitelist.")
            else:
                cursor.execute("INSERT INTO whitelisted_servers (server_id) VALUES (?)", (server_id,))
                conn.commit()
                await self.send_white_embed(ctx, "Server Whitelisted", f"Server ID {server_id} has been successfully added to the whitelist.")
        except Exception as e:
            logging.error(f"Error in whitelist command: {e}")
            await self.send_white_embed(ctx, "Error", "An error occurred while processing your request. Please try again later.")
        finally:
            conn.close()

    @commands.command(name='sblacklist')
    @commands.check(is_allowed_server)
    @commands.check(has_allowed_role)
    @commands.has_permissions(administrator=True)
    async def remove_whitelist(self, ctx, server_id: int):
        """Command to remove a server from the whitelist. Only usable by admins and in allowed servers/roles."""
        conn = self._connect_db()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM whitelisted_servers WHERE server_id = ?", (server_id,))
            conn.commit()

            await self.send_white_embed(ctx, "Server Removed from Whitelist", f"Server with ID {server_id} has been successfully removed from the whitelist.")
        except Exception as e:
            logging.error(f"Error in sblacklist command: {e}")
            await self.send_white_embed(ctx, "Error", "An error occurred while processing your request. Please try again later.")
        finally:
            conn.close()

    @commands.command(name='donoradd')
    @commands.check(is_allowed_server)
    @commands.check(has_allowed_role)
    @commands.has_permissions(administrator=True)
    async def donor_add(self, ctx, user_id: int):
        """Command to add a user to the donor whitelist. Only usable by admins."""
        conn = self._connect_db()
        cursor = conn.cursor()

        try:
            # Check if the user is already whitelisted
            cursor.execute("SELECT * FROM whitelisted_users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()

            if result:
                await self.send_white_embed(ctx, "User Already on Donor Whitelist", f"<@{user_id}> is already on the donor whitelist.")
            else:
                cursor.execute("INSERT INTO whitelisted_users (user_id) VALUES (?)", (user_id,))
                conn.commit()
                await self.send_white_embed(ctx, "User Added to Donor Whitelist", f"<@{user_id}> has been successfully added to the donor whitelist.")
        except Exception as e:
            logging.error(f"Error in donoradd command: {e}")
            await self.send_white_embed(ctx, "Error", "An error occurred while processing your request. Please try again later.")
        finally:
            conn.close()

    @commands.command(name='donorunadd')
    @commands.check(is_allowed_server)
    @commands.check(has_allowed_role)
    @commands.has_permissions(administrator=True)
    async def donor_unadd(self, ctx, user_id: int):
        """Command to remove a user from the donor whitelist. Only usable by admins."""
        conn = self._connect_db()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM whitelisted_users WHERE user_id = ?", (user_id,))
            conn.commit()

            await self.send_white_embed(ctx, "User Removed from Donor Whitelist", f"<@{user_id}> has been successfully removed from the donor whitelist.")
        except Exception as e:
            logging.error(f"Error in donorunadd command: {e}")
            await self.send_white_embed(ctx, "Error", "An error occurred while processing your request. Please try again later.")
        finally:
            conn.close()

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Catch command errors and log them."""
        if isinstance(error, commands.CheckFailure):
            await self.send_white_embed(ctx, "Permission Error", "You do not have permission to use this command.")
        elif isinstance(error, commands.MissingPermissions):
            await self.send_white_embed(ctx, "Missing Permissions", "You are missing the required permissions to use this command.")
        else:
            logging.error(f"Unexpected error in command {ctx.command}: {error}")
            await self.send_white_embed(ctx, "Unexpected Error", "An unexpected error occurred. Please try again later.")

# Setup the cog
async def setup(bot):
    await bot.add_cog(Owners(bot))
