import os
from discord import Message
from discord.ext import commands
from discord.ext.commands import Context, BadArgument
from discord import Embed, TextChannel
import discord
import asyncio
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from googleapiclient.discovery import build
from io import BytesIO
from typing import List
import base64
import textwrap
import random
import aiohttp
from color_processing import ColorInfo
from tool.emotes import EMOJIS
from typing import List, Dict, Set, Optional
from random import choice
from tool.managers.bing import BingService
from dataclasses import dataclass, field
from tool.worker import offloaded
# from greed.tool import aliases

@offloaded
def get_dominant_color(image_bytes: bytes) -> dict:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    colors = image.getcolors(maxcolors=1000000)
    colorful_colors = [color for color in colors if len(set(color[1])) > 1]
    dominant_color = max(colorful_colors, key=lambda item: item[0])[1]
    return {"dominant_color": dominant_color}


@offloaded
def rotate_image(image_bytes: bytes, angle: int) -> bytes:
    image = Image.open(BytesIO(image_bytes)).rotate(angle, expand=True)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()

@offloaded
def compress_image(image_bytes: bytes, quality: int = None) -> bytes:
    image = Image.open(BytesIO(image_bytes))
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality or 10, optimize=True)
    return output.getvalue()


@offloaded
def do_caption(para: list, image_bytes: bytes, message_data: dict):
    if isinstance(image_bytes, BytesIO):
        image_bytes = image_bytes.getvalue()
    image = Image.open(BytesIO(image_bytes))
    haikei = Image.open("quote/grad.jpeg")
    black = Image.open("quote/black.jpeg")
    w, h = (680, 370)
    haikei = haikei.resize((w, h))
    black = black.resize((w, h))
    icon = image.resize((h, h))

    new = Image.new(mode="L", size=(w, h))
    icon = icon.convert("L")
    black = black.convert("L")
    icon = icon.crop((40, 0, 680, 370))
    new.paste(icon)

    sa = Image.composite(new, black, haikei.convert("L"))
    draw = ImageDraw.Draw(sa)
    fnt = ImageFont.truetype("quote/Arial.ttf", 28)

    _, _, w2, h2 = draw.textbbox((0, 0), "a", font=fnt)
    i = (int(len(para) / 2) * w2) + len(para) * 5
    current_h, pad = 120 - i, 0

    for line in para:
        if message_data['content'].replace("\n", "").isascii():
            _, _, w3, h3 = draw.textbbox(
                (0, 0), line.ljust(int(len(line) / 2 + 11), " "), font=fnt
            )
            draw.text(
                (11 * (w - w3) / 13 + 10, current_h + h2),
                line.ljust(int(len(line) / 2 + 11), " "),
                font=fnt,
                fill="#FFF",
            )
        else:
            _, _, w3, h3 = draw.textbbox(
                (0, 0), line.ljust(int(len(line) / 2 + 5), "　"), font=fnt
            )
            draw.text(
                (11 * (w - w3) / 13 + 10, current_h + h2),
                line.ljust(int(len(line) / 2 + 5), "　"),
                font=fnt,
                fill="#FFF",
            )

        current_h += h3 + pad

    dr = ImageDraw.Draw(sa)
    font = ImageFont.truetype("quote/Arial.ttf", 15)
    _, _, authorw, _ = dr.textbbox((0, 0), f"-{message_data['author']}", font=font)

    output = BytesIO()
    dr.text(
        (480 - int(authorw / 2), current_h + h2 + 10),
        f"-{message_data['author']}",
        font=font,
        fill="#FFF",
    )
    sa.save(output, format="JPEG")
    output_bytes = output.getvalue()
    return output_bytes

GOOGLE_API_KEY = "AIzaSyCgPL4hAT14sdyylXxY_R-hXJN4XMo7zZo"
SEARCH_ENGINE_ID = "8691350b6083348ae"
class TicTacToeButton(discord.ui.Button):
    """
    Represents a button on the Tic Tac Toe board.
    """
    def __init__(self, x: int, y: int, player1: discord.Member, player2: discord.Member):
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=y)
        self.x = x
        self.y = y
        self.player1 = player1
        self.player2 = player2

    async def callback(self, interaction: discord.Interaction):
        """
        Handles the button click event.
        """
        assert self.view is not None
        view: 'TicTacToe' = self.view
        if view.board[self.y][self.x] in (view.X, view.O):
            return

        # Check if it's the correct player's turn
        if (view.current_player == view.X and interaction.user.id != self.player1.id) or (view.current_player == view.O and interaction.user.id != self.player2.id):
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)

        self.style = discord.ButtonStyle.danger if view.current_player == view.X else discord.ButtonStyle.success
        self.label = 'X' if view.current_player == view.X else 'O'
        self.disabled = True
        view.board[self.y][self.x] = view.current_player

        # Switch the turn
        view.switch_player()

        # Check for a winner
        winner = view.check_board_winner()
        if winner is not None:
            content = (
                "It's a tie!" if winner == view.Tie else
                f"**{self.player1.mention if winner == view.X else self.player2.mention}** won!"
            )
            # Disable all buttons and stop the view
            for child in view.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            view.stop()
        else:
            content = f"It's **{self.player1.mention if view.current_player == view.X else self.player2.mention}**'s turn."

        # Update the message
        await interaction.response.edit_message(content=content, view=view)


