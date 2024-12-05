import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt
from io import BytesIO

class VoiceTrack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.create_table()

        self.bot.db.execute("""CREATE TABLE IF NOT EXISTS voicetime_overall (
                user_id BIGINT NOT NULL,
                vc1 DECIMAL DEFAULT 0.0,
                vc2 DECIMAL DEFAULT 0.0,
                vc3 DECIMAL DEFAULT 0.0,
                vc4 DECIMAL DEFAULT 0.0,
                vc5 DECIMAL DEFAULT 0.0,
                PRIMARY KEY (user_id)
            );
        """)

    async def update_voicetime(self, user_id, vc_index, minutes):
        """Update the voice time for a specific VC."""
        column = f"vc{vc_index}"
        await self.bot.db.execute(f"""
            INSERT INTO voicetime_overall (user_id, {column})
            VALUES (%s, %s)
            ON CONFLICT(user_id) DO UPDATE SET {column} = {column} + %s;
        """, (user_id, minutes, minutes))

    @commands.command()
    async def voicetrack(self, ctx, member: discord.Member = None):
        """Generates a visual representation of voice time."""
        member = member or ctx.author

        # Fetch voice time data
        data = await self.bot.db.fetchrow("SELECT * FROM voicetime_overall WHERE user_id = %s", (member.id,))

        if not data:
            await ctx.send(f"No data found for {member.mention}.")
            return

        # Extract data for the chart
        vcs = data[1:]  # Skip user_id
        vc_names = [f"VC {i+1}" for i in range(len(vcs))]
        total_minutes = sum(vcs)

        if total_minutes == 0:
            await ctx.send(f"No voice activity recorded for {member.mention}.")
            return

        # Generate grayscale pie chart
        plt.figure(figsize=(8, 8))
        colors = [f"#{i:02x}{i:02x}{i:02x}" for i in range(50, 250, 50)]
        plt.pie(vcs, labels=vc_names, autopct="%.1f%%", startangle=140, colors=colors)
        plt.title(f"{member.name}'s Voice Time Distribution")
        
        # Save pie chart to a buffer
        pie_buffer = BytesIO()
        plt.savefig(pie_buffer, format="PNG")
        pie_buffer.seek(0)
        plt.close()

        # Load profile picture
        avatar_url = member.avatar.url
        avatar_data = BytesIO(await avatar_url.read())
        avatar_img = Image.open(avatar_data).convert("RGBA")

        # Load the pie chart and paste the avatar in the center
        pie_img = Image.open(pie_buffer).convert("RGBA")
        pie_size = pie_img.size
        avatar_img = avatar_img.resize((pie_size[0] // 3, pie_size[1] // 3))
        pie_img.paste(avatar_img, ((pie_size[0] - avatar_img.size[0]) // 2, (pie_size[1] - avatar_img.size[1]) // 2), avatar_img)

        # Add total time text
        draw = ImageDraw.Draw(pie_img)
        font = ImageFont.truetype("arial.ttf", 40)
        draw.text((20, 20), f"Total Time: {total_minutes} mins", fill="black", font=font)

        # Save final image to a buffer
        final_buffer = BytesIO()
        pie_img.save(final_buffer, format="PNG")
        final_buffer.seek(0)

        # Send the image
        await ctx.send(file=discord.File(final_buffer, "voicetrack.png"))

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(VoiceTrack(bot))
