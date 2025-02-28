import discord
from discord.ext import commands
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence
import os
import json
from loguru import logger

arial_bold_font_path = "/root/greed/data/fonts/arial_bold.ttf"

class Card(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_tracking = {}
        self.user_preferences = {}  # In-memory dictionary to store user preferences
        self.bot.loop.create_task(self.load_decos())  # Load decorations from the folder
        self.decos = {}  # Holds decoration names

    async def load_decos(self):
        """Loads all PNG and GIF decorations from the deco folder into a JSON file and handles APNG renaming."""
        deco_folder = '/root/greed/data/decos'
        deco_data = {}

        for file_name in os.listdir(deco_folder):
            if file_name.endswith('.png'):
                file_path = os.path.join(deco_folder, file_name)

                try:
                    with Image.open(file_path) as img:
                        # Check if the image is an APNG
                        if 'apng' in img.format.lower():
                            # Rename the file to have the .apng extension if it is an APNG
                            new_file_name = file_name.replace('.png', '.apng')
                            new_file_path = os.path.join(deco_folder, new_file_name)

                            # Rename the file
                            os.rename(file_path, new_file_path)
                            # Update the decoration data with the new file name
                            deco_data[file_name.replace('.png', '')] = new_file_name
                        else:
                            # If it's not an APNG, keep the original PNG format
                            deco_data[file_name.replace('.png', '')] = file_name
                except Exception as e:
                    print(f"Error processing {file_name}: {e}")
                    continue  # Skip problematic files

        # Save decorations data into a JSON file
        with open('decos.json', 'w') as f:
            json.dump(deco_data, f)

        self.decos = deco_data  # Load into the class's in-memory dictionary

    @commands.Cog.listener()
    async def on_message(self, message):
        """Tracks message count and updates rank per server."""
        try:
            if any([
                message.author.bot,
                not message.guild, 
                not message.author,
            ]):
                return

            guild_id = str(message.guild.id)
            user_id = str(message.author.id)

            if guild_id not in self.message_tracking:
                self.message_tracking[guild_id] = {}

            if user_id not in self.message_tracking[guild_id]:
                self.message_tracking[guild_id][user_id] = {
                    "message_count": 0,
                    "rank": 1
                }

            # Update message count
            try:
                self.message_tracking[guild_id][user_id]["message_count"] += 1
            except Exception as e:
                logger.error(f"Error updating message count: {e}")
                self.message_tracking[guild_id][user_id] = {
                    "message_count": 1,
                    "rank": 1
                }

            # Update ranks
            try:
                # Sort users by message count
                sorted_users = sorted(
                    self.message_tracking[guild_id].items(),
                    key=lambda item: item[1].get("message_count", 0),  # Safely get message count
                    reverse=True
                )

                # Update ranks
                for rank, (uid, data) in enumerate(sorted_users, start=1):
                    if uid in self.message_tracking[guild_id]:  # Check if user still exists
                        self.message_tracking[guild_id][uid]["rank"] = rank

            except Exception as e:
                logger.error(f"Error updating ranks: {e}")
                # If ranking fails, at least the message count was updated

        except Exception as e:
            logger.error(f"Error in message tracking: {e}")
            # Don't raise the exception to prevent breaking the bot
            return

    @commands.group(name="card", invoke_without_command=True)
    async def card_group(self, ctx):
        """Main command group for user card features."""
        return await ctx.send_help(ctx.command.qualified_name)


    @commands.command(name="usercard")
    @commands.is_owner()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def user_card(self, ctx, member: discord.Member = None):
        """Generates and displays a user card with avatar, status, and banner."""
        member = member or ctx.author  # Default to command sender if no member is mentioned

        # Fetch user preferences from the in-memory dictionary
        user_data = self.user_preferences.get(member.id, {})

        # Default preferences if no record exists
        background_color = user_data.get('background_color', "#2f3136")
        avatar_deco_name = user_data.get('avatar_deco', "")
        banner_image = user_data.get('banner', None)
        font_name = user_data.get('font', "arial.ttf")  # Default font
        custom_status = user_data.get('status', member.status.name.capitalize())  # Default to current status

        # Fetch user avatar
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        avatar_response = await self.fetch_image(avatar_url)
        avatar_img = Image.open(BytesIO(avatar_response)).convert("RGBA")
        deco_size = 135
        border3_size = 60  # Fixed border size
        avatar_size = 105
        avatar_img = avatar_img.resize((avatar_size, avatar_size))
        avatar_img = self.make_avatar_circular(avatar_img)

        # Create a circular border around the avatar
        border_total_size3 = avatar_size + 17 * border3_size
        avatar_with_border = Image.new("RGBA", (border_total_size3, border_total_size3), (0, 0, 0, 0))
        draw = ImageDraw.Draw(avatar_with_border)
        draw.ellipse((0, 0, border_total_size3, border_total_size3), fill="black")  # Black border
        avatar_with_border.paste(avatar_img, (border3_size, border3_size), avatar_img)

        # Apply avatar decoration if specified and place it over the avatar
        deco_path = None
        if avatar_deco_name:
            # Check for both PNG and APNG files
            deco_path_png = f"/root/greed/data/decos/{avatar_deco_name}.png"
            deco_path_apng = f"/root/greed/data/decos/{avatar_deco_name}.apng"

            # First, check for APNG file
            if os.path.exists(deco_path_apng):
                deco_path = deco_path_apng
            elif os.path.exists(deco_path_png):
                deco_path = deco_path_png

        # Create card canvas with rounded corners
        width, height = 600, 300
        total_avatar_size = avatar_size + 60 * 2
        # Handle banner
        # Handle banner
        banner_url = user_data.get('banner_url')
        if banner_url:
            banner_img = await self.fetch_image(banner_url)
            banner_img = Image.open(BytesIO(banner_img)).convert("RGBA")
            banner_img = banner_img.resize((600, 300))  # Resize banner to fit the card
        else:
            banner_img = Image.new("RGBA", (600, 300), background_color)  # Default background

        # Create card canvas with rounded corners
        card = Image.new("RGBA", (600, 300), (0, 0, 0, 0))  # Transparent background for the rounded corners

        # Create a new background layer for the card
        card_bg = Image.new("RGBA", (600, 300), background_color)
        card.paste(card_bg, (0, 0))  # This applies the background color over the canvas

        # Draw the rounded rectangle with a black border
        draw = ImageDraw.Draw(card)
        border_radius = 20  # Rounded corner radius
        border_thickness = 8  # Thickness of the black border

        # Create a new background layer for the card
        card_bg = Image.new("RGBA", (width, height), background_color)
        card.paste(card_bg, (0, 0))


        # Draw the rounded rectangle with a black border around the card
        draw.rounded_rectangle([border_thickness, border_thickness, width-border_thickness, height-border_thickness], radius=border_radius, fill=background_color)
        card.paste(banner_img, (0, 0), banner_img)
        draw.rounded_rectangle([border_thickness-1, border_thickness-1, width-border_thickness+1, height-border_thickness+1], radius=border_radius, outline="black", width=border_thickness)



        # Add padding around the avatar to prevent clipping
        avatar_border_padding = 20  # Add padding to the avatar
        total_avatar_size = avatar_size + avatar_border_padding * 2  # Total size with padding

        avatar_with_padding = Image.new("RGBA", (total_avatar_size, total_avatar_size), (0, 0, 0, 0))  # Transparent padded image
        avatar_with_padding.paste(avatar_img, (avatar_border_padding, avatar_border_padding))  # Paste the avatar into the center of the padded area

        # Paste avatar with border and padding onto the card
        card.paste(avatar_with_padding, (30, (height - total_avatar_size) // 2), avatar_with_padding)

        # If deco_path is set, apply decoration over the avatar
        if deco_path:
            with Image.open(deco_path) as deco_img:
                deco_img = deco_img.convert("RGBA")
                deco_img = deco_img.resize((deco_size, deco_size))  # Resize decoration to match the avatar size
                x, y = (border3_size + avatar_border_padding - 43, border3_size + avatar_border_padding - 0)  # Position of decoration
                card.paste(deco_img, (x, y), deco_img)  # Apply decoration over the avatar

        # Set the path to the font file
        font_path = f"/root/greed/data/fonts/{font_name}.ttf"  # Path to the custom font

        # Try loading the custom font
        try:
            font = ImageFont.truetype(font_path, 40)
        except IOError:
            # If the custom font is not found, fall back to the default 'arial.ttf'
            font_path = "/root/greed/data/fonts/arial.ttf"
            font = ImageFont.truetype(font_path, 40)

        # Draw username and status
        username_text = f"{member.name}"
        draw.text((180, 110), username_text, font=font, fill=(255, 255, 255))

        # Draw user status
        status_words = custom_status.split()[:4]  # Limit to 4 words
        status_text = " ".join(status_words)
        status_colors = {
            "online": (67, 181, 129),
            "idle": (250, 168, 26),
            "dnd": (240, 71, 71),
            "offline": (116, 127, 141)
        }
        status_color = status_colors.get(status_text.lower(), (255, 255, 255))
        draw.text((180, 160), f"{status_text}", font=font, fill=status_color)


        # Message count and global rank
        guild_id = str(ctx.guild.id)  # Get the guild ID as a string for uniqueness
        message_count = self.message_tracking.get(guild_id, {}).get(str(member.id), {}).get("message_count", 0)
        server_rank = self.message_tracking.get(guild_id, {}).get(str(member.id), {}).get("rank", 1)

        # Create smaller rounded boxes for message count and global rank, side by side
        box_width = 120  # Smaller width
        box_height = 40  # Smaller height
        box_padding = 8

        # Dark grey color for the box
        box_color = (44, 47, 51)

        # Message count box
        draw.rounded_rectangle([180, 220, 180 + box_width, 220 + box_height], radius=10, fill=box_color)
        draw.text((180 + box_padding, 220 + box_padding), f"msgs: {message_count}", font=ImageFont.truetype(arial_bold_font_path, 16), fill="white")

        # Global rank box (next to message count box)
        draw.rounded_rectangle([180 + box_width + 10, 220, 180 + 2 * box_width + 10, 220 + box_height], radius=10, fill=box_color)
        draw.text((180 + box_width + 10 + box_padding, 220 + box_padding), f"rank: {server_rank}", font=ImageFont.truetype(arial_bold_font_path, 16), fill="white")


        # Save image to a buffer
        buffer = BytesIO()
        card.save(buffer, format="PNG")
        buffer.seek(0)

        # Send image
        file = discord.File(buffer, filename="usercard.png")
        await ctx.send(file=file)

        
#    @card_group.command(name="status")
#    async def set_status(self, ctx, *, custom_text: str):
#        """Set a custom status text."""
#        # Limit custom text to 4 words
#        custom_status = " ".join(custom_text.split()[:4])
#
#        # Update the user's custom status in the preferences
#        if ctx.author.id not in self.user_preferences:
#            self.user_preferences[ctx.author.id] = {}
#
#        self.user_preferences[ctx.author.id]['status'] = custom_status
#        await ctx.success(f"Your custom status has been updated to: `{custom_status}`.")

#    @card_group.command(name="banner")
#    async def card_set_banner(self, ctx, url: str = None):
#        """Set a custom banner for the user card."""
#        # Allow setting the banner from an attachment or a URL
#        if url:
#            # Validate if it's a URL or attachment
#            if url.startswith("http"):
#                self.user_preferences[ctx.author.id] = self.user_preferences.get(ctx.author.id, {})
#                self.user_preferences[ctx.author.id]['banner_url'] = url
#                await ctx.success(f"Your banner has been updated to: {url}")
#            else:
#                await ctx.fail("Please provide a valid image URL.")
#        else:
#            if len(ctx.message.attachments) > 0:
#                # Get the first attachment's URL
#                url = ctx.message.attachments[0].url
#                self.user_preferences[ctx.author.id] = self.user_preferences.get(ctx.author.id, {})
#                self.user_preferences[ctx.author.id]['banner_url'] = url
#                await ctx.success(f"Your banner has been updated with your attachment.")
#            else:
#                await ctx.fail("You need to provide a valid image URL or an attachment.")

    @card_group.command(name="font")
    async def set_font(self, ctx, font_name: str):
        """Set a custom font for the user's name in the user card."""
        # Check if the font file exists
        font_path = f"/root/greed/data/fonts/{font_name}.ttf"  # Modify with your actual font path
        if not os.path.exists(font_path):
            return await ctx.fail(f"The font `{font_name}` does not exist. Please choose a valid font.")

        # Update the user's font preference
        if ctx.author.id not in self.user_preferences:
            self.user_preferences[ctx.author.id] = {}

        self.user_preferences[ctx.author.id]['font'] = font_name
        await ctx.success(f"Your font has been updated to `{font_name}`.")
        
    @card_group.command(name="decos")
    async def list_decos(self, ctx):
        """Lists all available avatar decorations in a paginated format."""
        if not self.decos:
            return await ctx.send("No decorations are available.")

        deco_names = list(self.decos.keys())
        pages = [deco_names[i:i + 5] for i in range(0, len(deco_names), 5)]  # Split into chunks of 5

        embeds = []
        for index, page in enumerate(pages, start=1):
            embed = discord.Embed(title="Available Decorations", color=self.bot.color)
            embed.description = "\n".join(f"- `{name}`" for name in page)
            embed.set_footer(text=f"Page {index}/{len(pages)}")
            embeds.append(embed)

        await ctx.paginate(embeds)  # Uses built-in pagination

    @card_group.command(name="color")
    async def set_bg_color(self, ctx, color: str):
        """Allows users to customize the background color of their user card."""
        # Validate hex color
        if not color.startswith("#") or len(color) != 7:
            return await ctx.fail("Please provide a valid hex color code (e.g., #2f3136).")

        # Update the user's background color in the in-memory dictionary
        if ctx.author.id not in self.user_preferences:
            self.user_preferences[ctx.author.id] = {}
        
        self.user_preferences[ctx.author.id]['background_color'] = color
        await ctx.success(f"Your background color has been updated to `{color}`.")




    @card_group.command(name="deco")
    async def set_avatar_deco(self, ctx, deco_name: str):
        """Allows users to set an avatar decoration for their user card."""
        # Check if the decoration exists in the loaded decos data
        result = await self.bot.db.fetchrow(
            """SELECT * FROM boosters WHERE user_id = $1""", ctx.author.id
        )
        if not result:
            await ctx.fail(f"You are not boosting [/greedbot](https://discord.gg/greedbot), boost the server to use this command")
            return
        

        if deco_name not in self.decos:
            return await ctx.fail(f"The decoration `{deco_name}` does not exist. Available decos: {', '.join(self.decos.keys())}.")

        # Update the user's avatar decoration in the in-memory dictionary
        if ctx.author.id not in self.user_preferences:
            self.user_preferences[ctx.author.id] = {}
        
        self.user_preferences[ctx.author.id]['avatar_deco'] = deco_name
        await ctx.success(f"Your avatar decoration has been updated to `{deco_name}`.")

    async def fetch_image(self, url: str):
        """Helper method to fetch an image from a URL."""
        async with self.bot.session.get(url) as response:
            return await response.read()

    def make_avatar_circular(self, avatar_img: Image):
        """Converts the avatar image into a circular shape."""
        mask = Image.new("L", avatar_img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, avatar_img.size[0], avatar_img.size[1]), fill=255)
        avatar_img.putalpha(mask)
        return avatar_img


# Cog setup
async def setup(bot):
    await bot.add_cog(Card(bot))
