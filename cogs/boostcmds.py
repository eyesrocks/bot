import discord
from discord.ext import commands


def check():
    async def predicate(ctx):
        guild = ctx.bot.get_guild(1301617147964821524)
        if guild:
            role = guild.premium_subscriber_role
            if not role:
                return False
            return role in ctx.author.roles
        return False
    return commands.check(predicate)     

class Booster(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.command()
    async def claim(self, ctx):
        """Allows a user with the booster role to claim access."""
        guild = self.bot.get_guild(1301617147964821524)
        if guild:
            role = guild.premium_subscriber_role
            if not role:
                return
            
            if role not in ctx.author.roles:
                return await ctx.fail(
                    "You are not boosting the [support server](https://discord.com/invite/pomice). Boost the server to claim your permissions."
                )
            
            else:
                await self.bot.db.execute("INSERT INTO boosters (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", ctx.author.id)
                await ctx.success("Access granted, You can now use the booster only commands!")
        else:
            return


    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @check()
    async def emojify(self, ctx, *, text: str = None):
        """Converts text into Discord emojis for boosters only."""
        if not text:
            return await ctx.fail("Please provide some text to emojify!")
            
        if len(text) > 200:
            return await ctx.fail("Text too long! Please keep it under 200 characters.")

        char_map = {
            '0': ':zero:', '1': ':one:', '2': ':two:', '3': ':three:', 
            '4': ':four:', '5': ':five:', '6': ':six:', '7': ':seven:', 
            '8': ':eight:', '9': ':nine:',
            '!': ':exclamation:', '?': ':question:', 
            '+': ':heavy_plus_sign:', '-': ':heavy_minus_sign:',
            '×': ':x:', '*': ':asterisk:', '$': ':heavy_dollar_sign:'
        }

        try:
            # Process text with list comprehension for better performance
            emojified = ' '.join(
                char_map.get(char) if char in char_map
                else f':regional_indicator_{char.lower()}:' if char.isalpha()
                else '   ' if char.isspace()
                else char
                for char in text
            )

            if len(emojified) > 2000:
                return await ctx.fail("The emojified result would be too long for Discord!")

            await ctx.reply(emojified)

        except Exception as e:
            await ctx.fail(f"An error occurred: {str(e)}")



            
async def setup(bot):
    """Setup function to load the cog."""
    await bot.add_cog(Booster(bot))
