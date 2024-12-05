import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt
from io import BytesIO

class VoiceTrack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def ensure_table(self):
        """Ensure the table has the correct schema."""
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS voicetime_overall (
                user_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                total_minutes DECIMAL DEFAULT 0.0,
                PRIMARY KEY (user_id, channel_id)
            );
        """)
        # Adding channel_id column if it doesn't exist
        await self.bot.db.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'voicetime_overall' AND column_name = 'channel_id') THEN
                    ALTER TABLE voicetime_overall ADD COLUMN channel_id BIGINT;
                END IF;
            END;
            $$;
        """)

    async def update_voicetime(self, user_id, channel_id, minutes):
        """Update the voice time for a specific user and channel."""
        query = """
            INSERT INTO voicetime_overall (user_id, channel_id, total_minutes)
            VALUES ($1, $2, $3)
            ON CONFLICT(user_id, channel_id) 
            DO UPDATE SET total_minutes = total_minutes + $3;
        """
        await self.bot.db.execute(query, user_id, channel_id, minutes)

    def calculate_time_spent(self, before, after):
        """Calculate time spent in the voice channel."""
        if before.channel is None or after.channel is None:
            return 0.0

        # Calculate the time spent in the channel, in minutes
        time_spent = (after.self_deaf - before.self_deaf) / 60.0
        return time_spent

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Listener to track voice state updates and store voice time"""
        # Only track if the member joins or leaves a channel
        if before.channel != after.channel:
            time_spent = self.calculate_time_spent(before, after)

            if after.channel:  # If the user joined a channel
                await self.update_voicetime(member.id, after.channel.id, time_spent)
            if before.channel:  # If the user left a channel
                await self.update_voicetime(member.id, before.channel.id, time_spent)

    @commands.command()
    async def voicetrack(self, ctx, member: discord.Member = None):
        """Generates a visual representation of voice time."""
        member = member or ctx.author

        # Fetch voice time data
        data = await self.bot.db.fetchrow("SELECT * FROM voicetime_overall WHERE user_id = $1", (member.id,))

        if not data:
            await ctx.send(f"No data found for {member.mention}.")
            return

        # Extract data for the chart
        vcs = data[1:]  # Skip user_id and channel_id
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