class TicTacToe(discord.ui.View):
    """
    Represents the Tic Tac Toe game board and logic.
    """
    children: List[TicTacToeButton]
    X = -1
    O = 1
    Tie = 0

    def __init__(self, player1: discord.Member, player2: discord.Member):
        super().__init__()
        self.current_player = self.X
        self.player1 = player1
        self.player2 = player2
        self.board = [[0 for _ in range(3)] for _ in range(3)]

        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y, player1, player2))

    def check_board_winner(self) -> Optional[int]:
        """
        Checks the board for a winner or tie.
        Returns:
            - X (-1) if player 1 wins
            - O (1) if player 2 wins
            - Tie (0) if the game is a draw
            - None if the game is still ongoing
        """
        board = self.board

        lines = (
            board +  # Rows
            [list(col) for col in zip(*board)] +  # Columns
            [[board[i][i] for i in range(3)], [board[i][2 - i] for i in range(3)]]  # Diagonals
        )

        for line in lines:
            if all(cell == self.X for cell in line):
                return self.X
            if all(cell == self.O for cell in line):
                return self.O

        if all(cell != 0 for row in board for cell in row):
            return self.Tie

        return None

    def switch_player(self):
        """
        Switches the current player.
        """
        self.current_player = self.O if self.current_player == self.X else self.X

    async def on_timeout(self):
        """
        Handles the timeout event when the game times out.
        """
        for item in self.children:
            item.disabled = True
        if hasattr(self, "message"):
            await self.message.edit(view=self)
    

class GuildData:
    """
    Holds per-guild data for the BlackTea game.
    """
    def __init__(self):
        self.players: List[int] = []
        self.lives: Dict[str, int] = {}
        self.guessed_words: Set[str] = set()


class BlackTea:
    """
    Manages the core mechanics of the BlackTea game.
    """
    LIFE_LIMIT = 3
    WORDS_URL = "https://www.mit.edu/~ecprice/wordlist.100000"

    def __init__(self, bot):
        self.bot = bot
        self.color = 0xA5D287
        self.emoji = "<a:boba_tea_green_gif:1302250923858591767>"
        self.match_started: Set[int] = set()
        self.guild_data: Dict[int, GuildData] = {}
        self.lock = asyncio.Lock()

    async def fetch_word_list(self) -> List[str]:
        """
        Fetches a word list from the predefined URL.
        """
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.WORDS_URL) as response:
                    response.raise_for_status()
                    return [
                        line.strip() for line in (await response.text()).splitlines() if len(line.strip()) > 3
                    ]
            except Exception as e:
                raise RuntimeError("Failed to fetch words") from e

    @staticmethod
    def pick_random_prefix(words: List[str]) -> str:
        """
        Picks a random 3-letter prefix from the list of valid words.
        """
        valid_words = [word for word in words if len(word) > 3]
        if not valid_words:
            raise ValueError("No suitable words found.")
        return random.choice(valid_words)[:3]

    async def decrement_life(self, member_id: str, channel: TextChannel, reason: str):
        """
        Reduces a player's life and handles elimination if lives reach zero.
        """
        guild_id = channel.guild.id
        guild_data = self.guild_data.get(guild_id)

        if not guild_data or member_id not in guild_data.lives:
            raise ValueError("Player data not initialized.")

        guild_data.lives[member_id] += 1
        remaining_lives = self.LIFE_LIMIT - guild_data.lives[member_id]

        if remaining_lives <= 0:
            guild_data.players.remove(int(member_id))
            del guild_data.lives[member_id]
            await self.send_embed(channel, f"☠️ <@{member_id}> is eliminated!")
        else:
            await self.send_embed(
                channel,
                f"💥 <@{member_id}> lost a life ({reason}). {remaining_lives} lives left.",
            )

    async def send_embed(self, channel: TextChannel, content: str) -> Message:
        """
        Sends an embedded message to the specified channel.
        """
        embed = Embed(color=self.color, description=content)
        return await channel.send(embed=embed)

    async def handle_guess(
        self,
        user: int,
        channel: TextChannel,
        prefix: str,
        words: List[str],
        session: GuildData,
    ):
        """
        Handles a player's guessing turn with countdown reactions and timeout handling.
        """
        member = channel.guild.get_member(user)
        member_id = str(user)

        TOTAL_TIMEOUT = 10  # Total time for the player to guess
        INITIAL_TIMEOUT = 7  # Initial wait before countdown starts
        COUNTDOWN_REACTIONS = ["3️⃣", "2️⃣", "1️⃣"]

        # Announce the string the player needs to guess
        prompt_message = await self.send_embed(
            channel,
            f"🎯 {member.mention}, your word must contain: **{prefix}**. "
            "You have 10 seconds to respond!"
        )

        try:
            # Wait for the player's message during the initial timeout
            message: Message = await self.bot.wait_for(
                "message",
                check=lambda m: (
                    m.channel.id == channel.id
                    and m.author.id == user
                    and m.content.lower() in words
                    and prefix.lower() in m.content.lower()
                    and m.content.lower() not in session.guessed_words
                ),
                timeout=INITIAL_TIMEOUT,
            )

            # Process a correct guess if received during the initial period
            session.guessed_words.add(message.content.lower())
            await self.send_embed(channel, f"✅ Correct answer, {member.mention}!")
            return True

        except asyncio.TimeoutError:
            # Start the countdown by reacting to the original prompt
            for reaction in COUNTDOWN_REACTIONS:
                await prompt_message.add_reaction(reaction)
                await asyncio.sleep(1)

            # Deduct a life if no valid guess was made
            await self.decrement_life(member_id, channel, "timeout")
            return False

    async def start_match(self, guild_id: int):
        """
        Starts a new match, ensuring no existing match is in progress.
        """
        async with self.lock:
            if guild_id in self.match_started:
                raise ValueError("A BlackTea match is already in progress.")
            self.match_started.add(guild_id)
            if guild_id not in self.guild_data:
                self.guild_data[guild_id] = GuildData()

    def reset_guild_data(self, guild_id: int):
        """
        Resets guild-specific game data.
        """
        self.guild_data.pop(guild_id, None)
        self.match_started.discard(guild_id)



