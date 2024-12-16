from discord import Embed, Message, Reaction, Member, TextChannel, VoiceChannel, Permissions
from discord.ext import commands


class deathshit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.word_counts = {}

    async def cog_load(self):
        await super().cog_load()
        await self.bot.db.execute("CREATE TABLE IF NOT EXISTS channelban (guild_id BIGINT PRIMARY KEY, role_id BIGINT)")
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS vcbans (
                guild_id BIGINT,
                user_id BIGINT,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS auto_reactions (
                guild_id BIGINT,
                user_id BIGINT,
                emojis TEXT[],
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS word_counts (
                guild_id BIGINT,
                user_id BIGINT,
                word TEXT,
                count INTEGER,
                PRIMARY KEY (guild_id, user_id, word)
            )
        """)
        
        # Load existing word counts into memory
        records = await self.bot.db.fetch("SELECT guild_id, user_id, word, count FROM word_counts")
        for record in records:
            guild_counts = self.word_counts.setdefault(record['guild_id'], {})
            user_counts = guild_counts.setdefault(record['user_id'], {})
            user_counts[record['word']] = record['count']


    @commands.command(name='setupchannelban', aliases=['scb', 'setupcb'])
    @commands.has_permissions(administrator=True)
    async def setup_channelban(self, ctx):
        try:
            guild = ctx.guild
            ban_role = await guild.create_role(name="Banned", permissions=Permissions(send_messages=False))
            
            for channel in guild.channels:
                await channel.set_permissions(ban_role, send_messages=False)
            
            await self.bot.db.execute(
                """INSERT INTO channelban (guild_id, role_id) 
                   VALUES ($1, $2) 
                   ON CONFLICT (guild_id) DO UPDATE SET role_id = $2""", 
                guild.id, ban_role.id
            )
            
            await ctx.send("Channel ban role created and permissions set for all channels.")
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")


    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            return
        
        if message.guild is None:
            return
        
        ban_role_id = await self.bot.db.fetchval("SELECT role_id FROM channelban WHERE guild_id = $1", message.guild.id)        
        if ban_role_id is None:
            return
        
        ban_role = message.guild.get_role(ban_role_id)
        
        if ban_role is None:
            return
        
        if ban_role in message.author.roles:
            await message.delete()


    @commands.command(name="channelban", aliases=['cban', 'shutthefuckup', 'shutupnia', 'stfu', 'stfubitch', 'silencenia', 'silencebitch'])
    @commands.has_permissions(administrator=True)
    async def channelban(self, ctx, member: Member):
        try:
            if member.top_role >= ctx.author.top_role:
                return await ctx.send("You cannot ban members with equal or higher roles.")
                
            ban_role_id = await self.bot.db.fetchval("SELECT role_id FROM channelban WHERE guild_id = $1", ctx.guild.id)
            ban_role = ctx.guild.get_role(ban_role_id)
            
            if ban_role is None:
                return await ctx.send("Channel ban role not setup.")
            
            await member.add_roles(ban_role)
            await ctx.send(f"{member.mention} has been channel banned.")
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    @commands.command(name="channelunban", aliases=['cub', 'cunban'])
    @commands.has_permissions(administrator=True)
    async def channelunban(self, ctx, member: Member):
        ban_role_id = await self.bot.db.fetchval("SELECT role_id FROM channelban WHERE guild_id = $1", ctx.guild.id)
        ban_role = ctx.guild.get_role(ban_role_id)
        
        if ban_role is None:
            return await ctx.send("Channel ban role not setup.")
        
        await member.remove_roles(ban_role)
        await ctx.send(f"{member.mention} has been channel unbanned.")


    @commands.command(name="channelbanlist", aliases=['cbl'])
    @commands.has_permissions(administrator=True)
    async def channelbanlist(self, ctx):
        ban_role_id = await self.bot.db.fetchval("SELECT role_id FROM channelban WHERE guild_id = $1", ctx.guild.id)
        ban_role = ctx.guild.get_role(ban_role_id)
        
        if ban_role is None:
            return await ctx.send("Channel ban role not setup.")
        
        members = [member.mention for member in ctx.guild.members if ban_role in member.roles]
        
        if not members:
            return await ctx.send("No members are channel banned.")
        
        embeds = []
        for i in range(0, len(members), 20):
            embed = Embed(title="Channel Banned Members", description="\n".join(members[i:i+20]))
            embeds.append(embed)
        
        await ctx.paginate(embeds)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: Member, before, after):
        if before.channel == after.channel:
            return
        
        if after.channel is None:
            return
            
        is_banned = await self.bot.db.fetchval("SELECT user_id FROM vcbans WHERE guild_id = $1 AND user_id = $2", member.guild.id, member.id)
        if is_banned:
            await member.move_to(None)

    @commands.command(name="vcban", aliases=['vban'])
    @commands.has_permissions(administrator=True)
    async def vcban(self, ctx, member: Member):
        try:

            guild = ctx.guild
            for channel in guild.voice_channels:
                await channel.set_permissions(member, connect=False)
            
            if member.voice:
                await member.move_to(None)

            await self.bot.db.execute(
                """INSERT INTO vcbans (guild_id, user_id) 
                   VALUES ($1, $2) 
                   ON CONFLICT DO NOTHING""", 
                guild.id, member.id
            )
            await ctx.send(f"{member.mention} has been voice channel banned.")
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    @commands.command(name="unvcban", aliases=['uvban'])
    @commands.has_permissions(administrator=True)
    async def unvcban(self, ctx, member: Member):
        guild = ctx.guild
        for channel in guild.voice_channels:
            await channel.set_permissions(member, overwrite=None)
        
        await self.bot.db.execute("DELETE FROM vcbans WHERE guild_id = $1 AND user_id = $2", guild.id, member.id)
        await ctx.send(f"{member.mention} has been voice channel unbanned.")

    @commands.command(name="banlist", aliases=['blist'])
    @commands.has_permissions(administrator=True)
    async def banlist(self, ctx):
        guild = ctx.guild
        ban_role_id = await self.bot.db.fetchval("SELECT role_id FROM channelban WHERE guild_id = $1", guild.id)
        ban_role = guild.get_role(ban_role_id)
        
        if ban_role is None:
            return await ctx.send("Channel ban role not setup.")
        
        channel_banned_members = [member for member in guild.members if ban_role in member.roles]
        vc_banned_user_ids = await self.bot.db.fetch("SELECT user_id FROM vcbans WHERE guild_id = $1", guild.id)
        vc_banned_members = [guild.get_member(record['user_id']) for record in vc_banned_user_ids]
        
        all_banned_members = set(channel_banned_members + vc_banned_members)
        
        if not all_banned_members:
            return await ctx.send("No members are banned from channels or voice channels.")
        
        embeds = []
        for i in range(0, len(all_banned_members), 20):
            embed = Embed(title="Banned Members", description="\n".join(member.mention for member in all_banned_members[i:i+20]))
            embeds.append(embed)
        
        await ctx.paginate(embeds)

    @commands.command(name="selfreact")
    @commands.has_permissions(administrator=True)
    async def react_setup(self, ctx, member: Member = None, *emojis):
        member = member or ctx.author
        if not emojis:
            return await ctx.send("Please provide at least one emoji.")
            
        # Get existing emojis
        existing_emojis = await self.bot.db.fetchval(
            "SELECT emojis FROM auto_reactions WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        ) or []
        
        # Calculate total emojis
        total_emojis = len(existing_emojis) + len(emojis)
        if total_emojis > 3:
            return await ctx.send(f"Maximum 3 emojis allowed. Currently using {len(existing_emojis)} emojis.")
            
        try:
            # Combine existing and new emojis
            combined_emojis = existing_emojis + list(emojis)
            
            await self.bot.db.execute(
                """INSERT INTO auto_reactions (guild_id, user_id, emojis)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET emojis = $3""",
                ctx.guild.id, member.id, combined_emojis
            )
            
            await ctx.send(f"Now auto-reacting to {member.mention}'s messages with {' '.join(combined_emojis)}")
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    @commands.command(name="reactend")
    @commands.has_permissions(administrator=True)
    async def react_end(self, ctx, member: Member):
        await self.bot.db.execute(
            "DELETE FROM auto_reactions WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )
        await ctx.send(f"Stopped auto-reacting to {member.mention}'s messages.")

    @commands.Cog.listener("on_message")
    async def react_check(self, message: Message):
        if message.author.bot or not message.guild:
            return
            
        reactions = await self.bot.db.fetchval(
            "SELECT emojis FROM auto_reactions WHERE guild_id = $1 AND user_id = $2",
            message.guild.id, message.author.id
        )
        
        if reactions:
            for emoji in reactions:
                try:
                    await message.add_reaction(emoji)
                except:
                    continue


    @commands.command(name="ipcheck")
    async def ip_check(self, ctx, ip: str):
        try:
            # Check IP info
            async with self.bot.session.get(f'http://ip-api.com/json/{ip}') as response:
                data = await response.json()
                
            if data['status'] == 'fail':
                return await ctx.send("Invalid IP address provided.")

            # Check if VPN using proxycheck.io API
            async with self.bot.session.get(f'https://proxycheck.io/v2/{ip}?vpn=1') as proxy_response:
                proxy_data = await proxy_response.json()
                is_vpn = proxy_data.get(ip, {}).get('proxy', 'no') == 'yes'

            embed = Embed(title=f"IP Information for {ip}")
            fields = {
                "Country": data.get('country', 'N/A'),
                "Region": data.get('regionName', 'N/A'),
                "City": data.get('city', 'N/A'),
                "ZIP": data.get('zip', 'N/A'),
                "ISP": data.get('isp', 'N/A'),
                "Organization": data.get('org', 'N/A'),
                "Timezone": data.get('timezone', 'N/A'),
                "Coordinates": f"{data.get('lat', 'N/A')}, {data.get('lon', 'N/A')}",
                "VPN/Proxy": "Yes" if is_vpn else "No"
            }
            
            for name, value in fields.items():
                embed.add_field(name=name, value=value, inline=True)
                
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")



    @commands.command(name="count")
    async def count_words(self, ctx, *items):
        if not items:
            return await ctx.send("Please provide words or emojis to count.")
        
        guild_counts = self.word_counts.setdefault(ctx.guild.id, {})
        user_counts = guild_counts.setdefault(ctx.author.id, {})
        
        for item in items:
            user_counts[item] = 0
            await self.bot.db.execute(
                """INSERT INTO word_counts (guild_id, user_id, word, count) 
                    VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING""",
                ctx.guild.id, ctx.author.id, item, 0
            )
        
        await ctx.send(f"Now counting: {', '.join(items)}")

    @commands.command(name="countoff")
    async def count_off(self, ctx):
        if ctx.guild.id in self.word_counts and ctx.author.id in self.word_counts[ctx.guild.id]:
            del self.word_counts[ctx.guild.id][ctx.author.id]
            await self.bot.db.execute(
                "DELETE FROM word_counts WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id, ctx.author.id
            )
            await ctx.send("Counting turned off.")
        else:
            await ctx.send("No active counting for you.")

    @commands.command(name="countlist")
    async def count_list(self, ctx):
        counts = await self.bot.db.fetch(
            "SELECT word, count FROM word_counts WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id
        )
        
        if not counts:
            return await ctx.send("No words being counted.")
            
        embed = Embed(title="Word Counts", description="\n".join(
            f"{record['word']}: {record['count']}" for record in counts
        ))
        await ctx.send(embed=embed)

    @commands.command(
        name="countcheck",
        aliases=['ccheck']
    )
    async def count_check(self, ctx, member: Member):
        counts = await self.bot.db.fetch(
            "SELECT word, count FROM word_counts WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )
        
        if not counts:
            return await ctx.send("No words being counted for this user.")
            
        embed = Embed(title="Word Counts", description="\n".join(
            f"{record['word']}: {record['count']}" for record in counts
        ))
        await ctx.send(embed=embed)

    @commands.Cog.listener("on_message")
    async def counter_check(self, message):
        if message.author.bot or not message.guild:
            return
            
        if message.guild.id not in self.word_counts or message.author.id not in self.word_counts[message.guild.id]:
            return
            
        user_counts = self.word_counts[message.guild.id][message.author.id]
        for word in user_counts:
            if word in message.content:
                await self.bot.db.execute(
                    """UPDATE word_counts 
                        SET count = count + 1 
                        WHERE guild_id = $1 AND user_id = $2 AND word = $3""",
                    message.guild.id, message.author.id, word
                )

async def setup(bot):
    await bot.add_cog(deathshit(bot))