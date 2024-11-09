import discord
from discord.ext import commands
import sqlite3
import logging
from discord import Embed

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

        # Ensure the database table is created when the cog is initialized
        self._initialize_db()

    def _connect_db(self):
        """Helper function to connect to the SQLite database."""
        return sqlite3.connect(self.db)

    def _initialize_db(self):
        """Initialize the database schema (create tables if not exists)."""
        conn = self._connect_db()
        cursor = conn.cursor()

        # Create a table for whitelisted users if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS whitelisted_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT NOT NULL
        );
        """)
        
        conn.commit()
        conn.close()





    async def send_white_embed(self, ctx, title: str, description: str):
        """Helper function to send an embed with white color."""
        embed = Embed(title=title, description=description, color=discord.Color.from_rgb(255, 255, 255))
        await ctx.send(embed=embed)

    def is_donator(self, ctx):
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

# Setup the cog
async def setup(bot):
    await bot.add_cog(Donators(bot))
