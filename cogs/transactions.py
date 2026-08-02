import discord
from discord.ext import commands
from discord import app_commands
from typing import Any, Optional
import uuid
from core.manager import manager
from utils.pdf import generate_certificate
import os

OWNER_ID = os.getenv("OWNER_ID", "Owner")

async def get_resolved_shares(client, shares):
    resolved_shares = {}
    for k, v in shares.items():
        if k == OWNER_ID or k == "Owner":
            resolved_shares["Owner"] = v
        else:
            try:
                user = await client.fetch_user(int(k))
                resolved_shares[user.display_name] = v
            except Exception:
                resolved_shares[f"Utilisateur {k}"] = v
    return resolved_shares

class TransferContract(discord.ui.View):
    def __init__(self, source_id_str: str, target_id_str: str, source_name: str, target_name: str, amount: float, source_user_id: Optional[int], target_user_id: int):
        super().__init__(timeout=86400)
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
        
        self.remove_item(self.sign_receiver)

    async def update_message(self, interaction: discord.Interaction, pdf_file=None):
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
                if pdf_file:
                    await getattr(interaction.channel, 'send')(f"🎉 **Transaction scellée.** `{self.source_name}` a transféré **{self.amount:.2f}%** à `{self.target_name}`.", file=pdf_file)
                else:
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
        self.remove_item(self.sign_sender)
        self.add_item(self.sign_receiver)
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
        
        try:
            manager.transfer(self.source_id_str, self.target_id_str, self.amount, "Contrat Double", self.contract_id)
            
            # PDF Generation
            resolved_shares = await get_resolved_shares(interaction.client, manager.get_shares())
            title = f"Transfert de parts ({self.amount:.2f}%)"
            details = f"L'actionnaire {self.source_name} a transféré {self.amount:.2f}% de ses parts à {self.target_name}."
            
            pdf_file = generate_certificate(self.contract_id, title, details, resolved_shares)
            
            await self.update_message(interaction, pdf_file=pdf_file)
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
            return await interaction.response.send_message("❌ Cette commande doit être exécutée dans un serveur.", ephemeral=True)

        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Seul un administrateur peut signer une dilution.", ephemeral=True)

        try:
            manager.dilute(self.new_member_id_str, self.amount, str(interaction.user), self.contract_id)
            
            # Generate PDF
            resolved_shares = await get_resolved_shares(interaction.client, manager.get_shares())
            title = f"Dilution Globale ({self.amount:.2f}% alloués à {self.new_member_name})"
            details = f"L'administrateur {interaction.user} a validé une dilution globale. {self.amount:.2f}% des parts ont été créées et allouées à {self.new_member_name}."
            
            pdf_file = generate_certificate(self.contract_id, title, details, resolved_shares)

            for child in self.children:
                if hasattr(child, 'disabled'):
                    child.disabled = True # type: ignore
            
            if interaction.message and interaction.message.embeds:
                embed = interaction.message.embeds[0]
                embed.color = discord.Color.green()
                embed.title = f"✅ Dilution Validée : {self.contract_id}"
                embed.add_field(name="Signé par", value=str(interaction.user), inline=False)
                await interaction.response.edit_message(embed=embed, view=self)
            
            if hasattr(interaction.channel, 'send') and interaction.channel:
                await getattr(interaction.channel, 'send')(f"📉 **Cap Table mise à jour.** Les parts ont été diluées pour l'entrée de `{self.new_member_name}`.", file=pdf_file)
                
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

    @commands.hybrid_command(name="diluer", description="Génère un contrat de dilution pour entrer un nouvel actionnaire.")
    @app_commands.describe(nouveau_membre="Nouvel actionnaire", pourcentage="Pourcentage alloué (ex: 10)")
    async def diluer(self, ctx: commands.Context[Any], nouveau_membre: discord.Member, pourcentage: float):
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

    @commands.hybrid_command(name="claim", description="[ADMIN] S'attribue les 100% de base du compte fictif 'Owner'.")
    @commands.has_permissions(administrator=True)
    async def claim(self, ctx: commands.Context[Any]):
        try:
            owner_shares = manager.shares.get(OWNER_ID, 0.0)
            if owner_shares <= 0:
                await ctx.send("❌ Le compte `Owner` n'a plus de parts à distribuer.")
                return
                
            admin_id_str = str(ctx.author.id)
            admin_name = ctx.author.display_name
            contract_id = str(uuid.uuid4())[:8].upper()
            
            manager.transfer(OWNER_ID, admin_id_str, owner_shares, str(ctx.author), contract_id)
            await ctx.send(f"🎉 **Succès !** `{admin_name}` vient de réclamer les {owner_shares:.2f}% de `Owner`. Vous pouvez maintenant utiliser l'autocomplétion native pour transférer vos parts !")
        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")

async def setup(bot):
    await bot.add_cog(TransactionsCog(bot))
