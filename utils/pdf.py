import os
import tempfile
import discord
from fpdf import FPDF
from datetime import datetime
import hashlib
import json

class PDF(FPDF):
    def header(self):
        # Bandeau supérieur
        self.set_fill_color(43, 108, 176) # Bleu corporate
        self.rect(0, 0, 210, 30, 'F')
        
        self.set_y(10)
        self.set_text_color(255, 255, 255)
        self.set_font('helvetica', 'B', 24)
        self.cell(0, 10, 'ONDURA SMART CONTRACTS', border=0, align='C')
        self.ln(15)
        
    def footer(self):
        self.set_y(-30)
        self.set_text_color(100, 100, 100)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 5, f'Certificat généré automatiquement le {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', align='C')
        self.ln()

def generate_certificate(contract_id: str, title: str, details_text: str, resolved_shares: dict):
    pdf = PDF()
    pdf.add_page()
    
    pdf.ln(10)
    # Titre du document
    pdf.set_font('helvetica', 'B', 20)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "CERTIFICAT D'ÉQUITÉ", align='C')
    pdf.ln(15)
    
    # Boîte d'informations du contrat
    pdf.set_fill_color(245, 245, 245)
    pdf.set_draw_color(200, 200, 200)
    pdf.rect(10, pdf.get_y(), 190, 45, 'DF')
    
    pdf.set_y(pdf.get_y() + 5)
    pdf.set_x(15)
    pdf.set_font('helvetica', 'B', 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f'ID CONTRAT : {contract_id}')
    pdf.ln(10)
    
    pdf.set_x(15)
    pdf.set_font('helvetica', 'B', 16)
    pdf.set_text_color(43, 108, 176)
    pdf.cell(0, 8, title)
    pdf.ln(10)
    
    pdf.set_x(15)
    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(50, 50, 50)
    pdf.multi_cell(180, 8, details_text)
    
    pdf.ln(20)
    
    # Titre de la Cap Table
    pdf.set_font('helvetica', 'B', 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, 'Table de Capitalisation (Post-Transaction)')
    pdf.ln(10)
    
    # Tableau - En-tête
    pdf.set_fill_color(43, 108, 176)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('helvetica', 'B', 12)
    pdf.set_draw_color(43, 108, 176)
    pdf.cell(100, 12, ' Actionnaire', border=1, fill=True)
    pdf.cell(45, 12, ' Parts (%)', border=1, align='C', fill=True)
    pdf.cell(45, 12, ' Équivalent', border=1, align='C', fill=True)
    pdf.ln()
    
    # Tableau - Contenu
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('helvetica', '', 12)
    
    fill = False
    total = 0.0
    for name, share in resolved_shares.items():
        if fill:
            pdf.set_fill_color(245, 245, 245)
        else:
            pdf.set_fill_color(255, 255, 255)
            
        pdf.cell(100, 12, f" {name[:40]}", border=1, fill=fill)
        pdf.cell(45, 12, f" {share:.2f}%", border=1, align='C', fill=fill)
        pdf.cell(45, 12, f" {share/100.0:.4f}", border=1, align='C', fill=fill)
        pdf.ln()
        fill = not fill
        total += share
        
    # Tableau - Pied
    pdf.set_font('helvetica', 'B', 12)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(100, 12, ' TOTAL', border=1, fill=True)
    pdf.cell(45, 12, f" {total:.2f}%", border=1, align='C', fill=True)
    pdf.cell(45, 12, f" {total/100.0:.4f}", border=1, align='C', fill=True)
    pdf.ln()
    
    # Sceau de validation
    pdf.ln(15)
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(39, 174, 96) # Vert
    pdf.cell(0, 10, "*** TRANSACTION VALIDEE PAR LE CONSEIL D'ADMINISTRATION ***", align='C')
    
    temp_path = os.path.join(tempfile.gettempdir(), f"cert_{contract_id}.pdf")
    pdf.output(temp_path)
    
    with open(temp_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    
    return discord.File(temp_path, filename=f"Certificat_{contract_id}.pdf"), file_hash

def generate_history_pdf(history_logs: list):
    pdf = PDF()
    pdf.add_page()
    
    pdf.ln(10)
    pdf.set_font('helvetica', 'B', 16)
    pdf.cell(0, 10, "REGISTRE OFFICIEL DES TRANSACTIONS", align='C')
    pdf.ln(15)
    
    pdf.set_font('helvetica', '', 10)
    
    for entry in history_logs:
        date_str = datetime.fromisoformat(entry['timestamp']).strftime('%Y-%m-%d %H:%M')
        pdf.set_font('helvetica', 'B', 11)
        pdf.cell(0, 8, f"[{entry['type']}] ID: {entry['id']} - {date_str}", ln=True)
        
        pdf.set_font('helvetica', '', 10)
        pdf.multi_cell(0, 6, f"Action : {entry['details']}\nExécuteur : {entry['executor']}")
        pdf.ln(5)
        
    pdf.ln(10)
    pdf.set_font('helvetica', 'I', 8)
    pdf.cell(0, 5, f'Généré automatiquement le {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', align='C')
    
    temp_path = os.path.join(tempfile.gettempdir(), "Historique_CapTable.pdf")
    pdf.output(temp_path)
    
    return discord.File(temp_path, filename="Historique_CapTable.pdf")
