import discord
from discord.ext import commands
import asyncio

# Simple test bot to debug connection issues
class TestBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Enable if you enabled it in dev portal
        super().__init__(command_prefix='!test ', intents=intents)
    
    async def on_ready(self):
        print("=" * 50)
        print(f"🤖 Bot User: {self.user}")
        print(f"🆔 Bot ID: {self.user.id}")
        print(f"📊 Connected to {len(self.guilds)} server(s)")
        
        if len(self.guilds) == 0:
            print("❌ WARNING: Bot is not in any servers!")
            print("🔗 You need to invite the bot to a server first")
        else:
            print("✅ Connected to these servers:")
            for i, guild in enumerate(self.guilds, 1):
                print(f"   {i}. {guild.name} (ID: {guild.id}) - {guild.member_count} members")
                
                # Check bot's permissions in this server
                bot_member = guild.get_member(self.user.id)
                if bot_member:
                    permissions = bot_member.guild_permissions
                    print(f"      Permissions: Send Messages={permissions.send_messages}, Read Messages={permissions.read_messages}")
        
        print("=" * 50)
        print("✅ Bot is ready! Try these commands in Discord:")
        print("   !test ping")
        print("   !test hello")
        print("=" * 50)
    
    async def on_guild_join(self, guild):
        print(f"🎉 Bot joined server: {guild.name}")
    
    async def on_message(self, message):
        # Don't respond to ourselves
        if message.author == self.user:
            return
            
        # Debug: Print all messages the bot can see
        print(f"📨 Message from {message.author}: {message.content}")
        
        # Process commands
        await self.process_commands(message)

bot = TestBot()

@bot.command(name='ping')
async def ping(ctx):
    """Test command to check if bot responds"""
    print(f"🏓 Ping command received from {ctx.author}")
    await ctx.send('🏓 Pong! Bot is working!')

@bot.command(name='hello')
async def hello(ctx):
    """Another test command"""
    print(f"👋 Hello command received from {ctx.author}")
    await ctx.send(f'👋 Hello {ctx.author.mention}! I can see your messages!')

@bot.command(name='debug')
async def debug_info(ctx):
    """Show debug information"""
    embed = discord.Embed(title="🔍 Debug Info", color=0x00ff00)
    embed.add_field(name="Server", value=ctx.guild.name if ctx.guild else "DM", inline=True)
    embed.add_field(name="Channel", value=ctx.channel.name, inline=True)
    embed.add_field(name="User", value=ctx.author.name, inline=True)
    embed.add_field(name="Bot ID", value=bot.user.id, inline=True)
    embed.add_field(name="Prefix", value="!test ", inline=True)
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    print(f"❌ Command error: {error}")
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found. Try `!test ping` or `!test hello`")
    else:
        await ctx.send(f"❌ Error: {str(error)}")

if __name__ == "__main__":
    TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"
    
    if TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("❌ Please set your Discord bot token!")
        print("Replace TOKEN = 'YOUR_DISCORD_BOT_TOKEN_HERE' with your actual token")
        exit(1)
    
    print("🚀 Starting test bot...")
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid bot token!")
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")