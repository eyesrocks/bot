import io
import random
import typing
from datetime import datetime
import aiohttp
import asyncio
import arrow
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Cog
from collections import defaultdict
from asyncio import Lock
from datetime import timedelta
from typing import Optional, Literal
from tool.important.services import TTS
from tool.processing import FileProcessing
from tool.important import Context  # type: ignore
from typing import Union
from discord import PartialEmoji 
import cairosvg


def generate(img: bytes) -> bytes:
    return cairosvg.svg2png(bytestring=img)

if typing.TYPE_CHECKING:
    from tool.greed import Greed  # type: ignore
from pydantic import BaseModel
from cashews import cache

DEBUG = True
cache.setup("mem://")
eros_key = "c9832179-59f7-477e-97ba-dca4a46d7f3f"


class ValorantProfile(BaseModel):
    account_level: Optional[int] = None
    avatar_url: Optional[str] = None
    current_rating: Optional[str] = None
    damage_round_ratio: Optional[float] = None
    deaths: Optional[int] = None
    headshot_percent: Optional[float] = None
    kd_ratio: Optional[float] = None
    kills: Optional[int] = None
    last_update: Optional[int] = None
    lost: Optional[int] = None
    matches_played: Optional[int] = None
    name: Optional[str] = None
    peak_rating_act: Optional[str] = None
    peak_rating: Optional[str] = None
    puuid: Optional[str] = None
    region: Optional[str] = None
    tag: Optional[str] = None
    win_percent: Optional[float] = None
    wins: Optional[int] = None

    async def to_embed(self, ctx: Context) -> discord.Embed:
        embed = discord.Embed(
            color=ctx.bot.color,
            title=f"{self.name}#{self.tag}",
            url=f"https://eros.rest/valorant?user={self.name}&tag={self.tag}",
        )
        embed.add_field(
            name="MMR",
            value=f"""**Current Rank:** {self.current_rating}\n**Peak:** {self.peak_rating}\n**Peak Act:** {self.peak_rating_act}""",
            inline=True,
        )
        embed.add_field(
            name="Stats",
            value=f"""**KDR:** {str(self.kd_ratio)[2]}\n**WR:** {str(self.wr_ratio)[2]}\n**HSR:** {str(self.hs_ratio)[2]}\n""",
            inline=True,
        )
        embed.set_thumbnail(url=self.avatar_url)
        embed.set_footer(
            text=f"Region: {self.region} | Matches: {self.matches_played} | DPR: {int(self.damage_round_ratio)}"
        )
        return embed

    @classmethod
    async def from_snowflake(cls, user: str, tag: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://eros.rest/valorant",
                params={"user": user, "tag": tag},
                headers={"api-key": eros_key},
            ) as response:
                data = await response.read()
        return cls.parse_raw(data)  # type: ignore


class ValorantUser(commands.Converter):
    async def convert(self, ctx: Context, argument: str):  # type: ignore
        if "#" not in argument:
            raise commands.CommandError(
                "please include a `#` inbetween the user and tag"
            )
        return argument.split("#")


snipe_message_author = {}
snipe_message_content = {}
snipe_message_attachment = {}
snipe_message_author_avatar = {}
snipe_message_time = {}
snipe_message_sticker = {}
snipe_message_embed = {}
from tool import valorant  # noqa: E402


