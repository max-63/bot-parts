import os
import tempfile
import discord
from fpdf import FPDF
from datetime import datetime
import hashlib
import json

class PDF(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 20)
        self.cell(0, 10, 'ONDURA SMART CONTRACTS', border=0, align='C')
        self.ln(10)
        self.set_font('helvetica', 'I', 10)
        self.cell(0, 10, 'Certificat Officiel de Cap Table', border=0, align='C')
        self.ln(15)

    def footer(self):
        self.set_y(-25)
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 5, f'Généré automatiquement le {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', align='C')
        self.ln()
        if hasattr(self, 'doc_hash'):
            self.set_font('helvetica', 'I', 6)
            self.cell(0, 5, f'SHA-256 Authenticity Hash: {self.doc_hash}', align='C')

def generate_certificate(contract_id: str, title: str, details_text: str, resolved_shares: dict) -> discord.File:
    # Génération du Hash SHA-256 pour l'authenticité
    timestamp = datetime.now().isoformat()
    raw_data = f"{contract_id}|{title}|{details_text}|{json.dumps(resolved_shares, sort_keys=True)}|{timestamp}"
    doc_hash = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()

    pdf = PDF()
    pdf.doc_hash = doc_hash
    pdf.add_page()
    
    # Titre du contrat
    pdf.set_font('helvetica', 'B', 16)
    pdf.cell(0, 10, f'Transaction ID: {contract_id}')
    pdf.ln(10)
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(43, 108, 176) # Bleu
    pdf.cell(0, 10, title)
    pdf.ln(10)
    pdf.set_text_color(0, 0, 0)
    
    # Détails
    pdf.set_font('helvetica', '', 12)
    pdf.multi_cell(0, 10, details_text)
    pdf.ln(10)
    
    # Cap Table
    pdf.set_font('helvetica', 'B', 14)
    pdf.cell(0, 10, 'Nouvelle Table de Capitalisation (Cap Table)')
    pdf.ln(10)
    
    # Table header
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(80, 10, 'Actionnaire', border=1)
    pdf.cell(40, 10, 'Parts (%)', border=1)
    pdf.cell(40, 10, 'Eq. Decimal', border=1)
    pdf.ln()
    
    # Table content
    pdf.set_font('helvetica', '', 12)
    total = 0.0
    for name, share in resolved_shares.items():
        pdf.cell(80, 10, name[:30], border=1)
        pdf.cell(40, 10, f"{share:.2f}%", border=1)
        pdf.cell(40, 10, f"{share/100.0:.4f}", border=1)
        pdf.ln()
        total += share
        
    # Table footer
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(80, 10, 'TOTAL', border=1)
    pdf.cell(40, 10, f"{total:.2f}%", border=1)
    pdf.cell(40, 10, f"{total/100.0:.4f}", border=1)
    pdf.ln()
    
    # Preuve cryptographique
    pdf.ln(15)
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(0, 5, 'Preuve Cryptographique Inviolable :')
    pdf.ln()
    pdf.set_font('helvetica', '', 8)
    pdf.multi_cell(0, 5, f'Ce document atteste de la transaction {contract_id}. La signature numérique ci-dessous permet de vérifier son intégrité.\nSignature: {doc_hash}')
    
    temp_path = os.path.join(tempfile.gettempdir(), f"cert_{contract_id}.pdf")
    pdf.output(temp_path)
    
    return discord.File(temp_path, filename=f"Certificat_{contract_id}.pdf")
