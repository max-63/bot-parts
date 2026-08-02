import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
import urllib.parse
from datetime import datetime
from datetime import datetime
import uuid
from typing import Any, Optional
from dotenv import load_dotenv

# Chargement du .env
load_dotenv()

# Configuration
TOKEN = os.getenv("DISCORD_TOKEN")
_guild_id = os.getenv("GUILD_ID")
GUILD_ID = int(_guild_id) if _guild_id else None
OWNER_ID = os.getenv("OWNER_ID", "Owner")

SHARES_FILE = "shares.json"
HISTORY_FILE = "history.json"

class SharesManager:
    def __init__(self, filename, history_filename):
        self.filename = filename
        self.history_filename = history_filename
        self.shares = self.load_shares()
        self.history = self.load_history()

    def load_shares(self):
        if not os.path.exists(self.filename):
            return {OWNER_ID: 100.0}
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {k: float(v) for k, v in data.items()}
        except Exception:
            return {OWNER_ID: 100.0}

    def load_history(self):
        if not os.path.exists(self.history_filename):
            return []
        try:
            with open(self.history_filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_shares(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.shares, f, indent=4)

    def save_history(self):
        with open(self.history_filename, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=4)

    def get_shares(self):
        return dict(sorted(self.shares.items(), key=lambda item: item[1], reverse=True))

    def log_action(self, action_type, details, executor, contract_id):
        log_entry = {
            "id": contract_id,
            "timestamp": datetime.now().isoformat(),
            "type": action_type,
            "executor": executor,
            "details": details
        }
        self.history.append(log_entry)
        self.save_history()

    def transfer(self, source: str, target: str, amount: float, executor: str, contract_id: str):
        amount = round(amount, 2)
        if amount <= 0:
            raise ValueError("Le pourcentage doit être supérieur à 0.")
        
        source_share = self.shares.get(source, 0.0)
        if source_share < amount:
            raise ValueError(f"'{source}' n'a pas assez de parts ({source_share:.2f}%).")

        self.shares[source] = round(source_share - amount, 2)
        if self.shares[source] == 0:
            del self.shares[source]

        self.shares[target] = round(self.shares.get(target, 0.0) + amount, 2)
        self.save_shares()
        self.log_action("TRANSFERT", f"{source} a donné {amount:.2f}% à {target}", executor, contract_id)

    def dilute(self, new_member: str, amount: float, executor: str, contract_id: str):
        amount = round(amount, 2)
        if amount <= 0 or amount >= 100:
            raise ValueError("Le pourcentage doit être entre 0 et 100.")
        
        factor = (100.0 - amount) / 100.0
        total_after = 0.0
        
        for member in list(self.shares.keys()):
            new_share = round(self.shares[member] * factor, 2)
            if new_share == 0:
                del self.shares[member]
            else:
                self.shares[member] = new_share
                total_after += new_share
        
        actual_new_share = round(100.0 - total_after, 2)
        self.shares[new_member] = round(self.shares.get(new_member, 0.0) + actual_new_share, 2)
        self.save_shares()
        self.log_action("DILUTION", f"Nouvel actionnaire {new_member} avec {amount:.2f}%", executor, contract_id)

    def reset(self, executor: str):
        self.shares = {OWNER_ID: 100.0}
        self.save_shares()
        self.log_action("RESET", "Réinitialisation de la table", executor, str(uuid.uuid4())[:8])


manager = SharesManager(SHARES_FILE, HISTORY_FILE)

# --- UI Components pour les Contrats ---

class TransferContract(discord.ui.View):
    def __init__(self, source_id_str: str, target_id_str: str, source_name: str, target_name: str, amount: float, source_user_id: Optional[int], target_user_id: int):
        super().__init__(timeout=86400) # Expire dans 24h
        self.source_id_str = source_id_str
        self.target_id_str = target_id_str
        self.source_name = source_name
        self.target_name = target_name
        self.amount = amount
        self.source_user_id = source_user_id
        self.target_user_id = target_user_id
        self.contract_id = str(uuid.uuid4())[:8].upper()
        
        self.sender_signed = False
        self.receiver_signed = False

    async def update_message(self, interaction: discord.Interaction):
        if not interaction.message or not interaction.message.embeds:
            return
            
        embed = interaction.message.embeds[0]
        
        if self.sender_signed and self.receiver_signed:
            embed.color = discord.Color.green()
            embed.title = f"✅ Contrat Validé : {self.contract_id}"
            
            for child in self.children:
                if hasattr(child, 'disabled'):
                    child.disabled = True # type: ignore
                    
            await interaction.response.edit_message(embed=embed, view=self)
            
            if hasattr(interaction.channel, 'send') and interaction.channel:
                await getattr(interaction.channel, 'send')(f"🎉 **Transaction scellée.** `{self.source_name}` a transféré **{self.amount:.2f}%** à `{self.target_name}`.")
        else:
            status_text = f"Expéditeur : {'✅ Signé' if self.sender_signed else '⏳ En attente'}\n"
            status_text += f"Receveur : {'✅ Signé' if self.receiver_signed else '⏳ En attente'}"
            
            found = False
            for i, field in enumerate(embed.fields):
                if field.name == "Statut des Signatures":
                    embed.set_field_at(i, name="Statut des Signatures", value=status_text, inline=False)
                    found = True
                    break
            
            if not found:
                embed.add_field(name="Statut des Signatures", value=status_text, inline=False)
                
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="✍️ Signer (Expéditeur)", style=discord.ButtonStyle.primary)
    async def sign_sender(self, interaction: discord.Interaction, button: discord.ui.Button[Any]):
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)
            
        if self.source_user_id is not None and interaction.user.id != self.source_user_id and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Vous n'êtes pas autorisé à signer ce contrat en tant qu'expéditeur.", ephemeral=True)
            
        if self.source_user_id is None and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Ce compte n'a pas de propriétaire assigné. Seul un administrateur peut forcer l'envoi.", ephemeral=True)
            
        self.sender_signed = True
        button.disabled = True
        button.style = discord.ButtonStyle.success
        
        if self.sender_signed and self.receiver_signed:
            try:
                manager.transfer(self.source_id_str, self.target_id_str, self.amount, "Contrat Double", self.contract_id)
            except ValueError as e:
                # Si erreur de solde, on annule le contrat
                embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed()
                embed.color = discord.Color.red()
                embed.title = f"❌ Contrat Annulé : Erreur"
                embed.add_field(name="Raison", value=str(e), inline=False)
                for child in self.children:
                    if hasattr(child, 'disabled'):
                        child.disabled = True # type: ignore
                await interaction.response.edit_message(embed=embed, view=self)
                return
            
        await self.update_message(interaction)

    @discord.ui.button(label="✍️ Signer (Receveur)", style=discord.ButtonStyle.primary)
    async def sign_receiver(self, interaction: discord.Interaction, button: discord.ui.Button[Any]):
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)
            
        if interaction.user.id != self.target_user_id and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Vous n'êtes pas autorisé à signer ce contrat en tant que receveur.", ephemeral=True)
            
        self.receiver_signed = True
        button.disabled = True
        button.style = discord.ButtonStyle.success
        
        if self.sender_signed and self.receiver_signed:
            try:
                manager.transfer(self.source_id_str, self.target_id_str, self.amount, "Contrat Double", self.contract_id)
            except ValueError as e:
                embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed()
                embed.color = discord.Color.red()
                embed.title = f"❌ Contrat Annulé : Erreur"
                embed.add_field(name="Raison", value=str(e), inline=False)
                for child in self.children:
                    if hasattr(child, 'disabled'):
                        child.disabled = True # type: ignore
                await interaction.response.edit_message(embed=embed, view=self)
                return
            
        await self.update_message(interaction)

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button[Any]):
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)

        is_sender = (self.source_user_id is not None and interaction.user.id == self.source_user_id)
        is_receiver = (interaction.user.id == self.target_user_id)
        
        if not (is_sender or is_receiver or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ Seuls les participants ou un admin peuvent annuler.", ephemeral=True)
            
        for child in self.children:
            if hasattr(child, 'disabled'):
                child.disabled = True # type: ignore
            
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = f"❌ Contrat Annulé : {self.contract_id}"
            embed.add_field(name="Annulé par", value=str(interaction.user), inline=False)
            await interaction.response.edit_message(embed=embed, view=self)


class DilutionContract(discord.ui.View):
    def __init__(self, new_member_id_str: str, new_member_name: str, amount: float):
        super().__init__(timeout=86400)
        self.new_member_id_str = new_member_id_str
        self.new_member_name = new_member_name
        self.amount = amount
        self.contract_id = str(uuid.uuid4())[:8].upper()

    @discord.ui.button(label="✍️ Signer la Dilution (Admin)", style=discord.ButtonStyle.success)
    async def sign_button(self, interaction: discord.Interaction, button: discord.ui.Button[Any]):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Seul un administrateur peut signer une dilution.", ephemeral=True)
            return

        try:
            manager.dilute(self.new_member_id_str, self.amount, str(interaction.user), self.contract_id)
            for child in self.children:
                if hasattr(child, 'disabled'):
                    child.disabled = True # type: ignore
            
            if interaction.message and interaction.message.embeds:
                embed = interaction.message.embeds[0]
                embed.color = discord.Color.green()
                embed.title = f"✅ Dilution Validée : {self.contract_id}"
                embed.add_field(name="Signé par", value=str(interaction.user), inline=False)
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.response.send_message("Dilution scellée, mais message original introuvable.", ephemeral=True)
            
            if hasattr(interaction.channel, 'send') and interaction.channel:
                await getattr(interaction.channel, 'send')(f"📉 **Cap Table mise à jour.** Les parts ont été diluées pour l'entrée de `{self.new_member_name}` avec **{self.amount:.2f}%**.")
        except ValueError as e:
            if interaction.message and interaction.message.embeds:
                embed = interaction.message.embeds[0]
                embed.color = discord.Color.red()
                embed.title = f"❌ Dilution Annulée : Erreur"
                embed.add_field(name="Raison", value=str(e), inline=False)
                for child in self.children:
                    if hasattr(child, 'disabled'):
                        child.disabled = True # type: ignore
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de l'exécution : {e}", ephemeral=True)

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Seul un administrateur peut refuser.", ephemeral=True)
            return
            
        for child in self.children:
            if hasattr(child, 'disabled'):
                child.disabled = True # type: ignore
            
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = f"❌ Contrat de Dilution Annulé : {self.contract_id}"
            await interaction.response.edit_message(embed=embed, view=self)

# --- Initialisation Bot ---

class SharesBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
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

def generate_quickchart_url(shares):
    labels = list(shares.keys())
    data = list(shares.values())
    
    # Palette professionnelle
    colors = ["#2b6cb0", "#c53030", "#38a169", "#d69e2e", "#805ad5", "#319795"]
    
    chart_config = {
        "type": "pie",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": data,
                "backgroundColor": colors[:len(labels)],
                "borderColor": "#1a202c",
                "borderWidth": 2
            }]
        },
        "options": {
            "plugins": {
                "legend": {
                    "position": "right",
                    "labels": { "color": "#e2e8f0", "font": { "size": 16, "family": "Helvetica" } }
                },
                "datalabels": { "color": "#ffffff", "font": { "weight": "bold", "size": 14 } }
            }
        }
    }
    
    config_json = json.dumps(chart_config)
    encoded_config = urllib.parse.quote(config_json)
    return f"https://quickchart.io/chart?c={encoded_config}&w=600&h=300&bkg=transparent"