class Miscellaneous(Cog):
    def __init__(self, bot: "Greed") -> None:
        self.bot = bot
        self.color = self.bot.color
        self.bot.afks = {}
        self.texttospeech = TTS()
        self.file_processor = FileProcessing(self.bot)
        self.queue = defaultdict(Lock)
    #     self.auto_destroy.start()

    # @tasks.loop(minutes = 10)
    # async def auto_destroy(self):
    #     for client in self.bot.voice_clients:
    #         if client.channel and len(client.channel.members) < 2:
    #             try: 
    #                 await client.destroy()
    #             except: 
    #                 await client.disconnect()

    @commands.command(
        name="valorant",
        brief="lookup a user's valorant stats",
        usage=",valorant <user>#<tag>",
        example=",valorant cop#00001",
    )
    async def valorant(self, ctx: Context, user: ValorantUser):
        #      try:
        return await valorant.valorant(ctx, f"{user[0]}#{user[1]}")
        #        except Exception:
        #           return await ctx.fail(f"that valorant user couldn't be fetched")
        embed = await data.to_embed(ctx)  # type: ignore  # noqa: F821
        return await ctx.send(embed=embed)

    @commands.command(
        name="variables",
        brief="show all embed variables used for the bots embed creator",
        example=",variables",
    )
    async def variables(self, ctx: Context):
        from tool.important.subclasses.parser import Script  # type: ignore

        b = Script("{embed}{description: sup}", user=ctx.author)
        rows = [f"`{k}`" for k in b.replacements.keys()]
        rows.extend([f"`{k}`" for k in ["{timer}", "{ends}", "{prize}"]])
        return await self.bot.dummy_paginator(
            ctx, discord.Embed(title="variables", color=self.bot.color), rows
        )
    
    async def do_tts(self, message: str, model: Optional[str] = "amy") -> str:
        try:
            return await self.texttospeech.tts_api(model, "en_US", "low", message)
        except Exception as e:
            if DEBUG:
                raise e
            from aiogtts import aiogTTS  # type: ignore
            i = io.BytesIO()
            aiogtts = aiogTTS()
            await aiogtts.save(message, ".tts.mp3", lang="en")
            await aiogtts.write_to_fp(message, i, slow=False, lang="en")
            return ".tts.mp3"

    @commands.command(
        name="tts",
        brief="Allow the bot to speak to a user in a voice channel",
        example=",tts whats up guys",
    )
    async def tts(self, ctx: Context, model: Optional[Literal["amy","danny","arctic","hfc_female","hfc_male","joe","kathleen","kusal","lessac","ryan",]] = "amy", *, message: str):
        fp = await self.do_tts(message, model)
        if ctx.author.voice is None:
            msg = await self.file_processor.upload_to_discord(ctx.channel, fp)
            await self.texttospeech.delete_soon(fp, 3)
            await self.texttospeech.delete_soon(fp.replace(".mp3", ".ogg"), 3)
            return msg
        if voice_channel := ctx.author.voice.channel:
#            if ctx.voice_client is None:
 #           else:
            try: 
                await ctx.voice_client.disconnect()
            except Exception: 
                pass
            vc = await voice_channel.connect()
  #                  await ctx.voice_client.move_to(voice_channel)
            #            aiogtts = aiogTTS()
            async with self.queue[ctx.guild.id]:
                await asyncio.sleep(0.5)
                try:
                    vc.play(discord.FFmpegPCMAudio(source=fp))
                except Exception as e: 
                    raise e #return await ctx.reply(file = discord.File("./.tts.mp3"))
        #                os.remove(".tts.mp3")
                await self.texttospeech.delete_soon(fp, 3)
        else:
            return await ctx.fail("you aren't in a voice channel")

    @commands.command(
        name="afk",
        brief="Set an afk message before going offline",
        example=",afk going to that little girls house",
    )
    async def afk(
        self, ctx: commands.Context, *, status: str = "AFK"
    ) -> discord.Message:
        if self.bot.afks.get(ctx.author.id):
            return await ctx.warning("You are **already afk**")
        self.bot.afks[ctx.author.id] = {"date": datetime.now(), "status": str(status)}
        return await ctx.success(f"**You're now afk** with the status: `{status[:25]}`")

    @commands.command(name="ramdomuser")
    async def randomuser(ctx):
     # Get the list of all members in the server
        members = ctx.guild.members
     
     # Filter out bots if you want to exclude them
        human_members = [member for member in members if not member.bot]
     
     # Check if there are human members available
        if not human_members:
              await ctx.send("No human members found in the server.")
              return

     # Pick a random member
        chosen_member = random.choice(human_members)

     # Send the selected member's username
         await ctx.send(f"Randomly selected user: {chosen_member.name}")

    @commands.command(
        name="snipe",
        aliases=["s"],
        example=",snipe 4",
        breif="Retrive a recently deleted message",
    )
    async def snipe(self, ctx: Context, index: int = 1):
        if not (
            snipe := await self.bot.snipes.get_entry(
                ctx.channel, type="snipe", index=index
            )
        ):
            return await ctx.fail(
                f"There are **no deleted messages** for {ctx.channel.mention}"
            )
        total = snipe[1]
        snipe = snipe[0]
        if await self.bot.db.fetch(
            """SELECT * FROM filter_event WHERE guild_id = $1 AND event = $2""",
            ctx.guild.id,
            "snipe",
        ):
            if content := snipe.get("content"):
                if (
                    "discord.gg/" in content.lower()
                    or "discord.com/" in content.lower()
                    or "discordapp.com/" in content.lower()
                ):
                    return await ctx.fail("snipe had **filtered content**")
                content = "".join(c for c in content if c.isalnum() or c.isspace())
                if (
                    "discord.gg" in content.lower()
                    or "discord.com/" in content.lower()
                    or "discordapp.com" in content.lower()
                ):
                    return await ctx.fail("snipe had **filtered content**")
                for keyword in self.bot.cache.filter.get(ctx.guild.id, []):
                    if keyword.lower() in content.lower():
                        return await ctx.fail("snipe had **filtered content**")
        embed = discord.Embed(
            color=self.bot.color,
            description=(
                snipe.get("content")
                or (
                    snipe["embeds"][0].get("description") if snipe.get("embeds") else ""
                )
            ),
            timestamp=datetime.fromtimestamp(snipe.get("timestamp")),
        )

        embed.set_author(
            name=snipe.get("author").get("name"),
            icon_url=snipe.get("author").get("avatar"),
        )

        if att := snipe.get("attachments"):
            embed.set_image(url=att[0])

        elif sticks := snipe.get("stickers"):
            embed.set_image(url=sticks[0])

        embed.set_footer(
            text=f"Deleted {arrow.get(snipe.get('timestamp')).humanize()} | {index}/{total}"
        )

        return await ctx.send(embed=embed)

    @commands.command(
        name="editsnipe",
        aliases=["es"],
        example=",editsnipe 2",
        brief="Retrieve a messages original text before edited",
    )
    async def editsnipe(self, ctx: Context, index: int = 1):
        if not (
            snipe := await self.bot.snipes.get_entry(
                ctx.channel, type="editsnipe", index=index
            )
        ):
            return await ctx.fail("There is nothing to snipe.")
        total = snipe[1]
        snipe = snipe[0]
        if await self.bot.db.fetch(
            """SELECT * FROM filter_event WHERE guild_id = $1 AND event = $2""",
            ctx.guild.id,
            "snipe",
        ):
            if content := snipe.get("content"):
                if (
                    "discord.gg/" in content.lower()
                    or "discord.com/" in content.lower()
                    or "discordapp.com/" in content.lower()
                ):
                    return await ctx.fail("snipe had **filtered content**")
                content = "".join(c for c in content if c.isalnum() or c.isspace())
                if (
                    "discord.gg" in content.lower()
                    or "discord.com/" in content.lower()
                    or "discordapp.com/" in content.lower()
                ):
                    return await ctx.fail("snipe had **filtered content**")
                for keyword in self.bot.cache.filter.get(ctx.guild.id, []):
                    if keyword.lower() in content.lower():
                        return await ctx.fail("editsnipe had **filtered content**")
        embed = discord.Embed(
            color=self.bot.color,
            description=(
                snipe.get("content")
                or ("Message contains an embed" if snipe.get("embeds") else "")
            ),
            timestamp=datetime.fromtimestamp(snipe.get("timestamp")),
        )

        embed.set_author(
            name=snipe.get("author").get("name"),
            icon_url=snipe.get("author").get("avatar"),
        )

        if att := snipe.get("attachments"):
            embed.set_image(url=att[0])

        elif sticks := snipe.get("stickers"):
            embed.set_image(url=sticks[0])

        embed.set_footer(
            text=f"Edited {arrow.get(snipe.get('timestamp')).humanize()} | {index}/{total}",
            icon_url=ctx.author.display_avatar,
        )

        return await ctx.send(embed=embed)

    @commands.command(
        name="reactionsnipe",
        aliases=["reactsnipe", "rs"],
        brief="Retrieve a deleted reaction from a message",
        example=",reactionsipe 2",
    )
    async def reactionsnipe(self, ctx: Context, index: int = 1):
        if not (
            snipe := await self.bot.snipes.get_entry(
                ctx.channel, type="reactionsnipe", index=index
            )
        ):
            return await ctx.fail("There is nothing to snipe.")
        snipe[1]  # type: ignore
        snipe = snipe[0]
        embed = discord.Embed(
            color=self.bot.color,
            description=(
                f"""**{str(snipe.get('author').get('name'))}** reacted with {snipe.get('reaction')
                if not snipe.get('reaction').startswith('https://cdn.discordapp.com/')
                else str(snipe.get('reaction'))} <t:{int(snipe.get('timestamp'))}:R>"""
            ),
        )

        return await ctx.send(embed=embed)

    @commands.command(
        name="clearsnipe",
        aliases=["cs"],
        brief="Clear all deleted messages from greed",
        example=",clearsnipe",
    )
    @commands.has_permissions(manage_messages=True)
    async def clearsnipes(self, ctx: Context):
        await self.bot.snipes.clear_entries(ctx.channel)
        return await ctx.success(f"**Cleared** snipes for {ctx.channel.mention}")

    @commands.group(
        name="birthday",
        aliases=["bday"],
        brief="get a user's birthday or set your own",
        example=",bday @aiohttp",
        usage=",bday {member}",
    )
    async def birthday(self, ctx, *, member: typing.Optional[discord.Member]):
        if ctx.invoked_subcommand is None:
            if not member:
                mem = "your"
                member = ctx.author
            else:
                mem = f"{member.mention}'s"
            date = await self.bot.db.fetchval(
                """SELECT ts FROM birthday WHERE user_id = $1""", member.id
            )
            if date:
                try:
                    if "ago" in arrow.get(date).humanize(granularity="day"):
                        date = arrow.get(date).shift(years=1)
                    else:
                        date = date
                    if arrow.get(date).humanize(granularity="day") == "in 0 days":
                        # date="tomorrow"
                        now = arrow.now()
                        d = arrow.get(date).humanize(now)
                        date = d
                    else:
                        date = arrow.get(
                            (arrow.get(date).datetime + timedelta(days=1))
                        ).humanize(granularity="day")
                    await ctx.send(
                        embed=discord.Embed(
                            color=self.color,
                            description=f"🎂 {mem} birthday is **{date}**",
                        )
                    )
                except Exception:
                    await ctx.send(
                        embed=discord.Embed(
                            color=self.color,
                            description=f"🎂 {mem} birthday is **today**",
                        )
                    )
            else:
                await ctx.fail(
                    f"{mem} birthday is not set, set it using `{ctx.prefix}bday set`"
                )

    @birthday.command(
        name="set",
        brief="set your birthday",
        usage=",birthday set {month} {day}",
        example=",birthday set August 10",
    )
    async def birthday_set(self, ctx, month: str, day: Optional[str]):
        if "/" in month:
            month, day = month.split("/")[0:2]
        try:
            if len(month) == 1:
                mn = "M"
            elif len(month) == 2:
                mn = "MM"
            elif len(month) == 3:
                mn = "MMM"
            else:
                mn = "MMMM"
            if "th" in day:
                day = day.replace("th", "")
            if "st" in day:
                day = day.replace("st", "")
            if len(day) == 1:
                dday = "D"
            else:
                dday = "DD"
            datee = arrow.now().date()
            ts = f"{month} {day} {datee.year}"
            if "ago" in arrow.get(ts, f"{mn} {dday} YYYY").humanize(granularity="day"):
                year = datee.year + 1
            else:
                year = datee.year
            string = f"{month} {day} {year}"
            date = arrow.get(string, f"{mn} {dday} YYYY").replace(tzinfo="America/New_York").to("UTC").datetime
            await self.bot.db.execute(
                """INSERT INTO birthday (user_id, ts) VALUES($1, $2) ON CONFLICT(user_id) DO UPDATE SET ts = excluded.ts""",
                ctx.author.id,
                date,
            )
            await ctx.success(f"set your birthday as `{month}` `{day}`")
        except Exception as e:
            if ctx.author.name == "aiohttp":
                raise e
            return await ctx.fail(
                f"please use this format `,birthday set <month> <day>` \n {e}"
            )

    @birthday.command(
        name="reset", brief="Clear your set birthday", example="birthday reset"
    )
    async def birthday_clear(self, ctx: Context):
        bday = await self.bot.db.fetchval(
            "SELECT ts FROM birthday WHERE user_id = $1;", ctx.author.id
        )
        if not bday:
            return await ctx.fail("You **don't have a birthday** set to clear")

        await self.bot.db.execute(
            "DELETE FROM birthday WHERE user_id = $1;",
            ctx.author.id,
        )
        return await ctx.success("**reset** your **birthday settings**")

    @commands.command(
        name="selfpurge",
        example=",selfpurge 100",
        brief="Clear your messages from a chat",
    )
    @commands.bot_has_permissions(manage_messages=True)
    async def selfpurge(self, ctx, amount: int):
        amount = amount + 1

        def check(message):
            return message.author == ctx.message.author

        await ctx.message.delete()
        deleted_messages = await ctx.channel.purge(limit=amount, check=check)
        if len(deleted_messages) > amount:
            deleted_messages = deleted_messages[:amount]
            return

    async def check_role(self, ctx, role: discord.Role):
        if (
            ctx.author.top_role.position <= role.position
            and not ctx.author.id == ctx.guild.owner_id
        ):
            await ctx.fail("your role isn't higher then that role")
            return False
        return True


        
    @commands.command(name="imageonly", brief="Toggle image only mode in a channel")
    @commands.has_permissions(manage_messages=True)
    async def imageonly(self, ctx: Context):
        if await self.bot.db.fetchval(
            "SELECT * FROM imageonly WHERE channel_id = $1", ctx.channel.id
        ):
            await self.bot.db.execute(
                "DELETE FROM imageonly WHERE channel_id = $1", ctx.channel.id
            )
            return await ctx.success("Disabled image only mode")
        await self.bot.db.execute(
            "INSERT INTO imageonly (channel_id) VALUES($1)", ctx.channel.id
        )
        return await ctx.success("Enabled image only mode")
    
    
    @commands.command(name="enlarge", aliases=["downloademoji", "e", "jumbo"])
    async def enlarge(self, ctx, emoji: Union[discord.PartialEmoji, str] = None):
        """
        Get an image version of a custom server emoji
        """
        if not emoji:
            return await ctx.fail("Please provide an emoji to enlarge")

        if isinstance(emoji, PartialEmoji):
            return await ctx.reply(
                file=await emoji.to_file(
                    filename=f"{emoji.name}{'.gif' if emoji.animated else '.png'}"
                )
            )

        elif isinstance(emoji, str):
            if not emoji.startswith('<'):
                return await ctx.fail("You can only enlarge custom server emojis")
                
            try:
                name = emoji.split(":")[1]
                emoji_id = emoji.split(":")[2][:-1]
                
                if emoji.startswith('<a:'):
                    # Animated emoji
                    url = f"https://cdn.discordapp.com/emojis/{emoji_id}.gif"
                    name += ".gif"
                else:
                    # Static emoji
                    url = f"https://cdn.discordapp.com/emojis/{emoji_id}.png"
                    name += ".png"
                    
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            return await ctx.fail("Could not download that emoji")
                        img = io.BytesIO(await resp.read())
                        
                return await ctx.send(file=discord.File(img, filename=name))
                
            except (IndexError, KeyError):
                return await ctx.fail("That doesn't appear to be a valid custom emoji")




async def setup(bot: "Greed") -> None: 
    await bot.add_cog(Miscellaneous(bot))
