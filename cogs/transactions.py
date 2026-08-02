import discord
from discord.ext import commands
from discord import app_commands
from typing import Any, Optional
import uuid
from core.manager import manager
from utils.pdf import generate_certificate
from cogs.cap_table import refresh_dashboard
import os

UNASSIGNED_SHARES_KEY = "Owner"

async def get_resolved_shares(client, shares):
    resolved_shares = {}
    for k, v in shares.items():
        if k == "Owner":
            resolved_shares["Owner (Non Réclamé)"] = v
        else:
            try:
                user = await client.fetch_user(int(k))
                resolved_shares[user.display_name] = v
            except Exception:
                resolved_shares[f"Utilisateur {k}"] = v
    return resolved_shares

class TransferContract(discord.ui.View):
    def __init__(self, source_id_str: str, target_id_str: str, source_name: str, target_name: str, amount: float, board: list):
        super().__init__(timeout=86400)
        self.source_id_str = source_id_str
        self.target_id_str = target_id_str
        self.source_name = source_name
        self.target_name = target_name
        self.amount = amount
        self.board = board
        self.approvals = {m_id: False for m_id in board}
        self.contract_id = str(uuid.uuid4())[:8].upper()

    async def update_message(self, interaction: discord.Interaction, pdf_file=None, file_hash=None):
        if not interaction.message or not interaction.message.embeds:
            return
            
        embed = interaction.message.embeds[0]
        all_approved = all(self.approvals.values())
        
        if all_approved:
            embed.color = discord.Color.green()
            embed.title = f"✅ Contrat Validé : {self.contract_id}"
            
            for child in self.children:
                if hasattr(child, 'disabled'):
                    child.disabled = True # type: ignore
                    
            await interaction.response.edit_message(embed=embed, view=self)
            
            if hasattr(interaction.channel, 'send') and interaction.channel:
                msg_content = f"🎉 **Transaction scellée.** (Consensus Global Atteint) `{self.source_name}` a transféré **{self.amount:.2f}%** à `{self.target_name}`."
                if file_hash:
                    msg_content += f"\n🔒 **Empreinte SHA-256 du fichier :** `{file_hash}`"
                    
                if pdf_file:
                    await getattr(interaction.channel, 'send')(msg_content, file=pdf_file)
                else:
                    await getattr(interaction.channel, 'send')(msg_content)
        else:
            status_lines = []
            for member_id, approved in self.approvals.items():
                status = "✅ Approuvé" if approved else "⏳ En attente"
                status_lines.append(f"{status} : <@{member_id}>")
            status_text = "\n".join(status_lines)
            
            found = False
            for i, field in enumerate(embed.fields):
                if field.name == "Board Approval (Consensus)":
                    embed.set_field_at(i, name="Board Approval (Consensus)", value=status_text, inline=False)
                    found = True
                    break
            
            if not found:
                embed.add_field(name="Board Approval (Consensus)", value=status_text, inline=False)
                
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="✅ Approuver la transaction", style=discord.ButtonStyle.success)
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button[Any]):
        user_id_str = str(interaction.user.id)
        if user_id_str not in self.board:
            return await interaction.response.send_message("❌ Vous ne faites pas partie de la Cap Table, vous ne pouvez pas voter.", ephemeral=True)
            
        if self.approvals.get(user_id_str):
            return await interaction.response.send_message("Vous avez déjà approuvé.", ephemeral=True)
        self.approvals[user_id_str] = True
            
        all_approved = all(self.approvals.values())
        
        if all_approved:
            button.disabled = True
            try:
                manager.transfer(self.source_id_str, self.target_id_str, self.amount, "Consensus Board", self.contract_id)
                resolved_shares = await get_resolved_shares(interaction.client, manager.get_shares())
                title = f"Transfert de parts ({self.amount:.2f}%)"
                details = f"L'actionnaire {self.source_name} a transféré {self.amount:.2f}% de ses parts à {self.target_name} avec l'approbation unanime du Board."
                pdf_file, file_hash = generate_certificate(self.contract_id, title, details, resolved_shares)
                await self.update_message(interaction, pdf_file=pdf_file, file_hash=file_hash)
                await refresh_dashboard(interaction.client)
                return
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

    @discord.ui.button(label="❌ Veto (Annuler)", style=discord.ButtonStyle.danger)
    async def veto_button(self, interaction: discord.Interaction, button: discord.ui.Button[Any]):
        user_id_str = str(interaction.user.id)
        if user_id_str not in self.board:
            return await interaction.response.send_message("❌ Vous ne faites pas partie de la Cap Table, vous ne pouvez pas mettre de Veto.", ephemeral=True)
            
        for child in self.children:
            if hasattr(child, 'disabled'):
                child.disabled = True # type: ignore
            
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = f"❌ Contrat Annulé (Veto) : {self.contract_id}"
            embed.add_field(name="Veto posé par", value=str(interaction.user), inline=False)
            await interaction.response.edit_message(embed=embed, view=self)


