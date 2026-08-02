import discord
from discord.ext import commands
from discord import app_commands
from typing import Any
import uuid
import os
import tempfile
import hashlib
from datetime import datetime
from core.manager import manager
from fpdf import FPDF
from cogs.transactions import get_current_board_ids, UNASSIGNED_SHARES_KEY

def generate_vote_pdf(question: str, yes_votes: dict, no_votes: dict, result: str):
    pdf = FPDF()
    pdf.add_page()
    
    pdf.ln(10)
    pdf.set_font('helvetica', 'B', 16)
    pdf.cell(0, 10, "DÉCISION D'ASSEMBLÉE GÉNÉRALE", align='C')
    pdf.ln(15)
    
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 8, "Résolution soumise au vote :", ln=True)
    pdf.set_font('helvetica', '', 12)
    pdf.multi_cell(0, 8, f"{question}")
    pdf.ln(10)
    
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 8, "Détail des votes :", ln=True)
    pdf.set_font('helvetica', '', 10)
    
    for member_name, weight in yes_votes.items():
        pdf.cell(0, 6, f"POUR : {member_name} ({weight:.2f}%)", ln=True)
    for member_name, weight in no_votes.items():
        pdf.cell(0, 6, f"CONTRE : {member_name} ({weight:.2f}%)", ln=True)
        
    pdf.ln(10)
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 8, f"RÉSULTAT : {result}", ln=True)
    
    pdf.ln(20)
    pdf.set_font('helvetica', 'I', 8)
    pdf.cell(0, 5, f'Scellé numériquement le {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', align='C')
    
    contract_id = str(uuid.uuid4())[:8].upper()
    temp_path = os.path.join(tempfile.gettempdir(), f"vote_{contract_id}.pdf")
    pdf.output(temp_path)
    
    with open(temp_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
        
    return discord.File(temp_path, filename=f"Resolution_{contract_id}.pdf"), file_hash, contract_id


class VoteView(discord.ui.View):
    def __init__(self, question: str, author_name: str, board: list):
        super().__init__(timeout=86400)
        self.question = question
        self.author_name = author_name
        self.board = board
        # Stocke member_id_str -> (name, weight, choice)
        self.votes = {}
        
    async def get_resolved_name(self, client, user_id_str: str) -> str:
        try:
            user = await client.fetch_user(int(user_id_str))
            return user.display_name
        except:
            return f"Actionnaire {user_id_str}"

    async def update_message(self, interaction: discord.Interaction):
        if not interaction.message or not interaction.message.embeds:
            return
            
        embed = interaction.message.embeds[0]
        
        # Calculate current yes/no
        yes_total = 0.0
        no_total = 0.0
        for data in self.votes.values():
            if data['choice'] == 'OUI':
                yes_total += data['weight']
            else:
                no_total += data['weight']
                
        has_everyone_voted = set(self.board) == set(self.votes.keys())
        
        # S'il ne manque plus personne, on conclut le vote
        if has_everyone_voted:
            result = "ADOPTÉE" if yes_total > no_total else "REJETÉE"
            embed.color = discord.Color.green() if result == "ADOPTÉE" else discord.Color.red()
            embed.title = f"🗳️ Résultat : Résolution {result}"
            
            yes_dict = {d['name']: d['weight'] for d in self.votes.values() if d['choice'] == 'OUI'}
            no_dict = {d['name']: d['weight'] for d in self.votes.values() if d['choice'] == 'NON'}
            
            pdf_file, file_hash, contract_id = generate_vote_pdf(self.question, yes_dict, no_dict, result)
            
            embed.add_field(name="Pour (OUI)", value=f"{yes_total:.2f}%", inline=True)
            embed.add_field(name="Contre (NON)", value=f"{no_total:.2f}%", inline=True)
            embed.set_footer(text=f"Résolution scellée | Hash : {file_hash[:16]}...")
            
            for child in self.children:
                if hasattr(child, 'disabled'):
                    child.disabled = True # type: ignore
                    
            manager.log_action("VOTE_AG", f"Résolution {result} ({yes_total:.2f}% vs {no_total:.2f}%). Question : {self.question}", "Assemblée Générale", contract_id)
            
            await interaction.response.edit_message(embed=embed, view=self)
            
            if interaction.channel:
                await getattr(interaction.channel, 'send')(
                    f"📜 **La résolution a été {result}.**\n🔒 SHA-256 : `{file_hash}`", 
                    file=pdf_file
                )
        else:
            # Update progress
            status_lines = []
            for m_id in self.board:
                if m_id in self.votes:
                    status_lines.append(f"✅ A voté : <@{m_id}>")
                else:
                    status_lines.append(f"⏳ En attente : <@{m_id}>")
            
            found = False
            for i, field in enumerate(embed.fields):
                if field.name == "Participation au vote":
                    embed.set_field_at(i, name="Participation au vote", value="\n".join(status_lines), inline=False)
                    found = True
                    break
            
            if not found:
                embed.add_field(name="Participation au vote", value="\n".join(status_lines), inline=False)
                
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="👍 OUI", style=discord.ButtonStyle.success)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button[Any]):
        await self.register_vote(interaction, "OUI")

    @discord.ui.button(label="👎 NON", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button[Any]):
        await self.register_vote(interaction, "NON")
        
    async def register_vote(self, interaction: discord.Interaction, choice: str):
        user_id_str = str(interaction.user.id)
        if user_id_str not in self.board:
            return await interaction.response.send_message("❌ Vous ne faites pas partie de la Cap Table, vous ne pouvez pas voter.", ephemeral=True)
            
        if user_id_str in self.votes:
            return await interaction.response.send_message("❌ Vous avez déjà voté.", ephemeral=True)
            
        weight = manager.shares.get(user_id_str, 0.0)
        name = await self.get_resolved_name(interaction.client, user_id_str)
        
        self.votes[user_id_str] = {
            'name': name,
            'weight': weight,
            'choice': choice
        }
        
        await self.update_message(interaction)


class VotesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="vote", description="Lance un vote d'Assemblée Générale (Poids proportionnel aux parts).")
    @app_commands.describe(question="La résolution ou la décision à voter")
    async def vote_cmd(self, ctx: commands.Context[Any], question: str):
        try:
            board = get_current_board_ids()
            if not board:
                await ctx.send("❌ La Cap Table est vide.")
                return
                
            view = VoteView(question, ctx.author.display_name, board)
            
            embed = discord.Embed(
                title="🗳️ Vote de l'Assemblée Générale",
                description=f"**Proposition initiée par {ctx.author.mention}**\n\n> {question}\n\n*Le poids de votre vote est proportionnel à vos parts dans l'entreprise. Le vote se termine lorsque tous les actionnaires ont répondu.*",
                color=0x805ad5
            )
            
            status_lines = [f"⏳ En attente : <@{m}>" for m in board]
            embed.add_field(name="Participation au vote", value="\n".join(status_lines), inline=False)
            
            await ctx.send(embed=embed, view=view)
        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}")

async def setup(bot):
    await bot.add_cog(VotesCog(bot))