@bot.hybrid_command(name="parts", description="Affiche la table de capitalisation (Cap Table) sous forme de graphique professionnel.")
async def parts(ctx: commands.Context[Any]):
    shares = manager.get_shares()
    if not shares:
        await ctx.send("Aucune part enregistrée.")
        return
    
    embed = discord.Embed(
        title="📊 Table de Capitalisation - Ondura", 
        description="Répartition actuelle de l'équité du projet.",
        color=0x2b6cb0,
        timestamp=datetime.now()
    )
    
    description = "```\n"
    description += f"{'Actionnaire':<20} | {'Parts':<10} | {'Décimal':<10}\n"
    description += "-" * 46 + "\n"
    
    total = 0.0
    for member, percentage in shares.items():
        decimal_val = percentage / 100.0
        description += f"{member:<20} | {percentage:>8.2f}% | {decimal_val:>8.4f}\n"
        total += percentage
        
    description += "-" * 46 + "\n"
    description += f"{'TOTAL':<20} | {total:>8.2f}% | {total/100.0:>8.4f}\n"
    description += "```"
    
    embed.add_field(name="Détail des actions", value=description, inline=False)
    
    # Ajout du graphique via QuickChart (zéro RAM utilisée)
    chart_url = generate_quickchart_url(shares)
    embed.set_image(url=chart_url)
    
    icon_url = bot.user.avatar.url if bot.user and bot.user.avatar else None
    embed.set_footer(text="Ondura Smart Contracts", icon_url=icon_url)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="historique", description="Affiche les dernières transactions et contrats scellés.")
