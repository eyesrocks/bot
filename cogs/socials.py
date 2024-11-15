from tool.pinterest import Pinterest  # type: ignore
from discord.ext import commands
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



    @commands.command(
        name="roblox",
        description="Shows information on a roblox user",
        usage=";roblox <username>",
    )
    async def roblox(self, ctx, username):
        try:
            users_json = requests.get(
                f"https://www.roblox.com/search/users/results?keyword={username}&maxRows=1&startIndex=0"
            )
            users = json.loads(users_json.text)

            if "UserSearchResults" not in users or not users["UserSearchResults"]:
                await ctx.send("User not found.")
                return

            user_id = users["UserSearchResults"][0]["UserId"]

            profile_json = requests.get(f"https://users.roblox.com/v1/users/{user_id}")
            profile = json.loads(profile_json.text)

            if (
                "displayName" not in profile
                or "created" not in profile
                or "description" not in profile
            ):
                await ctx.send("An error occurred while fetching user data.")
                return

            display_name = profile["displayName"]
            created_date = profile["created"]
            description = profile["description"]

            thumbnail_json = requests.get(
                f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=100x100&format=Png&isCircular=false"
            )
            thumbnail = json.loads(thumbnail_json.text)

            if "data" not in thumbnail or not thumbnail["data"]:
                await ctx.send("An error occurred while fetching user data.")
                return

            thumbnail_url = thumbnail["data"][0]["imageUrl"]

            followers_json = requests.get(
                f"https://friends.roblox.com/v1/users/{user_id}/followers/count"
            )
            followers_count = json.loads(followers_json.text)["count"]


            embed = discord.Embed(
                title=f"{username}",
                url=f"https://www.roblox.com/users/{user_id}/profile",
            )

            embed.add_field(name="ID", value=f"{user_id}", inline=True)
            embed.add_field(name="Display Name", value=f"{display_name}", inline=True)
            embed.add_field(
                name="Created", value=f"``{created_date[:10]}``", inline=True
            )  # Truncate the date to just show the month, day, and year in bold.
            embed.add_field(name="Description", value=f"{description}", inline=True)
            embed.add_field(name="Followers", value=f"{followers_count}", inline=True)
            embed.set_thumbnail(url=f"{thumbnail_url}")

            # Set the footer to the user ID
            embed.set_footer(text=f"User ID: {user_id}")

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"An error occurred while fetching user data: {e}")
            




async def setup(bot):
    await bot.add_cog(Socials(bot))
