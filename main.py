import discord
from discord.ext import commands
from discord import app_commands
import os
import dotenv
from core.manager import manager

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

@bot.check
async def global_check(ctx: commands.Context):
    if ctx.command and ctx.command.name in ["setup", "claim"]:
        return True

    # 1. Vérification du Salon
    active_channel = manager.config.get("active_channel_id")
    if active_channel and ctx.channel.id != active_channel:
        # ctx.send with ephemeral works well for hybrid commands
        await ctx.send("❌ Tu n'as pas le droit d'utiliser le bot des affaires dans ce salon, va jouer ailleurs !", ephemeral=True)
        return False
        
    # 2. Vérification de la Cap Table (sauf Administrateur Discord)
    if ctx.author.guild_permissions.administrator:
        return True
        
    user_id_str = str(ctx.author.id)
    board = list(manager.get_shares().keys())
    owner_env = os.getenv("OWNER_ID", "Owner")
    if owner_env in board:
        board.remove(owner_env)
        
    if user_id_str not in board:
        await ctx.send("❌ Dégage le clochard, tu n'as même pas de parts dans la Cap Table ! T'as cru t'étais un actionnaire ?", ephemeral=True)
        return False
        
    return True

@bot.hybrid_command(name="setup", description="[CREATEUR] Définit le salon dans lequel le bot des affaires est actif.")
@app_commands.describe(salon="Le salon textuel autorisé pour le bot")
async def setup_cmd(ctx: commands.Context, salon: discord.TextChannel):
    if ctx.guild and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("❌ Seul le créateur du serveur peut utiliser cette commande.", ephemeral=True)
        return
        
    manager.config["active_channel_id"] = salon.id  # pyright: ignore[reportArgumentType]
    manager.save_config()
    await ctx.send(f"✅ Le bot des affaires est désormais **exclusivement actif** dans le salon {salon.mention}.")

if __name__ == "__main__":
    if not TOKEN:
        print("Erreur : Veuillez configurer votre DISCORD_TOKEN dans le fichier .env")
    else:
        bot.run(TOKEN)
