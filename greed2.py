# hi whoever reads this im just practicing on a separate bot for greed 2 so dont get mad at me - Lim


import discord_ios  # type: ignore # noqa: F401
import traceback
import os
import discord
import datetime
import orjson
import aiohttp
import json
from tool.worker import start_dask  # type: ignore
import asyncio  # type: ignore
import tuuid
from loguru import logger
from voice import Whisper
from tool.important.services.Webhook import Webhook as Webhooks
# from logging import getLogger
# logger = getLogger(__name__)
from typing import Any, Dict, Optional, Union, Callable
from psutil import Process
from aiohttp import ClientSession
from discord import Color, Message, Guild, AuditLogEntry, TextChannel
from discord.ext import commands
from discord.ext.commands import (
    AutoShardedBot as Bot,
    when_mentioned_or,
    BotMissingPermissions,
)
from tool.aliases import handle_aliases, CommandAlias, fill_commands  # type: ignore
from tool.modlogs import Handler  # type: ignore

# from cogs.tickets import TicketView
from tool.processing import Transformers  # type: ignore # noqa: E402
from tool.important import Cache, Context, Database, MyHelpCommand, Red  # type: ignore
from tool.important.subclasses.parser import Script  # type: ignore
from tool.important.subclasses.context import NonRetardedCache  # type: ignore
from tool.important.runner import RebootRunner  # type: ignore
from tool.snipe import Snipe, SnipeError  # type: ignore
from tool.important.subclasses.command import RolePosition  # type: ignore
from tool.views import GiveawayView, PrivacyConfirmation  # type: ignore
from tool.important.subclasses.interaction import GreedInteraction  # type: ignore # noqa: F401
from _types import catch
# from tool import MemberConverter
from rival_tools import ratelimit, lock  # type: ignore
from tool.rival import RivalAPI, get_statistics as get_stats, Statistics  # type: ignore
from tool.paginate import Paginate  # type: ignore
from sys import stdout
import jishaku

intents = discord.Intents.all()


bot = commands.AutoShardedBot(command_prefix=";", intents=intents, help_command=None)



@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")
    await bot.change_presence(activity=discord.Game(name="/pomice"))

    for filename in os.listdir('./cogs2'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs2.{filename[:-3]}')  # Removing '.py' from filename
                print(f"Loaded cog: {filename}")
            except Exception as e:
                print(f"Failed to load cog {filename}: {e}")


    try:
        await bot.load_extension('jishaku')  # Load the Jishaku extension
        print("Successfully loaded Jishaku!")
    except Exception as e:
        print(f"Failed to load Jishaku: {e}")


database = Database()

async def setup_db():
    try:
        bot.db = await database.connect()  # Attempt to connect to the database
        print(f"Successfully connected to the database!")
    except Exception as e:
        print(f"Failed to connect to the database: {e}")


bot.run("MTMwMTg2MTExNTMxMTAzMDMzMw.GbnB0U.LsO1xbjKt_FRpkegNbysRWNvS_Gssg-bl_3oZY")
