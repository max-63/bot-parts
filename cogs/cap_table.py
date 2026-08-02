import discord
from discord.ext import commands
from typing import Any
import json
import urllib.parse
from datetime import datetime
from core.manager import manager
from utils.pdf import generate_history_pdf
import os

OWNER_ID = os.getenv("OWNER_ID", "Owner")

def generate_quickchart_url(labels, data):
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

class CapTableCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_resolved_labels(self, shares):
        resolved_labels = []
        for k in shares.keys():
            if k == "Owner":
                resolved_labels.append("Owner (Non Réclamé)")
            else:
                try:
                    # Utilisation de fetch_user pour éviter les problèmes de cache (Inconnu)
                    user = await self.bot.fetch_user(int(k))
                    resolved_labels.append(user.display_name)
                except Exception:
                    resolved_labels.append(f"Utilisateur {k}")
        return resolved_labels

    async def build_parts_embed(self):
        shares = manager.get_shares()
        if not shares:
            return discord.Embed(title="📊 Table de Capitalisation", description="Aucune part enregistrée.")
            
        labels = await self.get_resolved_labels(shares)
        data = list(shares.values())
        
        embed = discord.Embed(
            title="📊 Table de Capitalisation - Ondura (Live)", 
            description="Répartition actuelle de l'équité du projet. Actualisé en temps réel.",
            color=0x2b6cb0,
            timestamp=datetime.now()
        )
        
        description = "```\n"
        description += f"{'Actionnaire':<20} | {'Parts':<10} | {'Décimal':<10}\n"
        description += "-" * 46 + "\n"
        
        total = 0.0
        for name, percentage in zip(labels, data):
            decimal_val = percentage / 100.0
            description += f"{name[:19]:<20} | {percentage:>8.2f}% | {decimal_val:>8.4f}\n"
            total += percentage
            
        description += "-" * 46 + "\n"
        description += f"{'TOTAL':<20} | {total:>8.2f}% | {total/100.0:>8.4f}\n"
        description += "```"
        
        embed.add_field(name="Détail des actions", value=description, inline=False)
        
        chart_url = generate_quickchart_url(labels, data)
        embed.set_image(url=chart_url)
        
        icon_url = self.bot.user.avatar.url if self.bot.user and self.bot.user.avatar else None
        embed.set_footer(text="Ondura Smart Contracts", icon_url=icon_url)
        return embed

    @commands.hybrid_command(name="parts", description="Affiche la table de capitalisation sous forme de graphique professionnel.")
    async def parts(self, ctx: commands.Context[Any]):
        embed = await self.build_parts_embed()
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="spawn_dashboard", description="[CREATEUR] Crée le tableau de bord permanent.")
    async def spawn_dashboard(self, ctx: commands.Context[Any]):
        if ctx.guild and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("❌ Seul le créateur du serveur peut faire ça.", ephemeral=True)
            return
            
        embed = await self.build_parts_embed()
        msg = await ctx.send(embed=embed)
        
        manager.config["dashboard_channel_id"] = msg.channel.id  # pyright: ignore[reportArgumentType]
        manager.config["dashboard_msg_id"] = msg.id  # pyright: ignore[reportArgumentType]
        manager.save_config()
        await ctx.send("✅ Dashboard installé avec succès ! Il s'actualisera tout seul.", ephemeral=True)

    @commands.hybrid_command(name="historique", description="Génère un PDF avec l'historique depuis le dernier Reset.")
    async def historique(self, ctx: commands.Context[Any]):
        if not manager.history:
            await ctx.send("📝 Aucun historique disponible pour le moment.")
            return
            
        recent_history = []
        for entry in reversed(manager.history):
            recent_history.append(entry)
            if entry.get("type") == "RESET":
                break
        recent_history.reverse()
        
        pdf_file = generate_history_pdf(recent_history)
        await ctx.send("📜 **Voici le registre officiel des transactions depuis la dernière réinitialisation :**", file=pdf_file)

    @commands.hybrid_command(name="reset", description="[ADMIN] Réinitialise la Cap Table (Attention !)")
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx: commands.Context[Any]):
        try:
            manager.reset(str(ctx.author))
            await ctx.send("🔄 **Cap Table réinitialisée.** `Owner` possède de nouveau 100% des parts.")
            await refresh_dashboard(ctx.bot)
        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")

    @commands.hybrid_command(name="dividendes", description="Simule la distribution d'une somme selon les parts de chacun.")
    @app_commands.describe(montant="Le montant total à distribuer (en euros ou autre devise)")
    async def dividendes(self, ctx: commands.Context[Any], montant: float):
        shares = manager.get_shares()
        if not shares:
            await ctx.send("Aucune part enregistrée.")
            return
            
        labels = await self.get_resolved_labels(shares)
        data = list(shares.values())
        
        embed = discord.Embed(
            title="💰 Simulateur de Dividendes",
            description=f"Répartition de **{montant:,.2f}** selon la table de capitalisation actuelle.",
            color=0x38a169,
            timestamp=datetime.now()
        )
        
        description = "```\n"
        description += f"{'Actionnaire':<20} | {'Parts':<8} | {'Montant':<12}\n"
        description += "-" * 47 + "\n"
        
        total_distrib = 0.0
        for name, percentage in zip(labels, data):
            part_val = (percentage / 100.0) * montant
            description += f"{name[:19]:<20} | {percentage:>7.2f}% | {part_val:>11,.2f}\n"
            total_distrib += part_val
            
        description += "-" * 47 + "\n"
        description += f"{'TOTAL':<20} | {100.0:>7.2f}% | {total_distrib:>11,.2f}\n"
        description += "```"
        
        embed.add_field(name="Détail de la répartition", value=description, inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CapTableCog(bot))

async def refresh_dashboard(client: discord.Client):
    channel_id = manager.config.get("dashboard_channel_id")
    msg_id = manager.config.get("dashboard_msg_id")
    if not channel_id or not msg_id:
        return
        
    try:
        channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
        msg = await channel.fetch_message(msg_id)
        
        cog = client.get_cog("CapTableCog")
        if cog:
            embed = await cog.build_parts_embed() # type: ignore
            await msg.edit(embed=embed)
    except Exception as e:
        print(f"Failed to update dashboard: {e}")
