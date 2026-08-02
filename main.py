import discord
from discord.ext import commands
import os
import dotenv

dotenv.load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
if GUILD_ID:
    GUILD_ID = int(GUILD_ID)

class SharesBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Chargement des Cogs
        await self.load_extension("cogs.cap_table")
        await self.load_extension("cogs.transactions")
        
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        print("Commandes Slash synchronisées.")

bot = SharesBot()

@bot.event
async def on_ready():
    bot_id = bot.user.id if bot.user else "Inconnu"
    print(f'Bot Cap Table connecté : {bot.user} (ID: {bot_id})')
    print('------')

if __name__ == "__main__":
    if not TOKEN:
        print("Erreur : Veuillez configurer votre DISCORD_TOKEN dans le fichier .env")
    else:
        bot.run(TOKEN)
