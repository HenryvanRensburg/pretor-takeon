from fpdf import FPDF
from datetime import datetime
import os
from utils import clean_text

def add_logo_to_pdf(pdf):
    if os.path.exists("pretor_logo.png"):
        pdf.image("pretor_logo.png", 10, 8, 40)
        pdf.ln(15)

def generate_appointment_pdf(building_name, request_df, agent_name, take_on_date, year_end, building_code):
    pdf = FPDF()
    pdf.add_page()
    add_logo_to_pdf(pdf)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, txt=clean_text(f"RE: {building_name} - APPOINTMENT AS MANAGING AGENT"), ln=1)
    pdf.ln(5)
    pdf.set_font("Arial", size=10)
    intro = (f"ATTENTION: {agent_name}\n\n"
             f"We confirm that we have been appointed as Managing Agents of {building_name} effective from {take_on_date}.\n"
             f"In terms of this appointment, we request you to make all documentation in your possession pertaining to "
             f"{building_name} available for collection by us.")
    pdf.multi_cell(0, 5, clean_text(intro))
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, "REQUIRED DOCUMENTATION:", ln=1)
    pdf.set_font("Arial", size=9)
    
    preferred_order = ["Take-On", "Financial", "Legal", "Statutory Compliance", "Building Compliance", "Insurance", "City Council", "Employee", "General"]
    
    if 'Task Heading' in request_df.columns:
        unique_headings = request_df['Task Heading'].unique().tolist()
        unique_headings.sort(key=lambda x: preferred_order.index(x) if x in preferred_order else 99)
        for heading in unique_headings:
            if not heading: continue
            pdf.set_font("Arial", 'B', 9)
            pdf.ln(2)
            pdf.cell(0, 6, clean_text(str(heading).upper()), ln=1)
            pdf.set_font("Arial", size=9)
            section_items = request_df[request_df['Task Heading'] == heading]
            for _, row in section_items.iterrows():
                pdf.cell(5, 5, "-", ln=0)
                pdf.multi_cell(0, 5, clean_text(str(row['Task Name'])))
    else:
        for _, row in request_df.iterrows():
            pdf.cell(5, 5, "-", ln=0)
            pdf.multi_cell(0, 5, clean_text(str(row['Task Name'])))
            
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, "BANKING DETAILS FOR TRANSFER OF FUNDS:", ln=1)
    pdf.set_font("Arial", size=9)
    banking_info = (f"Account Name: Pretor Group (Pty) Ltd\nBank: First National Bank\nBranch: Pretoria (251445)\n"
                    f"Account Number: 514 242 794 08\nReference: S{building_code}12005X")
    pdf.multi_cell(0, 5, clean_text(banking_info))
    pdf.ln(5)
    pdf.cell(0, 5, "Your co-operation regarding the above will be appreciated.", ln=1)
    pdf.cell(0, 5, "Yours faithfully,", ln=1)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 5, "PRETOR GROUP", ln=1)
    filename = clean_text(f"{building_name}_Handover_Request.pdf")
    pdf.output(filename)
    return filename

def generate_report_pdf(building_name, items_df, providers_df, title):
    pdf = FPDF()
    pdf.add_page()
    add_logo_to_pdf(pdf)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt=clean_text(f"{title}: {building_name}"), ln=1, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "1. Take-On Checklist", ln=1)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(80, 10, "Item", 1)
    pdf.cell(30, 10, "Status", 1)
    pdf.cell(40, 10, "Action By", 1)
    pdf.cell(40, 10, "Notes", 1)
    pdf.ln()
    pdf.set_font("Arial", size=9)
    for _, row in items_df.iterrows():
        status = "Received" if row['Received'] else "Pending"
        pdf.cell(80, 10, clean_text(str(row['Task Name'])[:40]), 1)
        pdf.cell(30, 10, status, 1)
        pdf.cell(40, 10, clean_text(str(row['Responsibility'])[:20]), 1)
        pdf.cell(40, 10, clean_text(str(row['Notes'])[:20]), 1)
        pdf.ln()
    filename = clean_text(f"{building_name}_Report.pdf")
    pdf.output(filename)
    return filename

def generate_weekly_report_pdf(summary_list):
    pdf = FPDF()
    pdf.add_page()
    add_logo_to_pdf(pdf)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt="Weekly Take-On Overview", ln=1, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(60, 10, "Complex Name", 1)
    pdf.cell(40, 10, "Manager", 1)
    pdf.cell(30, 10, "Status", 1)
    pdf.cell(20, 10, "Prog.", 1)
    pdf.cell(40, 10, "Pending Items", 1)
    pdf.ln()
    pdf.set_font("Arial", size=9)
    for item in summary_list:
        pdf.cell(60, 10, clean_text(str(item['Complex Name'])[:25]), 1)
        pdf.cell(40, 10, clean_text(str(item['Manager'])[:18]), 1)
        pdf.cell(30, 10, clean_text(item['Status'])[:15], 1)
        pdf.cell(20, 10, f"{int(item['Progress']*100)}%", 1)
        pdf.cell(40, 10, str(item['Items Pending']), 1)
        pdf.ln()
    filename = f"Weekly_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
    pdf.output(filename)
    return filename