async def historique(ctx: commands.Context[Any]):
    if not manager.history:
        await ctx.send("📝 Aucun historique disponible pour le moment.")
        return
        
    embed = discord.Embed(title="📜 Historique des Transactions", color=0x718096, timestamp=datetime.now())
    
    recent_history = manager.history[-10:] # Affiche les 10 dernières
    recent_history.reverse()
    
    for entry in recent_history:
        date_str = datetime.fromisoformat(entry['timestamp']).strftime('%Y-%m-%d %H:%M')
        title = f"[{entry['type']}] ID: {entry['id']}"
        desc = f"**Action:** {entry['details']}\n**Par:** `{entry['executor']}`\n*Le {date_str}*"
        embed.add_field(name=title, value=desc, inline=False)
        
    await ctx.send(embed=embed)

@bot.hybrid_command(name="donner", description="Génère un contrat de transfert de parts.")
@app_commands.describe(source="L'actionnaire qui donne", cible="Le receveur", pourcentage="Montant en %")
async def donner(ctx: commands.Context[Any], source: discord.Member, cible: discord.Member, pourcentage: float):
    try:
        pourcentage = round(pourcentage, 2)
        if pourcentage <= 0:
            raise ValueError("Le pourcentage doit être supérieur à 0.")
            
        source_id_str = str(source.id)
        cible_id_str = str(cible.id)
        source_name = source.display_name
        cible_name = cible.display_name
        
        view = TransferContract(source_id_str, cible_id_str, source_name, cible_name, pourcentage, source.id, cible.id)
        
        embed = discord.Embed(
            title="📜 Contrat de Transfert - En Attente",
            description=f"Demande de transfert d'équité initiée par {ctx.author.mention}.\n\nCe contrat doit être signé par **les deux parties** pour être validé.",
            color=0xd69e2e
        )
        embed.add_field(name="Expéditeur", value=f"{source_name}", inline=True)
        embed.add_field(name="Bénéficiaire", value=f"{cible_name}", inline=True)
        embed.add_field(name="Montant", value=f"**{pourcentage:.2f}%**", inline=False)
        embed.add_field(name="Statut des Signatures", value="Expéditeur : ⏳ En attente\nReceveur : ⏳ En attente", inline=False)
        
        embed.set_footer(text=f"ID Contrat : {view.contract_id} | Double Signature Requise")
        
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")

