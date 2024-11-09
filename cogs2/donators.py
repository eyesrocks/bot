import discord
from discord import Message
from discord.ext import commands
import sqlite3
import logging
import aiohttp
import os
from typing import Optional
from uuid import uuid4
from tool.worker import offload
from voice import Whisper as VoiceWhisper
# Set up logging
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("error.log"), logging.StreamHandler()]
)

class Donators(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = '/root/greed/premium.sql'  # Path to your SQLite database
        self.transcriptions_dir = '/root/greed/data/transcriptions'

        # Ensure the transcription directory exists
        if not os.path.exists(self.transcriptions_dir):
            os.makedirs(self.transcriptions_dir)

        # Ensure the database table is created when the cog is initialized
        self._initialize_db()

    def _connect_db(self):
        """Helper function to connect to the SQLite database."""
        return sqlite3.connect(self.db)

    def _initialize_db(self):
        """Initialize the database schema (create tables if not exists)."""
        conn = self._connect_db()
        cursor = conn.cursor()

        # Create a table for whitelisted users (donators) if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS whitelisted_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT NOT NULL
        );
        """)

        # Create the table for auto_transcribe if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS auto_transcribe (
            guild_id INTEGER PRIMARY KEY,
            transcribe_enabled BOOLEAN NOT NULL DEFAULT 1
        );
        """)
        
        conn.commit()
        conn.close()

    async def save_file(self, content: str, file_name: str):
        """Save the transcription content as a text file."""
        file_path = os.path.join(self.transcriptions_dir, file_name)
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
            return file_path  # Return the file path where it was saved
        except Exception as e:
            logging.error(f"Error saving transcription file: {e}")
            return None

    async def do_transcribe(self, filepath: str):
        """Call the transcription service."""
        return await self.do_whisper(filepath)

    @offload
    def do_whisper(self, filepath: str, segments):
        """Handle transcription using Whisper model."""
        whisper = VoiceWhisper()
        import faster_whisper, ctranslate2
        from faster_whisper import WhisperModel
        import os
        result = "".join(r.text for r in segments)
        try:
            os.remove(filepath)
        except Exception:
            pass
        whisper.model.unload()
        return result

    def get_filetype(self, url: str) -> str:
        return url.split('/')[-1].split('.')[1].split('?')[0]

    async def download_file(self, url: str) -> str:
        """Download the file from the URL."""
        file_type = self.get_filetype(url)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.read()
        file_name = f"{uuid4()}.{file_type}"
        content = data.decode('utf-8')
        return await self.save_file(content, file_name)

    async def make_transcription(self, message: discord.Message):
        """Transcribe voice messages."""
        if len(message.attachments) > 0:
                if attachment.content_type == 'audio/ogg':
                    filepath = await self.download_file(attachment.url)
                    return await self.do_transcribe(filepath)
                    return await self.do_transcribe(filepath)

    def is_donator(self, ctx: commands.Context):
        """Check if the user is a donator."""
        conn = self._connect_db()
        cursor = conn.cursor()

        # Check if the user is in the whitelisted_users table (donators)
        cursor.execute("SELECT user_id FROM whitelisted_users WHERE user_id = ?", (ctx.author.id,))
        result = cursor.fetchone()  # Use fetchone() for a single result
        conn.close()
        
        if result:
            logging.debug(f"User {ctx.author.name} is a donator.")
            return True
        else:
            logging.debug(f"User {ctx.author.name} is NOT a donator.")
            return False

    @commands.command(name='donators')
    async def donators(self, ctx):
        """Command to show all donators."""
        conn = self._connect_db()
        cursor = conn.cursor()

        try:
            # Query all whitelisted users (donators)
            cursor.execute("SELECT user_id, username FROM whitelisted_users")
            rows = cursor.fetchall()

            if rows:
                donators_text = ""
                for user_row in rows:
                    user_id, username = user_row
                    user = self.bot.get_user(user_id)  # Fetch the user object by ID
                    user_id, _ = user_row
                    if user:
                        donators_text += f"{user.mention}\n"  # Format as "username#discriminator"
                    else:
                        donators_text += f"User with ID {user_id} not found\n"  # In case the user is not cached
                
                # If there is a long list of donators, you can break it up into multiple embeds.
                await self.send_white_embed(ctx, "Donators List", f"Here is the list of all donators:\n{donators_text}")
            else:
                await self.send_white_embed(ctx, "No Donators", "There are no donators at the moment.")
        except Exception as e:
            logging.error(f"Error in donators command: {e}")
            await self.send_white_embed(ctx, "Error", f"An error occurred while fetching donators: {str(e)}")
        finally:
            conn.close()

    @commands.command(name='dtest')
    async def donator_test(self, ctx):
        """Donator-only command for testing."""
        if not self.is_donator(ctx):
            await self.send_white_embed(ctx, "Access Denied", "You must be a donator to use this command.")
            return

        # Command logic for donators
        await self.send_white_embed(ctx, "Donator Test", "Congratulations, you are a donator! This command is restricted to donators only.")

    @commands.Cog.listener("on_message")
    async def on_voice_message(self, message: discord.Message):
        """Triggered when a message is received."""
        if not message.guild:
            return
        if message.author.bot:
            return

        # Check if auto-transcription is enabled for this server
        conn = self._connect_db()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM auto_transcribe WHERE guild_id = ?", (message.guild.id,))
        auto_transcribe = cursor.fetchone()

        if not auto_transcribe:
            conn.close()
            return
        
        text = await self.make_transcription(message)
        if text:
            embed = discord.Embed(description=text, color=0xffffff).set_author(
                name=message.author.display_name,
                icon_url=message.author.display_avatar.url,
            )
            return await message.reply(embed=embed)
        
        conn.close()

    @commands.command(
        name="transcribe",
        brief="Return the text from a voice message",
        help="Usage: ,transcribe [audio_reply]",
    )
    async def transcribe(self, ctx: commands.Context, message: Optional[Message] = None):
        """Command to transcribe voice messages."""
        
        # **Check if the user is a donator** before proceeding
        if not self.is_donator(ctx):
            return await ctx.send("You must be a donator to use this command.")
        
        if not message:
            if not ctx.message.reference:
                messages = [
                    message
                    async for message in ctx.channel.history(limit=50)
                    if len(message.attachments) > 0
                    and message.attachments[0].is_voice_message()
                ]

                if len(messages) == 0:
                    return await ctx.send("Please reply to a message or provide a message to transcribe.")
                else:
                    message = messages[0]

                    msg = await ctx.send(
                        embed=discord.Embed(
                            color=0xffffff,
                            description=f"<a:loading:1302351366584270899> **Transcribing this message...**",
                        )
                    )
                    text = await self.make_transcription(message)

            else:
                message = await ctx.channel.fetch_message(ctx.message.reference.message_id)

                msg = await ctx.send(
                    embed=discord.Embed(
                        color=0xffffff,
                        description=f"<a:loading:1302351366584270899> **Transcribing this message...**",
                    )
                )

                text = await self.make_transcription(message)

        else:
            text = await self.make_transcription(message)

        if text is None:
            return await ctx.send(f"**Failed to transcribe** [**this message**]({message.jump_url})")

        # Save the transcription as a file and send the file back
        file_path = await self.save_file(text, f"{message.id}_transcription.txt")

        if file_path:
            # Send the transcription file back to the user
            await msg.edit(
                embed=discord.Embed(description=text, color=0xffffff).set_author(
                    name=message.author.display_name,
                    icon_url=message.author.display_avatar.url,
                )
            )
            await ctx.send(file=discord.File(file_path))  # Send the file

        else:
            # If saving the file failed
            await ctx.send("An error occurred while saving the transcription file.")

# Setup the cog
async def setup(bot):
    await bot.add_cog(Donators(bot))
