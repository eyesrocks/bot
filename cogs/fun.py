from discord import Message
from discord.ext import commands
from discord.ext.commands import Context, BadArgument
from discord import Embed, TextChannel
import random
import discord
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
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
        word = random.choice([l for l in words if len(l) > 3])  # noqa: E741
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

        def do_caption(para, image, message):
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
            _, _, authorw, _ = dr.textbbox((0, 0), f"-{str(message.author)}", font=font)

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

        output = await asyncio.to_thread(do_caption, para, image, message)
        file = discord.File(fp=output, filename="quote.png")
        return await ctx.send(file=file)

    @commands.command(name="uwuify", brief="uwuify a message", aliases=["uwu"])
    async def uwuify(self, ctx: Context, *, message: str):
        try:
            text = await self.bot.rival.uwuify(message)
            return await ctx.send(text)
        except Exception:  # noqa: E722
            return await ctx.fail("couldn't uwuify that message")

    @commands.group(name="blacktea", invoke_without_command=True)
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
            self.blacktea.MatchStart.remove(ctx.guild.id)
            return await ctx.send("The blacktea message was deleted")

        users = [
            u.id async for u in newmes.reactions[0].users() if u.id != self.bot.user.id and not u.bot
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
                    while True:
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
                            break
                except asyncio.TimeoutError:
                    await self.blacktea.lost_a_life(user, "timeout", ctx.channel)
                    break

        await self.blacktea.send_embed(
            ctx.channel,
            f"👑 <@{self.blacktea.players[f'{ctx.guild.id}'][0]}> Won the game!!",
        )
        self.blacktea.players[str(ctx.guild.id)][0]

        self.blacktea.remove_stuff(ctx.guild.id)


    @blacktea.command(name="end")
    async def blacktea_end(self, ctx):
        try:
            self.blacktea.remove_stuff(ctx.guild.id)
            await ctx.success("Blacktea match ended")
        except Exception:
            await ctx.fail("No blacktea match is in progress")

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
                    description=f"<:arolighter:1303239578009866252> {ctx.author.mention} sparked the blunt!",
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
                description=f"<:arolighter:1303239578009866252> {ctx.author.mention} sparked their first blunt!",
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
                    description=f"<a:d_smoke:1303264450572324894>  {ctx.author.mention} took a hit from the blunt!",
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
            description=f"<:vape:1306875712065503262> {ctx.author.mention} is about to take a hit of the vape...",
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
            f"<:vape:1306875712065503262> {ctx.author.mention} took a hit of the vape! "
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
                    description=f"<:vape:1306875712065503262> You have claimed the vape, **{ctx.author.mention}**",
                    color=self.bot.color,
                )
            )

        # Handle existing vape holder
        current_holder = ctx.guild.get_member(res["holder"])
        if current_holder == ctx.author:
            return await ctx.send(
                embed=discord.Embed(
                    description="<:vape:1306875712065503262> You already have the vape, you fiend!",
                    color=self.bot.color,
                )
            )

        await self.bot.db.execute(
            "UPDATE vape SET holder = $1 WHERE guild_id = $2",
            ctx.author.id,
            ctx.guild.id,
        )
        description = (
            f"<:vape:1306875712065503262> You have successfully stolen the vape from {current_holder.mention}."
            if current_holder
            else f"<:vape:1306875712065503262> You have claimed the vape, **{ctx.author.mention}**"
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


    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def fuck(self, ctx, member: discord.Member = None):
        if member == None:
            member = ctx.author
            return await ctx.reply(f"mention someone to fuck them loser")


        await ctx.reply(f"**{ctx.author.name}** fucks **{member.name}** freaky mf...")



    @commands.command(name = "pp", description = "See pp size for specified user",aliases=['ppsize'], usage = "pp [user]")
    @commands.cooldown(1, 4, commands.BucketType.guild)
    async def pp(self, ctx, *, user: discord.Member = None):
        if user is None:
            user = ctx.author
            size = random.randint(1, 50)
            ppsize = ""
            for _i in range(size):
                ppsize += "="
                embed = discord.Embed(
                    title=f"{user}'s pp size",
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
        colors = Image.open(BytesIO(image)).convert("RGB").getcolors(maxcolors=1000000)
        # Filter out grayscale colors
        colorful_colors = [color for color in colors if len(set(color[1])) > 1]
        dominant_color = max(colorful_colors, key=lambda item: item[0])[1]
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
        img = Image.open(BytesIO(image)).rotate(angle, expand=True)
        output = BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        file = discord.File(output, filename="rotated.png")
        await ctx.send(file=file)
        output.close()

    @commands.command(
        name="compress",
        brief="Compress an image to reduce its size",
    )
    async def compress(self, ctx, message: Optional[discord.Message] = None):
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
        img = Image.open(BytesIO(image))
        output = BytesIO()
        img.save(output, format="JPEG", quality=10, optimize=True)
        output.seek(0)
        file = discord.File(output, filename="compressed.jpg")
        await ctx.send(file=file)
        output.close()

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
        await message.add_reaction("<:UB_Check_Icon:1306875712782864445>")
        await message.add_reaction("<:UB_X_Icon:1306875714426900531>")






async def setup(bot):
    await bot.add_cog(Fun(bot))