@bot.hybrid_command(name="claim", description="[ADMIN] S'attribue les 100% de base du compte fictif 'Owner'.")
@commands.has_permissions(administrator=True)
async def claim(ctx: commands.Context[Any]):
    try:
        owner_shares = manager.shares.get(OWNER_ID, 0.0)
        if owner_shares <= 0:
            await ctx.send("❌ Le compte `Owner` n'a plus de parts à distribuer.")
            return
            
        admin_id_str = str(ctx.author.id)
        admin_name = ctx.author.display_name
        contract_id = str(uuid.uuid4())[:8].upper()
        
        # On transfère l'équité depuis OWNER_ID vers admin_id_str
        manager.transfer(OWNER_ID, admin_id_str, owner_shares, str(ctx.author), contract_id)
        await ctx.send(f"🎉 **Succès !** `{admin_name}` vient de réclamer les {owner_shares:.2f}% de `Owner`. Vous pouvez maintenant utiliser l'autocomplétion native pour transférer vos parts !")
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")

@bot.hybrid_command(name="diluer", description="Génère un contrat de dilution pour entrer un nouvel actionnaire.")
@app_commands.describe(nouveau_membre="Nouvel actionnaire", pourcentage="Pourcentage alloué (ex: 10)")
async def diluer(ctx: commands.Context[Any], nouveau_membre: discord.Member, pourcentage: float):
    try:
        new_member_id_str = str(nouveau_membre.id)
        new_member_name = nouveau_membre.display_name
        
        view = DilutionContract(new_member_id_str, new_member_name, pourcentage)
        
        embed = discord.Embed(
            title="⚖️ Contrat de Dilution - En Attente",
            description=f"Demande de dilution globale de la Cap Table initiée par {ctx.author.mention}.\n\n⚠️ Une dilution réduit la valeur des parts de **tous les actionnaires actuels** de manière proportionnelle.",
            color=0xd69e2e
        )
        embed.add_field(name="Nouvel Actionnaire", value=f"`{nouveau_membre}`", inline=True)
        embed.add_field(name="Parts allouées", value=f"**{pourcentage:.2f}%**", inline=True)
        embed.set_footer(text=f"ID Contrat : {view.contract_id} | Signature Administrateur requise")
        
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")

@bot.hybrid_command(name="reset", description="[ADMIN] Réinitialise la Cap Table (Attention !)")
@commands.has_permissions(administrator=True)
async def reset(ctx: commands.Context[Any]):
    try:
        manager.reset(str(ctx.author))
        await ctx.send("🔄 **Cap Table réinitialisée.** `Owner` possède de nouveau 100% des parts.")
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")

if __name__ == "__main__":
    if not TOKEN:
        print("Erreur : Veuillez configurer votre DISCORD_TOKEN dans le fichier .env")
    else:
        bot.run(TOKEN)
