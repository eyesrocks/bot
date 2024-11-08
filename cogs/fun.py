from discord import Message
from types import resolve_bases
from discord.ext import commands
from discord.ext.commands import Context, BadArgument
from discord import Embed, TextChannel
import random
import discord
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import textwrap

# from greed.tool import aliases

class BlackTea:
    def __init__(self, bot):
        self.bot = bot
        self.color = 0xA5D287
        self.emoji = "<a:boba_tea_green_gif:1302250923858591767>"
        self.MatchStart = []
        self.lifes = {}
        self.players = {}


    def get_string(self):
        words = self.get_words()
        word = random.choice([l for l in words if len(l) > 3])
        return word[:3]

    async def send_embed(self, channel: TextChannel, content: str):
        return await channel.send(embed=Embed(color=self.color, description=content))

    def match_started(self, guild_id: int):
        if guild_id in self.MatchStart:
            raise BadArgument("A Black Tea match is **already** in progress")
        else:
            self.MatchStart.append(guild_id)

    async def lost_a_life(self, member: int, reason: str, channel: TextChannel):
        lifes = self.lifes[f"{channel.guild.id}"].get(f"{member}")
        self.lifes[f"{channel.guild.id}"][f"{member}"] = lifes + 1

        if reason == "timeout":
            await self.send_embed(
                channel,
                f"⏰ <@{member}> time is up! **{3-int(self.lifes[f'{channel.guild.id}'][f'{member}'])}** lifes left..",
            )

        elif reason == "wrong":
            await self.send_embed(
                channel,
                f"💥 <@{member}> wrong answer! **{3-int(self.lifes[f'{channel.guild.id}'][f'{member}'])}** lifes left..",
            )

        if self.lifes[f"{channel.guild.id}"][f"{member}"] == 3:
            await self.send_embed(channel, f"☠️ <@{member}> you're eliminated")
            del self.lifes[f"{channel.guild.id}"][f"{member}"]
            self.players[f"{channel.guild.id}"].remove(member)

    def get_words(self):
        data = open("./data/words.txt", encoding="utf-8")
        return [d for d in data.read().splitlines()]

    def clear_all(self):
        self.MatchStart = []
        self.lifes = {}
        self.players = {}

    def remove_stuff(self, guild_id: int):
        del self.players[f"{guild_id}"]
        del self.lifes[f"{guild_id}"]
        self.MatchStart.remove(guild_id)


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.blacktea = BlackTea(self.bot)

    async def get_caption(self, ctx: Context, message: Optional[discord.Message] = None):
        if message is None:
            msg = ctx.message.reference
            if msg is None:
                return await ctx.warn(f"no **message** or **reference** provided")
            id = msg.message_id
            message = await ctx.fetch_message(id)

        image = BytesIO(await message.author.display_avatar.read())
        image.seek(0)
        if message.content.replace("\n", "").isascii():
            para = textwrap.wrap(message.clean_content, width=26)
        else:
            para = textwrap.wrap(message.clean_content, width=13)

        async def do_caption(para, image, message):
            icon = Image.open(image)
            haikei = Image.open("quote/grad.jpeg")
            black = Image.open("quote/black.jpeg")
            w, h = (680, 370)
            haikei = haikei.resize((w, h))
            black = black.resize((w, h))
            icon = icon.resize((h, h))

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
                if message.content.replace("\n", "").isascii():
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
                        (0, 0), line.ljust(int(len(line) / 2 + 5), "　"), font=fnt
                    )
                    draw.text(
                        (11 * (w - w3) / 13 + 10, current_h + h2),
                        line.ljust(int(len(line) / 2 + 5), "　"),
                        font=fnt,
                        fill="#FFF",
                    )

                current_h += h3 + pad

            dr = ImageDraw.Draw(sa)
            font = ImageFont.truetype("quote/Arial.ttf", 15)
            _, _, authorw, _ = dr.textbbox(
                (0, 0), f"-{str(message.author)}", font=font
            )

            output = BytesIO()
            dr.text(
                (480 - int(authorw / 2), current_h + h2 + 10),
                f"-{str(message.author)}",
                font=font,
                fill="#FFF",
            )
            sa.save(output, format="JPEG")
            output.seek(0)
            return output

        loop = asyncio.get_event_loop()
        output = await loop.create_task(do_caption(para, image, message))
        file = discord.File(fp=output, filename="quote.png")
        return await ctx.send(file=file)


    @commands.command(name="uwuify", brief="uwuify a message", aliases=["uwu"])
    async def uwuify(self, ctx: Context, *, message: str):
        try:
            text = await self.bot.rival.uwuify(message)
            return await ctx.send(text)
        except Exception:  # noqa: E722
            return await ctx.fail("couldn't uwuify that message")


    @commands.command(name="blacktea")
    async def blacktea(self, ctx: Context):
        """
        play blacktea with the server members
        """

        self.blacktea.match_started(ctx.guild.id)
        coffee_emoji = "☕️"
        other_emoji = "<a:boba_tea_green_gif:1302250923858591767>"

        # Create a list with 10 coffee emojis
        emojis = [coffee_emoji] * 10

        # Initialize index to track which emoji to change next
        index_to_change = 9

        # Wait for 1 second before printing and changing again
        embed = Embed(
            color=self.blacktea.color,
            title="BlackTea Matchmaking",
        )
        mes = await ctx.send(embed=embed, content="".join(emojis))
        await mes.add_reaction(self.blacktea.emoji)
        for i in range(11):
            # Print the current list of emojis
            new_content = "".join(emojis)

            # Change the emoji at the current index
            emojis[index_to_change] = other_emoji

            # Move to the next index (circular fashion)
            index_to_change = (index_to_change - 1) % len(emojis)
            await mes.edit(content=new_content)
            await asyncio.sleep(1)

        try:
            newmes = await ctx.channel.fetch_message(mes.id)
        except Exception:
            try:
                self.blacktea.MatchStart.remove(ctx.guild.id)
            except Exception:
                pass
            return await ctx.send("The blacktea message was deleted")

        users = [
            u.id async for u in newmes.reactions[0].users() if u.id != self.bot.user.id
        ]

        if len(users) < 2:
            try:
                self.blacktea.MatchStart.remove(ctx.guild.id)
            except Exception:
                pass
            return await ctx.send("not enough players to start the blacktea match...")

        words = self.blacktea.get_words()
        self.blacktea.players.update({f"{ctx.guild.id}": users})
        self.blacktea.lifes.update(
            {f"{ctx.guild.id}": {f"{user}": 0 for user in users}}
        )

        while len(self.blacktea.players[f"{ctx.guild.id}"]) > 1:
            for user in users:
                rand = self.blacktea.get_string()
                await self.blacktea.send_embed(
                    ctx.channel,
                    f"{self.blacktea.emoji} <@{user}>: Say a word containing **{rand}** in **10 seconds**",
                )
                try:
                    message = await self.bot.wait_for(
                        "message",
                        check=lambda m: m.channel.id == ctx.channel.id
                        and m.author.id == user,
                        timeout=10,
                    )
                    if (
                        rand in message.content.lower()
                        and message.content.lower() in words
                    ):
                        await self.blacktea.send_embed(
                            ctx.channel,
                            f"<@{user}> Correct answer!",
                        )
                    else:
                        await self.blacktea.lost_a_life(user, "wrong", ctx.channel)
                except asyncio.TimeoutError:
                    await self.blacktea.lost_a_life(user, "timeout", ctx.channel)

        await self.blacktea.send_embed(
            ctx.channel,
            f"👑 <@{self.blacktea.players[f'{ctx.guild.id}'][0]}> Won the game!!",
        )
        member = self.blacktea.players[str(ctx.guild.id)][0]

        self.blacktea.remove_stuff(ctx.guild.id)
        self.blacktea


    @commands.command()
    async def spark(self, ctx):
        user_id = ctx.author.id
        row = await self.bot.db.fetchrow("SELECT sparked, last_sparked FROM blunt_hits WHERE user_id = $1", user_id)

        if row:
            sparked, last_sparked = row
            if not sparked or (datetime.now() - last_sparked).total_seconds() > 300:
                await self.bot.db.execute("""
                    INSERT INTO blunt_hits (user_id, sparked, last_sparked)
                    VALUES ($1, TRUE, $2)
                    ON CONFLICT (user_id)
                    DO UPDATE SET sparked = TRUE, last_sparked = $2
                """, user_id, datetime.now())
                embed = discord.Embed(description=f"<:arolighter:1303239578009866252> {ctx.author.mention} sparked the blunt!", color=self.bot.color)
                await ctx.send(embed=embed)
            else:
                remaining_time = timedelta(seconds=300) - (datetime.now() - last_sparked)
                remaining_minutes, remaining_seconds = divmod(int(remaining_time.total_seconds()), 60)
                embed = discord.Embed(description=f"{ctx.author.mention}, you need to wait {remaining_minutes} minutes and {remaining_seconds} seconds before sparking another blunt!", color=self.bot.color)
                await ctx.send(embed=embed)
        else:
            await self.bot.db.execute("""
                INSERT INTO blunt_hits (user_id, sparked, last_sparked)
                VALUES ($1, TRUE, $2)
            """, user_id, datetime.now())
            embed = discord.Embed(description=f"<:arolighter:1303239578009866252> {ctx.author.mention} sparked their first blunt!", color=self.bot.color)
            await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def smoke(self, ctx):
        user_id = ctx.author.id
        row = await self.bot.db.fetchrow("SELECT sparked, taps FROM blunt_hits WHERE user_id = $1", user_id)

        if row and row[0]:  # If sparked is True
            taps = row[1]
            if taps < 100:
                await self.bot.db.execute("UPDATE blunt_hits SET taps = taps + 1 WHERE user_id = $1", user_id)
                embed = discord.Embed(description=f"<a:d_smoke:1303264450572324894>  {ctx.author.mention} took a hit from the blunt!", color=self.bot.color)
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(description=f"{ctx.author.mention}, your blunt has gone out!", color=self.bot.color)
                await ctx.send(embed=embed)
        else:
            embed = discord.Embed(description="You need to spark the blunt first!", color=self.bot.color)
            await ctx.send(embed=embed)

    @commands.command()
    async def taps(self, ctx):
        user_id = ctx.author.id
        taps = await self.bot.db.fetchval("SELECT taps FROM blunt_hits WHERE user_id = $1", user_id) or 0

        embed = discord.Embed(description=f"{ctx.author.mention} has taken {taps} hits from the blunt.", color=self.bot.color)
        await ctx.send(embed=embed)

    @commands.command(help="shows how gay you are", description="fun", usage="<member>")
    async def howgay(self, ctx, user: discord.Member=None):

        if user==None:
            embed=discord.Embed(color=self.bot.color, title="gay r8", description= f"{ctx.author.mention} is `{random.randrange(201)}%` gay")
            await ctx.reply(embed=embed, mention_author=False)
        else:
            embed=discord.Embed(color=self.bot.color, title="gay r8", description= f"{user.mention} is `{random.randrange(201)}%` gay")


    @commands.command(help="shows your iq", description="fun", usage="<member>")
    async def iq(self, ctx, user: discord.Member=None):

        if user==None:
            embed=discord.Embed(color=self.bot.color, title="iq test", description= f"{ctx.author.mention} has `{random.randrange(201)}` iq :brain:")
            await ctx.reply(embed=embed, mention_author=False)
        else:
            embed=discord.Embed(color=self.bot.color, title="iq test", description= f"{user.mention} has `{random.randrange(201)}` iq :brain:")
            await ctx.reply(embed=embed, mention_author=False)

    @commands.command(help="shows how many bitches you have", description="fun", usage="<member>")
    async def bitches(self, ctx, user: discord.Member=None):
        user = user or ctx.author
        await ctx.reply(embed=discord.Embed(color=self.bot.color, description= f"{user.mention} has `{random.randrange(51)}` bitches"), mention_author=False)


    @commands.group(
          name="vape",
          brief="Hit the vape",
          invoke_without_command=True
     )
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def vape(self, ctx):
          has_vape = await self.bot.db.fetchrow(
               "SELECT holder FROM vape WHERE guild_id = $1", ctx.guild.id
          )
          
          # If no vape is found in the server
          if not has_vape:
               embed = discord.Embed(
                    description="> The vape doesn't exist in this server. Someone needs to claim it first!",
                    color=self.bot.color
               )
               return await ctx.send(embed=embed)

          if has_vape['holder'] is None:
               embed = discord.Embed(
                    description="> No one has the vape yet. Steal it using the **`vape steal`** command.",
                    color=self.bot.color
               )
               return await ctx.send(embed=embed)

          elif has_vape['holder'] != ctx.author.id:
               member = await ctx.guild.fetch_member(has_vape['holder'])
               if member:
                    embed = discord.Embed(
                         description=f"> You don't have the vape! Steal it from **{member.display_name}**.",
                         color=self.bot.color
                    )
               else:
                    embed = discord.Embed(
                         description="> The vape holder is no longer in this server. Someone else can claim it!",
                         color=self.bot.color
                    )
               return await ctx.send(embed=embed)

          # Initial embed saying "hitting vape"
          embed = discord.Embed(
               description=f"<:hits:1303239575250014241> {ctx.author.mention} is about to take a hit of the vape...",
               color=self.bot.color
          )
          message = await ctx.send(embed=embed)

          # Add a small delay (2.3 seconds) before updating the embed
          await asyncio.sleep(2.3)

          # Record the hit and update the hit counter
          await self.bot.db.execute(
               "UPDATE vape SET guild_hits = guild_hits + 1 WHERE guild_id = $1", ctx.guild.id
          )
          res = await self.bot.db.fetchrow(
               "SELECT * FROM vape WHERE guild_id = $1", ctx.guild.id
          )

          # Update the embed with the actual hit description and server stats
          embed.description = f"<:hits:1303239575250014241> {ctx.author.mention} took a hit of the vape! The server now has **{res['guild_hits']}** hits."
          await message.edit(embed=embed)

    @vape.command(
          name="steal",
          brief="Steal the vape from the current holder"
     )
    @commands.cooldown(1, 20, commands.BucketType.guild)
    async def vape_steal(self, ctx):
          res = await self.bot.db.fetchrow("SELECT * FROM vape WHERE guild_id = $1", ctx.guild.id)
          
          if res:
               result = await ctx.guild.fetch_member(res['holder'])

               if result is None:
                    # Steal the vape if the holder is not in the server
                    await self.bot.db.execute(
                         "UPDATE vape SET holder = $1 WHERE guild_id = $2",
                         ctx.author.id, ctx.guild.id
                    )
                    embed = discord.Embed(
                         description=f"<:hits:1303239575250014241> You have claimed the vape, **{ctx.author.mention}**",
                         color=self.bot.color
                    )
                    return await ctx.send(embed=embed)

               elif result == ctx.author:
                    # User already has the vape
                    embed = discord.Embed(
                         description="<:hits:1303239575250014241> You already have the vape you fiend",
                         color=self.bot.color
                    )
                    return await ctx.send(embed=embed)

               else:
                    # Steal the vape from the current holder
                    await self.bot.db.execute(
                         "UPDATE vape SET holder = $1 WHERE guild_id = $2",
                         ctx.author.id, ctx.guild.id
                    )
                    embed = discord.Embed(
                         description=f"<:hits:1303239575250014241> You have successfully stolen the vape from {result.mention}.",
                         color=self.bot.color
                    )
                    return await ctx.send(embed=embed)
          else:
               # No vape data exists, so claim it
               await self.bot.db.execute(
                    "INSERT INTO vape (holder, guild_id) VALUES ($1, $2)",
                    ctx.author.id, ctx.guild.id
               )
               embed = discord.Embed(
                    description=f"<:hits:1303239575250014241> You have claimed the vape, **{ctx.author.mention}**",
                    color=self.bot.color
               )
               return await ctx.send(embed=embed)

    @vape.command(
          name="flavor",
          aliases=["taste"]
     )
    async def vape_flavor(self, ctx, flavor: str):
          flavors = [
               "Strawberry", "Mango", "Blueberry", "Watermelon", "Grape",
               "Pineapple", "Vanilla", "Chocolate", "Caramel", "Mint",
               "Coffee", "Cinnamon", "Bubblegum", "Peach", "Apple",
               "Lemon", "Cherry", "Raspberry"
          ]

          if flavor.lower() not in [f.lower() for f in flavors]:
               embed = discord.Embed(

                    description=f"> This is not a valid flavor. Choose from: {', '.join(flavors)}",
                    color=self.bot.color
               )
               return await ctx.send(embed=embed)

          # Save the user's selected flavor
          await self.bot.db.execute(
               """
               INSERT INTO vape_flavors (flavor, user_id)
               VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE SET flavor = $1
               """,
               flavor, ctx.author.id
          )

          embed = discord.Embed(
               title="Flavor Set",
               description=f"> You have set your flavor to **{flavor}**.",
               color=self.bot.color
          )
          await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Fun(bot))