class DilutionContract(discord.ui.View):
    def __init__(self, new_member_id_str: str, new_member_name: str, amount: float, board: list):
        super().__init__(timeout=86400)
        self.new_member_id_str = new_member_id_str
        self.new_member_name = new_member_name
        self.amount = amount
        self.board = board
        self.approvals = {m_id: False for m_id in board}
        self.contract_id = str(uuid.uuid4())[:8].upper()

    async def update_message(self, interaction: discord.Interaction, pdf_file=None, file_hash=None):
        if not interaction.message or not interaction.message.embeds:
            return
            
        embed = interaction.message.embeds[0]
        all_approved = all(self.approvals.values())
        
        if all_approved:
            embed.color = discord.Color.green()
            embed.title = f"✅ Dilution Validée : {self.contract_id}"
            
            for child in self.children:
                if hasattr(child, 'disabled'):
                    child.disabled = True # type: ignore
                    
            await interaction.response.edit_message(embed=embed, view=self)
            
            if hasattr(interaction.channel, 'send') and interaction.channel:
                msg_content = f"📉 **Cap Table mise à jour.** (Consensus Global Atteint) Les parts ont été diluées pour l'entrée de `{self.new_member_name}`."
                if file_hash:
                    msg_content += f"\n🔒 **Empreinte SHA-256 du fichier :** `{file_hash}`"
                    
                if pdf_file:
                    await getattr(interaction.channel, 'send')(msg_content, file=pdf_file)
                else:
                    await getattr(interaction.channel, 'send')(msg_content)
        else:
            status_lines = []
            for member_id, approved in self.approvals.items():
                status = "✅ Approuvé" if approved else "⏳ En attente"
                status_lines.append(f"{status} : <@{member_id}>")
            status_text = "\n".join(status_lines)
            
            found = False
            for i, field in enumerate(embed.fields):
                if field.name == "Board Approval (Consensus)":
                    embed.set_field_at(i, name="Board Approval (Consensus)", value=status_text, inline=False)
                    found = True
                    break
            
            if not found:
                embed.add_field(name="Board Approval (Consensus)", value=status_text, inline=False)
                
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="✅ Approuver la Dilution", style=discord.ButtonStyle.success)
    async def sign_button(self, interaction: discord.Interaction, button: discord.ui.Button[Any]):
        user_id_str = str(interaction.user.id)
        if user_id_str not in self.board:
            return await interaction.response.send_message("❌ Vous ne faites pas partie de la Cap Table, vous ne pouvez pas voter.", ephemeral=True)

        if self.approvals.get(user_id_str):
            return await interaction.response.send_message("Vous avez déjà approuvé.", ephemeral=True)
        self.approvals[user_id_str] = True

        all_approved = all(self.approvals.values())

        if all_approved:
            button.disabled = True
            try:
                manager.dilute(self.new_member_id_str, self.amount, "Consensus Board", self.contract_id)
                resolved_shares = await get_resolved_shares(interaction.client, manager.get_shares())
                title = f"Dilution Globale ({self.amount:.2f}% alloués à {self.new_member_name})"
                details = f"Le Board a validé une dilution globale à l'unanimité. {self.amount:.2f}% des parts ont été créées et allouées à {self.new_member_name}."
                
                pdf_file, file_hash = generate_certificate(self.contract_id, title, details, resolved_shares)
                await self.update_message(interaction, pdf_file=pdf_file, file_hash=file_hash)
                await refresh_dashboard(interaction.client)
                return
                    
            except ValueError as e:
                embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed()
                embed.color = discord.Color.red()
                embed.title = f"❌ Dilution Annulée : Erreur"
                embed.add_field(name="Raison", value=str(e), inline=False)
                for child in self.children:
                    if hasattr(child, 'disabled'):
                        child.disabled = True # type: ignore
                await interaction.response.edit_message(embed=embed, view=self)
                return
                
        await self.update_message(interaction)

    @discord.ui.button(label="❌ Veto (Annuler)", style=discord.ButtonStyle.danger)
    async def veto_button(self, interaction: discord.Interaction, button: discord.ui.Button[Any]):
        user_id_str = str(interaction.user.id)
        if user_id_str not in self.board:
            return await interaction.response.send_message("❌ Vous ne faites pas partie de la Cap Table, vous ne pouvez pas mettre de Veto.", ephemeral=True)
            
        for child in self.children:
            if hasattr(child, 'disabled'):
                child.disabled = True # type: ignore
            
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = f"❌ Dilution Annulée (Veto) : {self.contract_id}"
            embed.add_field(name="Veto posé par", value=str(interaction.user), inline=False)
            await interaction.response.edit_message(embed=embed, view=self)


