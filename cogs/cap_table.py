import discord
from discord.ext import commands
from typing import Any
import json
import urllib.parse
from datetime import datetime
from core.manager import manager
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
            if k == OWNER_ID or k == "Owner":
                resolved_labels.append("Owner")
            else:
                try:
                    # Utilisation de fetch_user pour éviter les problèmes de cache (Inconnu)
                    user = await self.bot.fetch_user(int(k))
                    resolved_labels.append(user.display_name)
                except Exception:
                    resolved_labels.append(f"Utilisateur {k}")
        return resolved_labels

    @commands.hybrid_command(name="parts", description="Affiche la table de capitalisation sous forme de graphique professionnel.")
    async def parts(self, ctx: commands.Context[Any]):
        shares = manager.get_shares()
        if not shares:
            await ctx.send("Aucune part enregistrée.")
            return
            
        # Résolution des noms via fetch_user (API en temps réel)
        labels = await self.get_resolved_labels(shares)
        data = list(shares.values())
        
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
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="historique", description="Affiche les dernières transactions et contrats scellés.")
    async def historique(self, ctx: commands.Context[Any]):
        if not manager.history:
            await ctx.send("📝 Aucun historique disponible pour le moment.")
            return
            
        embed = discord.Embed(title="📜 Historique des Transactions", color=0x718096, timestamp=datetime.now())
        
        recent_history = manager.history[-10:]
        recent_history.reverse()
        
        for entry in recent_history:
            date_str = datetime.fromisoformat(entry['timestamp']).strftime('%Y-%m-%d %H:%M')
            title = f"[{entry['type']}] ID: {entry['id']}"
            desc = f"**Action:** {entry['details']}\n**Par:** `{entry['executor']}`\n*Le {date_str}*"
            embed.add_field(name=title, value=desc, inline=False)
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="reset", description="[ADMIN] Réinitialise la Cap Table (Attention !)")
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx: commands.Context[Any]):
        try:
            manager.reset(str(ctx.author))
            await ctx.send("🔄 **Cap Table réinitialisée.** `Owner` possède de nouveau 100% des parts.")
        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")

async def setup(bot):
    await bot.add_cog(CapTableCog(bot))
