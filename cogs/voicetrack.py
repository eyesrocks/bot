import discord
from discord.ext import commands
from datetime import datetime

class VoiceTrack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_voice_states = {}  # To track user voice channel join times
        bot.loop.create_task(self.create_table())

    async def create_table(self):
        """Create the database table for tracking voice time."""
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS voicetime_overall (
                user_id BIGINT NOT NULL,
                vc1 DECIMAL DEFAULT 0.0,
                vc2 DECIMAL DEFAULT 0.0,
                vc3 DECIMAL DEFAULT 0.0,
                vc4 DECIMAL DEFAULT 0.0,
                vc5 DECIMAL DEFAULT 0.0,
                PRIMARY KEY (user_id)
            );
        """)

    async def update_voicetime(self, user_id, vc_id, minutes):
        """Update the voice time for a specific VC."""
        column = f"vc{vc_id}"
        query = f"""
            INSERT INTO voicetime_overall (user_id, {column})
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE
            SET {column} = voicetime_overall.{column} + $2;
        """
        await self.bot.db.execute(query, user_id, minutes)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Tracks users joining and leaving voice channels."""
        # Ignore bot users
        if member.bot:
            return

        user_id = member.id
        now = datetime.utcnow()

        # User joins a voice channel
        if before.channel is None and after.channel is not None:
            self.user_voice_states[user_id] = {
                "channel_id": after.channel.id,
                "join_time": now
            }
            print(f"{member.name} joined {after.channel.name} at {now}.")

        # User leaves a voice channel
        elif before.channel is not None and after.channel is None:
            if user_id in self.user_voice_states:
                data = self.user_voice_states.pop(user_id)
                join_time = data["join_time"]
                vc_id = self.map_channel_to_vc(data["channel_id"])

                # Calculate time spent in the channel
                time_spent = (now - join_time).total_seconds() / 60  # Convert to minutes
                print(f"{member.name} left {before.channel.name} after {time_spent:.2f} minutes.")

                # Update the database
                await self.update_voicetime(user_id, vc_id, time_spent)

        # User switches voice channels
        elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            if user_id in self.user_voice_states:
                data = self.user_voice_states.pop(user_id)
                join_time = data["join_time"]
                vc_id = self.map_channel_to_vc(data["channel_id"])

                # Calculate time spent in the old channel
                time_spent = (now - join_time).total_seconds() / 60  # Convert to minutes
                print(f"{member.name} switched from {before.channel.name} to {after.channel.name} after {time_spent:.2f} minutes.")

                # Update the database for the old channel
                await self.update_voicetime(user_id, vc_id, time_spent)

            # Log the new channel
            self.user_voice_states[user_id] = {
                "channel_id": after.channel.id,
                "join_time": now
            }


# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(VoiceTrack(bot))