class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.blacktea = BlackTea(self.bot)
        self.bing = BingService(self.bot.redis, None)
        self.flavors = [
            "Strawberry",
            "Mango",
            "Blueberry",
            "Watermelon",
            "Grape",
            "Pineapple",
            "Vanilla",
            "Chocolate",
            "Caramel",
            "Mint",
            "Coffee",
            "Cinnamon",
            "Bubblegum",
            "Peach",
            "Apple",
            "Lemon",
            "Cherry",
            "Raspberry",
        ]



    async def get_caption(
        self, ctx: Context, message: Optional[discord.Message] = None
    ):
        
        if message is None:
            msg = ctx.message.reference
            if msg is None:
                return await ctx.fail("no **message** or **reference** provided")
            id = msg.message_id
            message = await ctx.fetch_message(id)

        image = BytesIO(await message.author.display_avatar.read())
        image.seek(0)
        if message.content.replace("\n", "").isascii():
            para = textwrap.wrap(message.clean_content, width=26)
        else:
            para = textwrap.wrap(message.clean_content, width=13)

        output = await do_caption(para, image, message_data={"author": message.author.name, "content": message.content})
        buffer = BytesIO(output)
        buffer.seek(0)
        file = discord.File(fp=buffer, filename="quote.png")
        return await ctx.send(file=file)

    @commands.command(name="uwuify", brief="uwuify a message", aliases=["uwu"])
    async def uwuify(self, ctx: Context, *, message: str):
        try:
            text = await self.bot.rival.uwuify(message)
            return await ctx.send(text)
        except Exception:  # noqa: E722
            return await ctx.fail("couldn't uwuify that message")

    @commands.group(name="blacktea", invoke_without_command=True)
    async def blacktea(self, ctx: commands.Context):
        """
        Starts a BlackTea game with server members.
        """
        guild_id = ctx.guild.id

        try:
            await self.blacktea.start_match(guild_id)
        except ValueError as e:
            return await ctx.send(str(e))

        embed = Embed(
            color=self.blacktea.color,
            title="BlackTea Matchmaking",
            description=(
                "React to join the game!\n"
                "Each player will take turns guessing words containing specific letters.\n"
                "Run out of time or make incorrect guesses, and you lose lives. "
                "The last player standing wins!"
            ),
        )
        message = await ctx.send(embed=embed)

        try:
            await message.add_reaction("☕")
        except Exception as e:
            self.blacktea.reset_guild_data(guild_id)
            return await ctx.send(f"Failed to add reaction: {e}")

        await asyncio.sleep(10)

        try:
            fetched_message = await ctx.channel.fetch_message(message.id)
            if not fetched_message.reactions:
                self.blacktea.reset_guild_data(guild_id)
                return await ctx.send("No reactions were added to the BlackTea message.")
        except Exception:
            self.blacktea.reset_guild_data(guild_id)
            return await ctx.send("The BlackTea message was deleted.")

        users = [
            u.id async for u in fetched_message.reactions[0].users()
            if u.id != self.bot.user.id and not u.bot
        ]

        if len(users) < 2:
            self.blacktea.reset_guild_data(guild_id)
            return await ctx.send("Not enough players to start.")

        words = await self.blacktea.fetch_word_list()
        guild_data = self.blacktea.guild_data[guild_id]
        guild_data.players = users
        guild_data.lives = {str(user): 0 for user in users}

        while len(guild_data.players) > 1:
            for user in list(guild_data.players):
                prefix = self.blacktea.pick_random_prefix(words)
                correct = await self.blacktea.handle_guess(
                    user=user,
                    channel=ctx.channel,
                    prefix=prefix,
                    words=words,
                    session=guild_data,
                )
                if not correct and user not in guild_data.players:
                    break

        winner = guild_data.players[0]
        await self.blacktea.send_embed(ctx.channel, f"👑 <@{winner}> won the game!")
        self.blacktea.reset_guild_data(guild_id)

    @blacktea.command(name="end")
    async def blacktea_end(self, ctx):
        """
        Ends an ongoing BlackTea match.
        """
        self.blacktea.reset_guild_data(ctx.guild.id)
        await ctx.send("BlackTea match ended.")

    @commands.command()
    async def spark(self, ctx):
        user_id = ctx.author.id
        row = await self.bot.db.fetchrow(
            "SELECT sparked, last_sparked FROM blunt_hits WHERE user_id = $1", user_id
        )

        if row:
            sparked, last_sparked = row
            if not sparked or (datetime.now() - last_sparked).total_seconds() > 300:
                await self.bot.db.execute(
                    """
                    INSERT INTO blunt_hits (user_id, sparked, last_sparked)
                    VALUES ($1, TRUE, $2)
                    ON CONFLICT (user_id)
                    DO UPDATE SET sparked = TRUE, last_sparked = $2
                """,
                    user_id,
                    datetime.now(),
                )
                embed = discord.Embed(
                    description=f"{EMOJIS['arolighter']} {ctx.author.mention} sparked the blunt!",
                    color=self.bot.color,
                )
                await ctx.send(embed=embed)
            else:
                remaining_time = timedelta(seconds=300) - (
                    datetime.now() - last_sparked
                )
                remaining_minutes, remaining_seconds = divmod(
                    int(remaining_time.total_seconds()), 60
                )
                embed = discord.Embed(
                    description=f"{ctx.author.mention}, you need to wait {remaining_minutes} minutes and {remaining_seconds} seconds before sparking another blunt!",
                    color=self.bot.color,
                )
                await ctx.send(embed=embed)
        else:
            await self.bot.db.execute(
                """
                INSERT INTO blunt_hits (user_id, sparked, last_sparked)
                VALUES ($1, TRUE, $2)
            """,
                user_id,
                datetime.now(),
            )
            embed = discord.Embed(
                description=f"{EMOJIS['arolighter']} {ctx.author.mention} sparked their first blunt!",
                color=self.bot.color,
            )
            await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def smoke(self, ctx):
        user_id = ctx.author.id
        row = await self.bot.db.fetchrow(
            "SELECT sparked, taps FROM blunt_hits WHERE user_id = $1", user_id
        )

        if row and row[0]:  # If sparked is True
            taps = row[1]
            if taps < 100000000:
                await self.bot.db.execute(
                    "UPDATE blunt_hits SET taps = taps + 1 WHERE user_id = $1", user_id
                )
                embed = discord.Embed(
                    description=f"{EMOJIS['d_smoke']}  {ctx.author.mention} took a hit from the blunt!",
                    color=self.bot.color,
                )
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    description=f"{ctx.author.mention}, your blunt has gone out!",
                    color=self.bot.color,
                )
                await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                description="You need to spark the blunt first!", color=self.bot.color
            )
            await ctx.send(embed=embed)

    @commands.command()
    async def taps(self, ctx):
        user_id = ctx.author.id
        taps = (
            await self.bot.db.fetchval(
                "SELECT taps FROM blunt_hits WHERE user_id = $1", user_id
            )
            or 0
        )

        embed = discord.Embed(
            description=f"{ctx.author.mention} has taken {taps} hits from the blunt.",
            color=self.bot.color,
        )
        await ctx.send(embed=embed)

    @commands.command(help="shows how gay you are", description="fun", usage="<member>")
    async def howgay(self, ctx, user: discord.Member = None):

        percentage = random.randint(1, 100)

        if user is None:
            embed = discord.Embed(
                color=self.bot.color,
                title="gay r8",
                description=f"{ctx.author.mention} is `{percentage}%` gay",
            )
            await ctx.reply(embed=embed, mention_author=False)
        else:
            embed = discord.Embed(
                color=self.bot.color,
                title="gay r8",
                description=f"{user.mention} is `{percentage}%` gay",
            )
            await ctx.reply(embed=embed, mention_author=False)

    @commands.command(help="shows your iq", description="fun", usage="<member>")
    async def iq(self, ctx, user: discord.Member = None):
        if user is None:
            embed = discord.Embed(
                color=self.bot.color,
                title="iq test",
                description=f"{ctx.author.mention} has `{random.randrange(201)}` iq :brain:",
            )
            await ctx.reply(embed=embed, mention_author=False)
        else:
            embed = discord.Embed(
                color=self.bot.color,
                title="iq test",
                description=f"{user.mention} has `{random.randrange(201)}` iq :brain:",
            )
            await ctx.reply(embed=embed, mention_author=False)

    @commands.command(
        help="shows how many bitches you have", description="fun", usage="<member>"
    )
    async def bitches(self, ctx, user: discord.Member = None):
        user = user or ctx.author
        await ctx.reply(
            embed=discord.Embed(
                color=self.bot.color,
                description=f"{user.mention} has `{random.randrange(51)}` bitches",
            ),
            mention_author=False,
        )

    @commands.group(name="vape", brief="Hit the vape", invoke_without_command=True, aliases=["hit"])
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def vape(self, ctx):
        has_vape = await self.bot.db.fetchrow(
            "SELECT holder, guild_hits FROM vape WHERE guild_id = $1", ctx.guild.id
        )

        # Check if the vape exists in the server
        if not has_vape:
            return await ctx.send(
                embed=discord.Embed(
                    description="> The vape doesn't exist in this server. Someone needs to claim it first!",
                    color=self.bot.color,
                )
            )

        # Check if anyone currently holds the vape
        holder_id = has_vape["holder"]
        if holder_id is None:
            return await ctx.send(
                embed=discord.Embed(
                    description="> No one has the vape yet. Steal it using the **`vape steal`** command.",
                    color=self.bot.color,
                )
            )

        # Check if the user is the current holder
        if holder_id != ctx.author.id:
            holder = ctx.guild.get_member(holder_id)
            holder_message = (
                f"> You don't have the vape! Steal it from **{holder.display_name}**."
                if holder
                else "> The vape holder is no longer in this server. Someone else can claim it!"
            )
            return await ctx.send(
                embed=discord.Embed(description=holder_message, color=self.bot.color)
            )

        # Vape hit sequence
        embed = discord.Embed(
            description=f"{EMOJIS['vape']} {ctx.author.mention} is about to take a hit of the vape...",
            color=self.bot.color,
        )
        message = await ctx.send(embed=embed)
        await asyncio.sleep(2.3)

        # Update hit count and display new total
        guild_hits = has_vape["guild_hits"] + 1
        await self.bot.db.execute(
            "UPDATE vape SET guild_hits = $1 WHERE guild_id = $2",
            guild_hits,
            ctx.guild.id,
        )
        embed.description = (
            f"{EMOJIS['vape']} {ctx.author.mention} took a hit of the vape! "
            f"The server now has **{guild_hits}** hits."
        )
        await message.edit(embed=embed)

    @vape.command(name="steal", brief="Steal the vape from the current holder")
    @commands.cooldown(1, 20, commands.BucketType.guild)
    async def vape_steal(self, ctx):
        res = await self.bot.db.fetchrow(
            "SELECT holder FROM vape WHERE guild_id = $1", ctx.guild.id
        )

        # If the vape doesn't exist in the server, create a new entry
        if not res:
            await self.bot.db.execute(
                "INSERT INTO vape (holder, guild_id, guild_hits) VALUES ($1, $2, 0)",
                ctx.author.id,
                ctx.guild.id,
            )
            return await ctx.send(
                embed=discord.Embed(
                    description=f"{EMOJIS['vape']} You have claimed the vape, **{ctx.author.mention}**",
                    color=self.bot.color,
                )
            )

        # Handle existing vape holder
        current_holder = ctx.guild.get_member(res["holder"])
        if current_holder == ctx.author:
            return await ctx.send(
                embed=discord.Embed(
                    description=f"{EMOJIS['vape']} You already have the vape, you fiend!",
                    color=self.bot.color,
                )
            )

        await self.bot.db.execute(
            "UPDATE vape SET holder = $1 WHERE guild_id = $2",
            ctx.author.id,
            ctx.guild.id,
        )
        description = (
            f"{EMOJIS['vape']} You have successfully stolen the vape from {current_holder.mention}."
            if current_holder
            else f"{EMOJIS['vape']} You have claimed the vape, **{ctx.author.mention}**"
        )
        await ctx.send(
            embed=discord.Embed(description=description, color=self.bot.color)
        )

    @vape.command(name="flavor", aliases=["taste"])
    async def vape_flavor(self, ctx, flavor: str):

        if flavor.capitalize() not in self.flavors:
            return await ctx.send(
                embed=discord.Embed(
                    description=f"> This is not a valid flavor. Choose from: {', '.join(self.flavors)}",
                    color=self.bot.color,
                )
            )

        # Update user's flavor choice
        await self.bot.db.execute(
            """
            INSERT INTO vape_flavors (flavor, user_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET flavor = $1
            """,
            flavor,
            ctx.author.id,
        )
        await ctx.send(
            embed=discord.Embed(
                title="Flavor Set",
                description=f"> You have set your flavor to **{flavor}**.",
                color=self.bot.color,
            )
        )
    
    @vape.command(name="hits", brief="Show the total number of hits taken by the server")
    async def vape_hits(self, ctx):
        hits = await self.bot.db.fetchval(
            "SELECT guild_hits FROM vape WHERE guild_id = $1", ctx.guild.id
        )
        await ctx.send(
            embed=discord.Embed(
                description=f"> The server has taken **{hits}** hits from the vape.",
                color=self.bot.color,
            )
        )


    @commands.command(name="caption", aliases=["quote"])
    async def caption(
        self, ctx: Context, message: Optional[discord.Message] = None
    ) -> Message:
        return await self.get_caption(ctx, message)






    @commands.command(name="pp", description="See pp size for specified user", aliases=['ppsize'], usage="pp [user]")
    @commands.cooldown(1, 4, commands.BucketType.guild)
    async def pp(self, ctx, *, user: discord.Member = None):
        if user is None:
            user = ctx.author
        size = random.randint(1, 50)
        ppsize = "=" * size
        embed = discord.Embed(
            title=f"{user.display_name}'s pp size",
            description=f"8{ppsize}D",
            colour=self.bot.color,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(help="roast anyone", description="fun")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def roast(self, ctx):
        roast_list = [
            "at least my mom pretends to love me",
            "Bards will chant parables of your legendary stupidity for centuries, You",
            "Don't play hard to get when you are hard to want",
            "Don't you worry your pretty little head about it. The operative word being little. Not pretty.",
            "Get a damn life you uncultured cranberry fucknut.",
            "God wasted a good asshole when he put teeth in your mouth",
            "Goddamn did your parents dodge a bullet when they abandoned you.",
            "I bet your dick is an innie and your belly button an outtie.",
            "I can't even call you Fucking Ugly, because Nature has already beaten me to it.",
            "I cant wait to forget you.",
            "I curse the vagina that farted you out.",
            "I don't have the time, or the crayons to explain this to you.",
            "I FART IN YOUR GENERAL DIRECTION",
            "I fucking hate the way you laugh.",
            "I hope you win the lottery and lose your ticket.",
            "I once smelled a dog fart that had more cunning, personality, and charm than you.",
            "I shouldn't roast you, I can't imagine the pain you go through with that face!",
            "I want to call you a douche, but that would be unfair and unrealistic. Douches are often found near vaginas.",
            "I wonder if you'd be able to speak more clearly if your parents were second cousins instead of first.",
            "I would call you a cunt, but you lack the warmth or the depth.",
            "I would challenge you to a battle of wits, but it seems you come unarmed",
            "I would rather be friends with Ajit Pai than you.",
            "I'd love to stay and chat but I'd rather have type-2 diabetes",
            "I'm just surprised you haven't yet retired from being a butt pirate.",
            "I'm not mad. I'm just... disappointed.",
            "I've never met someone who's at once so thoughtless, selfish, and uncaring of other people's interests, while also having such lame and boring interests of his own. You don't have friends, because you shouldn't.",
            "Im betting your keyboard is filthy as fuck now from all that Cheeto-dust finger typing, you goddamn weaboo shut in. ",
            "If 'unenthusiastic handjob' had a face, your profile picture would be it.",
            "If there was a single intelligent thought in your head it would have died from loneliness.",
            "If you were a potato you'd be a stupid potato.",
            "If you were an inanimate object, you'd be a participation trophy.",
            "If you where any stupider we'd have to water you",
            "If you're dad wasn't so much of a pussy, he'd have come out of the closet before he had you.",
            "It's a joke, not a dick. You don't have to take it so hard.",
            "Jesus Christ it looks like your face was on fire and someone tried to put it out with an ice pick",
            "May the fleas of ten thousand camels live happily upon your buttocks",
            "Maybe if you eat all that makeup you will be beautiful on the inside.",
            "Mr. Rogers would be disappointed in you.",
            "Next time, don't take a laxative before you type because you just took a steaming stinking dump right on the page. Now wipe that shit up and don't fuck it up like your life.",
            "Not even your dog loves you. He's just faking it.",
            "Once upon a time, Santa Clause was asked what he thought of your mom, your sister and your grandma, and thus his catchphrase was born.",
            "People don't even pity you.",
            "People like you are the reason God doesn't talk to us anymore",
            "Take my lowest priority and put yourself beneath it.",
            "The IQ test only goes down to zero but you make a really compelling case for negative numbers",
            "the only thing you're fucking is natural selection",
            "There are two ugly people in this chat, and you're both of them.",
            "There will never be enough middle fingers in this world for You",
            "They don't make a short enough bus in the Continental United States for a person like you.",
            "Those aren't acne scars, those are marks from the hanger.",
            "Twelve must be difficult for you. I dont mean BEING twelve, I mean that being your IQ.",
            "We all dislike you, but not quite enough that we bother to think about you.",
            "Were you born a cunt, or is it something you have to recommit yourself to every morning?",
            "What's the difference between three dicks and a joke? You can't take a joke.",
            "When you die, people will struggle to think of nice things to say about you.",
            "Where'd ya get those pants? The toilet store?",
            "Why do you sound like you suck too many cocks?",
            "Why dont you crawl back to whatever micro-organism cesspool you came from, and try not to breath any of our oxygen on the way there",
            "WHY SHOULD I LISTEN TO YOU ARE SO FAT THAT YOU CAN'T POO OR PEE YOU STINK LYRE YOU HAVE A CRUSH ON POO",
            "You are a pizza burn on the roof of the world's mouth.",
            "You are a stupid.",
            "You are dumber than a block of wood and not nearly as useful",
            "You are like the end piece of bread in a loaf, everyone touches you but no one wants you",
            "You have a face made for radio",
            "You have more dick in your personality than you do in your pants",
            "You have the face of a bulldog licking piss off a stinging nettle.",
            "You know they say 90% of dust is dead human skin? That's what you are to me.",
            "You know, one of the many, many things that confuses me about you is that you remain unmurdered.",
            "You look like your father would be disappointed in you. If he stayed.",
            "You losing your virginity is like a summer squash growing in the middle of winter. Never happening.",
            "You may think people like being around you- but remember this: there is a difference between being liked and being tolerated.",
            "You might want to get a colonoscopy for all that butthurt",
            "You need to go up to your daddy, get on your knees and apologize to each and every brother and sister that didn't make it to your mother's egg before you",
            "You should put a condom on your head, because if you're going to act like a dick you better dress like one too.",
            "You stuck up, half-witted, scruffy looking nerf herder!",
            "You were birthed out your mothers ass because her cunt was too busy.",
            "You're an example of why animals eat their young.",
            "You're impossible to underestimate",
            "You're kinda like Rapunzel except instead of letting down your hair you let down everyone in your life",
            "You're like a penny on the floor of a public restroom - filthy, untouchable and practically worthless.",
            "You're like a square blade, all edge and no point.",
            "You're looking well for a man twice your age! Any word on the aneurism?",
            "You're not pretty enough to be this dumb",
            "You're objectively unattractive.",
            "You're so dense, light bends around you.",
            "You're so salty you would sink in the Dead Sea",
            "You're so stupid you couldn't pour piss out of a boot if the directions were written on the heel",
            "You're such a pussy that fucking you wouldnt be gay.",
            "You're ugly when you cry.",
            "Your birth certificate is an apology letter from the abortion clinic.",
            "Your memes are trash.",
            "Your mother may have told you that you could be anything you wanted, but a douchebag wasn't what she meant.",
            "Your mother was a hamster, and your father reeks of elderberries!",
            "Your penis is smaller than the payment a homeless orphan in Mongolia received for stitching my shoes.",
            "What are serbians? Never heard of then before."
    ]
        
        embed=discord.Embed(color=0x2B2D31, description= f"{random.choice(roast_list)}")
        await ctx.reply(embed=embed, mention_author=False)



    @commands.hybrid_command(help="ask the :8ball: anything", aliases=["8ball"], description="fun", usage="<member>")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def eightball(self, ctx, *, question):
        responses  = ["It is certain.",
                    "It is decidedly so.",
                    "Without a doubt.",
                    "Yes - definitely.",
                    "You may rely on it.",
                    "As I see it, yes.",
                    "Most likely.",
                    "Outlook good.",
                    "Yes.",
                    "Signs point to yes.",
                    "Reply hazy, try again.",
                    "Ask again later.",
                    "Better not tell you now.",
                    "Cannot predict now.",
                    "Concentrate and ask again.",
                    "Don't count on it.",
                    "My reply is no.",
                    "My sources say no.",
                    "Outlook not so good.",
                    "Very doubtful.",
                    "Maybe."]
        embed=discord.Embed(color=0x2B2D31, description= f" :8ball: {random.choice(responses)}")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(
        name="dominant",
        brief="Get the most dominant color in a user's avatar",
        aliases=["dom"],
    )
    async def dominant(self, ctx, user: discord.Member = None):
        user = user or ctx.author
        avatar = user.avatar.with_format("png")
        async with self.bot.session.get(str(avatar)) as resp:
            image = await resp.read()
        result = await get_dominant_color(image)
        dominant_color = result["dominant_color"]
        hex_color = "#{:02x}{:02x}{:02x}".format(*dominant_color)
        embed = discord.Embed(
            color=discord.Color.from_rgb(*dominant_color),
            description=f"{user.mention}'s dominant color is ``{hex_color}``",
        )
        embed.set_thumbnail(url=str(avatar))
        await ctx.send(embed=embed)

    @commands.command(
        name="rotate",
        brief="Rotate an image by a specified angle",
    )
    async def rotate(self, ctx, angle: int, message: Optional[discord.Message] = None):
        if message is None:
            msg = ctx.message.reference
            if msg is None:
                return await ctx.send("No message or reference provided")
            id = msg.message_id
            message = await ctx.fetch_message(id)

        if not message.attachments:
            return await ctx.send("No media found in the message")

        url = message.attachments[0].url
        async with self.bot.session.get(url) as resp:
            image = await resp.read()
        rotated_image_bytes = await rotate_image(image, angle)
        buffer = BytesIO(rotated_image_bytes)
        buffer.seek(0)
        file = discord.File(buffer, filename="rotated.png")
        await ctx.send(file=file)
        buffer.close()


    @commands.command(
        name="compress",
        brief="Compress an image to reduce its size",
    )
    async def compress(self, ctx, message: Optional[discord.Message] = None, quality: int = 10):
        if message is None:
            msg = ctx.message.reference
            if msg is None:
                return await ctx.send("No message or reference provided")
            id = msg.message_id
            message = await ctx.fetch_message(id)

        if not message.attachments:
            return await ctx.send("No media found in the message")

        url = message.attachments[0].url
        async with self.bot.session.get(url) as resp:
            image = await resp.read()

        compressed_image = await compress_image(image)
        buffer = BytesIO(compressed_image)
        buffer.seek(0)
        file = discord.File(buffer, filename="compressed.jpg")
        await ctx.send(file=file)
        buffer.close()

    @commands.command(
        name="quickpoll",
        brief="Create a quick yes/no poll",
        aliases=["qpoll"],
    )
    async def quickpoll(self, ctx, *, question):
        embed = discord.Embed(
            description=question,
            color=self.bot.color,
        )
        embed.set_footer(text=f"Poll created by {ctx.author}")
        message = await ctx.send(embed=embed)
        await message.add_reaction(f"{EMOJIS['UB_Check_Icon']}")
        await message.add_reaction(f"{EMOJIS['UB_X_Icon']}")

    @commands.command(
        name="randomhex",
        brief="Generate a random hex color",
        aliases=["rhex"],
    )
    async def randomhex(self, ctx):
        color = random.randint(0, 0xFFFFFF)
        hex_color = f"#{color:06x}"
        return await ColorInfo().convert(ctx, hex_color)
    
    @commands.command(
        name="rps",
        brief="Play rock, paper, scissors",
    )
    async def rps(self, ctx, choice: str):
        choices = ["rock", "paper", "scissors"]
        if choice not in choices:
            embed = discord.Embed(
                description=f"Invalid choice. Choose from: {', '.join(choices)}",
                color=self.bot.color,
            )
            return await ctx.send(embed=embed)
        
        bot_choice = random.choice(choices)
        if choice == bot_choice:
            embed = discord.Embed(
                description=f"Both players chose ``{choice}``. It's a tie!",
                color=self.bot.color,
            )
            return await ctx.send(embed=embed)
        
        if (choice == "rock" and bot_choice == "scissors") or (
            choice == "paper" and bot_choice == "rock"
        ) or (choice == "scissors" and bot_choice == "paper"):
            embed = discord.Embed(
                description=f"You chose ``{choice}`` and I chose ``{bot_choice}``. **You win!**",
                color=self.bot.color,
            )
            return await ctx.send(embed=embed)
        
        embed = discord.Embed(
            description=f"You chose ``{choice}`` and I chose ``{bot_choice}``. **I win!**",
            color=self.bot.color,
        )
        return await ctx.send(embed=embed)
    
    @commands.command(
        name="choose",
        brief="Choose between multiple options",
        aliases=["pick"],
    )
    async def choose(self, ctx, *, options: commands.clean_content):
        choices = options.split(",")
        choice = random.choice(choices)
        embed = discord.Embed(
            description=f"I choose: **{choice.strip()}**",
            color=self.bot.color,
        )
        await ctx.send(embed=embed)
    
    @commands.command(
        name="wyr",
        brief="Play a game of Would You Rather",
        aliases=["wouldyourather"],
    )
    async def wyr(self, ctx):
        url = "https://would-you-rather.p.rapidapi.com/wyr/random"
        headers = {
            "x-rapidapi-key": "dd42e94a21msh04bda572c6da553p127a95jsnf367d0e280bb",
            "x-rapidapi-host": "would-you-rather.p.rapidapi.com"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    question = data[0].get("question", "No question available.")
                else:
                    question = "Sorry, couldn't fetch a question at the moment."

        embed = discord.Embed(
            description=question,
            color=self.bot.color,
        )
        await ctx.send(embed=embed)

    @commands.command(name="nword", help="Shows how many times you've said the n-word")
    async def nword_count(self, ctx):
        """
        Show how many times the user has said 'nigga'.
        """
        try:
            user_id = ctx.author.id
            result = await self.bot.db.fetchrow(
                "SELECT count FROM offensive WHERE user_id = $1", user_id  # Pass user_id directly, not as a tuple
            )

            if result:
                count = result['count']  # Use the key 'count' to access the result

                # Create an embed with the response
                embed = Embed(
                    description=f"{ctx.author.name} You've said it **{count}** times...",
                    color=self.bot.color
                )

                # Send the embed to the channel
                await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"Error fetching your count: {e}")
            print(f"Error fetching count for {ctx.author.id}: {e}")



    @commands.command(name="nwordlb", help="Shows the top 10 users who said the n-word.")
    async def nword_leaderboard(self, ctx):
        """
        Displays the top 10 users who have said the 'n-word' the most.
        """
        try:
            # Fetch the top 10 users based on the 'nigga' count, descending order
            rows = await self.bot.db.fetch(
                "SELECT user_id, count FROM offensive ORDER BY count DESC LIMIT 10"
            )

            # If no data is available
            if not rows:
                await ctx.send("No data available in the leaderboard.")
                return

            # Create a list to hold user leaderboard entries
            leaderboard_entries = []

            # Loop through the results and get user data from the database
            for row in rows:
                user_id = row['user_id']
                count = row['count']

                # Try to fetch the user from the guild (fall back to user_id if not found)
                user = ctx.guild.get_member(user_id)

                # If user not found in the guild, attempt to fetch globally
                if not user:
                    try:
                        user = await self.bot.fetch_user(user_id)
                    except discord.NotFound:
                        user = None  # If not found globally, set user to None

                # If user exists, mention the user with a clickable link; else fallback to "Unknown User"
                if user:
                    username = f"[{user.name}](https://discord.com/users/{user.id})"  # Username linked to profile
                else:
                    username = "Unknown User"  # Use "Unknown User" if not found

                leaderboard_entries.append(f"**{username}: {count} times**")

            # Split leaderboard entries into pages (10 entries per page)
            page_size = 10
            pages = [leaderboard_entries[i:i + page_size] for i in range(0, len(leaderboard_entries), page_size)]

            # Handle pagination
            for page_num, page in enumerate(pages, 1):
                # Create the embed for the page
                embed = discord.Embed(
                    title="Top 10 idiots",
                    description="\n".join(page),
                    color=self.bot.color
                )
                embed.set_footer(text=f"ong yall racist -nox")
                
                # Send the embed for the current page
                await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @commands.command(
        name="tictactoe",
        brief="Play a game of Tic Tac Toe",
        aliases=["ttt"],
    )
    async def tictactoe(self, ctx, opponent: discord.Member):
        if opponent.bot:
            return await ctx.fail("You can't play against a bot!")
        
        if opponent == ctx.author:
            return await ctx.fail("You can't play against yourself!")
        
        view = TicTacToe(ctx.author, opponent)
        await ctx.send(
            f"Tic Tac Toe: {ctx.author.mention} vs {opponent.mention}",
            view=view
        )



    @commands.command(name="image", aliases=["img"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def image(self, ctx, *, query: str):
        """Search for images using Google's Custom Search JSON API with button-based navigation."""

        # Check if the user is a donator
        try:
            is_donator = await self.bot.db.fetchrow(
                """SELECT * FROM boosters WHERE user_id = $1""", ctx.author.id
            )
        except Exception as e:
            return await ctx.fail(f"An error occurred while checking donator status: {e}")

        # If not a donator, limit access to the image search
        if not is_donator and not ctx.author.id in self.bot.owner_ids:
            return await ctx.fail(
                "You are not boosting [/pomice](https://discord.gg/pomice). Boost this server to use this command."
            )
        try:
            results = await self.bing.image_search(query = query, safe = True if not ctx.channel.is_nsfw() else False, pages = 2)
            embeds = []
            for i, result in enumerate(results.results, start = 1):
                embed = discord.Embed(
                    title = f"Image Results for {query}",
                    color = self.bot.color
                )
                embed.set_image(url = result.image or result.thumbnail)
                embed.set_footer(text = f"Page {i}/{len(results.results)}")
                embeds.append(embed)
            return await ctx.alternative_paginate(embeds)
        except Exception as e:
            if ctx.author.name == "aiohttp":
                raise e
            return await ctx.fail(f"No results found for query `{query[:50]}`")


          
    # @commands.command(name="image")
    # @commands.cooldown(1, 5, commands.BucketType.user)
    async def old_image(self, ctx, *, query: str):
          """Search for images using Google's Custom Search JSON API with button-based navigation."""

          # Check if the user is a donator
          try:
               is_donator = await self.bot.db.fetchrow(
                    """SELECT * FROM boosters WHERE user_id = $1""", ctx.author.id
               )
          except Exception as e:
               return await ctx.fail(f"An error occurred while checking donator status: {e}")

          # If not a donator, limit access to the image search
          if not is_donator:
               return await ctx.fail(
                    "You are not boosting [/pomice](https://discord.gg/pomice). Boost this server to use this command."
               )

          try:
               # Build the Google Custom Search service
               service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)

               # Initialize variables
               embeds = []
               items_collected = 0
               start_index = 1

               # Fetch results in batches (max 10 results per API call)
               while items_collected < 100:
                    result = service.cse().list(
                         q=query,              # Query string
                         cx=SEARCH_ENGINE_ID,  # Custom Search Engine ID
                         searchType="image",   # Search type: Image
                         safe="active",        # SafeSearch filter
                         num=10,               # Number of results to fetch (max 10 per API call)
                         start=start_index     # Start index for results
                    ).execute()

                    # Extract the results
                    items = result.get("items", [])
                    if not items:
                         break  # Stop if no more results

                    # Add the results to the embeds list
                    for index, item in enumerate(items, start=items_collected + 1):
                         image_url = item.get("link")
                         embed = discord.Embed(
                              color=self.bot.color
                         )
                         embed.set_image(url=image_url)
                         embed.set_footer(text="Images provided by Greed")
                         embeds.append(embed)

                    # Update variables for the next batch
                    items_collected += len(items)
                    start_index += 10

                    # Stop if fewer than 10 results are returned (indicating no more results available)
                    if len(items) < 10:
                         break

               # If no embeds were created, notify the user
               if not embeds:
                    return await ctx.fail("No images found for your query.")

               # Adjust page count to match total results
               for idx, embed in enumerate(embeds):
                    embed.description = f"<:Google:1315861928538800189> **Search results for: {query}**\nPage {idx + 1}/{len(embeds)}"

               # Send the first embed with buttons
               view = ImagePaginationView(ctx.author, embeds)
               await ctx.send(embed=embeds[0], view=view)

          except Exception as e:
               await ctx.send(f"An error occurred: {e}")

    @commands.command(name="poll", brief="Create a poll with multiple options")
    async def poll(self, ctx, time: str, *, question: str):
        """Create a poll with multiple options."""
        from humanfriendly import parse_timespan

        t = parse_timespan(time)
        if t is None:
            return await ctx.send("Invalid time format. Example: `1h`, `30m`, `1d`")

        embed = discord.Embed(
            title=f"{ctx.author} asked",
            description=question, 
            color=self.bot.color,
        )
        embed.set_footer(text=f"Poll created by {ctx.author}")
        message = await ctx.send(embed=embed)
        
        # Add reactions
        emojis = ["👍", "👎"]
        await asyncio.gather(*[message.add_reaction(emoji) for emoji in emojis])

        # Track votes
        votes = {}
        def check(reaction, user):
            return user != self.bot.user and reaction.message.id == message.id and user != user.bot

        try:
            while True:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=t, check=check)
                if user.id not in votes:
                    votes[user.id] = reaction.emoji
                else:
                    # Remove subsequent reactions if user already voted
                    await reaction.remove(user)
                
        except asyncio.TimeoutError:
            # Time's up, tally the results
            message = await ctx.channel.fetch_message(message.id)
            if not message:
                return

            final_counts = {emoji: 0 for emoji in emojis}
            for user_id, emoji in votes.items():
                final_counts[emoji] += 1

            embed = discord.Embed(
                title=f"Poll Results: {question}",
                color=self.bot.color,
            )
            for emoji, count in final_counts.items():
                embed.add_field(name=emoji, value=count)
            await message.reply(embed=embed)

class ImagePaginationView(discord.ui.View):
    def __init__(self, user: discord.Member, embeds: list[discord.Embed]):
        super().__init__(timeout=60)
        self.user = user
        self.embeds = embeds
        self.current_page = 0

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handles the Previous button click."""
        if interaction.user != self.user:
            await interaction.response.send_message("You cannot control this interaction.", ephemeral=True)
            return

        self.current_page -= 1
        self.update_buttons()
        embed = self.embeds[self.current_page]
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.success)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handles the Next button click."""
        if interaction.user != self.user:
            await interaction.response.send_message("You cannot control this interaction.", ephemeral=True)
            return

        self.current_page += 1
        self.update_buttons()
        embed = self.embeds[self.current_page]
        await interaction.response.edit_message(embed=embed, view=self)

    def update_buttons(self):
        """Enable or disable buttons based on the current page."""
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.embeds) - 1



async def setup(bot):
    await bot.add_cog(Fun(bot))
