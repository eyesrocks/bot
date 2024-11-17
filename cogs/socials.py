from tool.pinterest import Pinterest  # type: ignore
from discord.ext import commands
from discord.utils import format_dt
import discord
import io
from discord.ext.commands import Context
from aiohttp import ClientSession as Session
from tool.pinpostmodels import Model  # type: ignore
from tuuid import tuuid
import requests
import json




class Socials(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pinterest = Pinterest()


    @commands.command(name="roblox", aliases=["rblx"], brief="Get a Roblox user's profile")
    async def roblox(self, ctx: Context, username: str):
        try:
            profile = await self.bot.rival.roblox_profile(username)
            embed = discord.Embed(
                title=f"{profile.display_name} (@{profile.username})",
                description=profile.description or "No description",
                url=profile.url,
                color=ctx.author.color
            )
            embed.set_thumbnail(url=profile.avatar_url)
            
            stats = profile.statistics
            if stats:
                stats_text = f"Friends: {stats.friends:,}\nFollowers: {stats.followers:,}\nFollowing: {stats.following:,}"
                embed.add_field(name="Statistics", value=stats_text, inline=False)
            else:
                embed.add_field(name="Statistics", value="No statistics available", inline=False)
                        
            embed.set_footer(text=f"{profile.id} | created {format_dt(profile.created_at)}", icon_url=profile.avatar_url)
            
            await ctx.reply(embed=embed)
        except Exception as e:
            await ctx.send(f"Failed to fetch Roblox profile: {str(e)}")



async def setup(bot):
    await bot.add_cog(Socials(bot))