def get_current_board_ids():
    shares = manager.get_shares()
    board = list(shares.keys())
    if UNASSIGNED_SHARES_KEY in board:
        board.remove(UNASSIGNED_SHARES_KEY)
    return board

class TransactionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="donner", description="Génère un contrat de transfert de parts.")
    @app_commands.describe(source="L'actionnaire qui donne", cible="Le receveur", pourcentage="Montant en %")
    async def donner(self, ctx: commands.Context[Any], source: discord.Member, cible: discord.Member, pourcentage: float):
        try:
            pourcentage = round(pourcentage, 2)
            if pourcentage <= 0:
                raise ValueError("Le pourcentage doit être supérieur à 0.")
                
            source_id_str = str(source.id)
            cible_id_str = str(cible.id)
            source_name = source.display_name
            cible_name = cible.display_name
            
            board = get_current_board_ids()
            if source_id_str not in board:
                board.append(source_id_str)
            if cible_id_str not in board:
                board.append(cible_id_str)
                
            view = TransferContract(source_id_str, cible_id_str, source_name, cible_name, pourcentage, board)
            
            embed = discord.Embed(
                title="📜 Contrat de Transfert - En Attente de Consensus",
                description=f"Demande de transfert d'équité initiée par {ctx.author.mention}.\n\n⚠️ **Règle d'Agrément** : Ce contrat doit être approuvé par **100% de la Cap Table actuelle** pour être validé.",
                color=0xd69e2e
            )
            embed.add_field(name="Expéditeur", value=f"{source_name}", inline=True)
            embed.add_field(name="Bénéficiaire", value=f"{cible_name}", inline=True)
            embed.add_field(name="Montant", value=f"**{pourcentage:.2f}%**", inline=False)
            
            status_lines = [f"⏳ En attente : <@{m}>" for m in board]
            embed.add_field(name="Board Approval (Consensus)", value="\n".join(status_lines), inline=False)
            embed.set_footer(text=f"ID Contrat : {view.contract_id} | Consensus Global Requis")
            
            await ctx.send(embed=embed, view=view)
        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")

    @commands.hybrid_command(name="diluer", description="Génère un contrat de dilution pour entrer un nouvel actionnaire.")
    @app_commands.describe(nouveau_membre="Nouvel actionnaire", pourcentage="Pourcentage alloué (ex: 10)")
    async def diluer(self, ctx: commands.Context[Any], nouveau_membre: discord.Member, pourcentage: float):
        try:
            new_member_id_str = str(nouveau_membre.id)
            new_member_name = nouveau_membre.display_name
            
            board = get_current_board_ids()
            if new_member_id_str not in board:
                board.append(new_member_id_str)
            
            view = DilutionContract(new_member_id_str, new_member_name, pourcentage, board)
            
            embed = discord.Embed(
                title="⚖️ Contrat de Dilution - En Attente de Consensus",
                description=f"Demande de dilution globale de la Cap Table initiée par {ctx.author.mention}.\n\n⚠️ Une dilution réduit la valeur des parts de tous les actionnaires actuels. **L'accord unanime du Board est requis.**",
                color=0xd69e2e
            )
            embed.add_field(name="Nouvel Actionnaire", value=f"`{nouveau_membre}`", inline=True)
            embed.add_field(name="Parts allouées", value=f"**{pourcentage:.2f}%**", inline=True)
            
            status_lines = [f"⏳ En attente : <@{m}>" for m in board]
            embed.add_field(name="Board Approval (Consensus)", value="\n".join(status_lines), inline=False)
            embed.set_footer(text=f"ID Contrat : {view.contract_id} | Consensus Global Requis")
            
            await ctx.send(embed=embed, view=view)
        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")

    @commands.hybrid_command(name="claim", description="[ADMIN] S'attribue les 100% de base du compte fictif 'Owner'.")
    @commands.has_permissions(administrator=True)
    async def claim(self, ctx: commands.Context[Any]):
        try:
            owner_shares = manager.shares.get(UNASSIGNED_SHARES_KEY, 0.0)
            if owner_shares <= 0:
                await ctx.send("❌ Le compte `Owner` n'a plus de parts à distribuer.")
                return
                
            admin_id_str = str(ctx.author.id)
            admin_name = ctx.author.display_name
            contract_id = str(uuid.uuid4())[:8].upper()
            
            manager.transfer(UNASSIGNED_SHARES_KEY, admin_id_str, owner_shares, str(ctx.author), contract_id)
            # Force explicite de la sauvegarde pour éviter les soucis
            manager.save_shares()
            
            await ctx.send(f"🎉 **Succès !** `{admin_name}` vient de réclamer les {owner_shares:.2f}% de `Owner`. La Cap Table est désormais active !")
            await refresh_dashboard(ctx.bot)
        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")

async def setup(bot):
    await bot.add_cog(TransactionsCog(bot))
