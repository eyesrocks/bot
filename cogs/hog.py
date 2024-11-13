from discord.ext import commands, tasks  # type: ignore
from discord.ext.commands import Context, check, CommandError  # type: ignore
from discord import (  # type: ignore
    Member as DiscordMember,
    Embed,
)
from tool.greed import Greed  # type: ignore
from typing import Union, Optional  # type: ignore
from tool.important.subclasses.command import (  # type: ignore
    Member,
    User,  # type: ignore
)
from rival_tools import thread  # type: ignore
from tool.important.subclasses.color import ColorConverter  # type: ignore
from discord.utils import format_dt  # type: ignore
from collections import defaultdict
from tool.chart import EconomyCharts  # type: ignore
import random
import asyncio
import discord  # type: ignore
from discord.ui import View, Button  # type: ignore
from tool.worker import offloaded  # type: ignore
from loguru import logger  # type: ignore
from datetime import datetime, timedelta
from pytz import timezone  # type: ignore
from dataclasses import dataclass
from posthog import Posthog

posthog = Posthog(project_api_key='phc_qVSqh7vg3DdOYEF3FvFVvkPawHNNH83kPQ2WFAmeDId', host='https://greedanalytics.nick.tips')


class Hog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.description = "Posthog Analytics"

       # @self.bot.after_invoke
       # async def after_invoke(ctx):
           # posthog.capture(
              #  str(ctx.author.id),
              #  event="command executed",
               # properties={"command name": ctx.command.qualified_name},
              #  groups={"guild": str(ctx.guild.id)},
           # )

    @commands.Cog.listener("on_guild_join")
    async def on_guild_join(self, guild: discord.Guild):
        posthog.group_identify(
            "guild",
            str(guild.id),
            {
                "name": guild.name,
                "member count": guild.member_count,
            },
        )

    @commands.Cog.listener("on_guild_update")
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        posthog.group_identify(
            "guild",
            str(after.id),
            {
                "name": after.name,
                "subscription type": await get_sub_type(self, after),
                "member count": after.member_count,
            },
        )


async def get_sub_type(self, guild):
    auth = await self.bot.db.fetchrow(
        "SELECT * FROM AUTHORIZE WHERE guild_id = $1", guild.id
    )
    if auth:
        till = auth.get("till")
        if till:
            return "monthly"
        else:
            return "onetime"
    else:
        if guild.member_count > 5000:
            return "5k"
        else:
            return "none"


async def setup(bot) -> None:
    return await bot.add_cog(Hog(bot))