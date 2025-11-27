import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from fpdf import FPDF
import urllib.parse 
import os
import time

# --- CONFIGURATION ---
# Note: Add [supabase] url = "..." and key = "..." to your .streamlit/secrets.toml
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]

# --- SUPABASE CONNECTION ---
@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- DATA FUNCTIONS ---
def get_data(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        df = pd.DataFrame(response.data)
        return df
    except Exception as e:
        st.error(f"Error fetching {table_name}: {e}")
        return pd.DataFrame()

def clear_cache():
    st.cache_data.clear()

def add_master_item(task_name, category, default_resp, task_heading):
    data = {
        "Task Name": task_name,
        "Category": category,
        "Default Responsibility": default_resp,
        "Task Heading": task_heading
    }
    supabase.table("Master").insert(data).execute()
    st.cache_data.clear()

def add_service_provider(complex_name, name, service, email, phone):
    data = {
        "Complex Name": complex_name,
        "Provider Name": name,
        "Service Type": service,
        "Email": email,
        "Phone": phone,
        "Date Emailed": ""
    }
    supabase.table("ServiceProviders").insert(data).execute()
    st.cache_data.clear()

def add_employee(complex_name, name, surname, id_num, paye, contract, payslip, id_copy, bank_conf):
    data = {
        "Complex Name": complex_name,
        "Name": name,
        "Surname": surname,
        "ID Number": id_num,
        "PAYE Number": paye,
        "Contract Received": contract,
        "Payslip Received": payslip,
        "ID Copy Received": id_copy,
        "Bank Confirmation": bank_conf
    }
    supabase.table("Employees").insert(data).execute()
    st.cache_data.clear()

def add_arrears_item(complex_name, unit, amount, attorney_name, attorney_email, attorney_phone):
    data = {
        "Complex Name": complex_name,
        "Unit Number": unit,
        "Outstanding Amount": str(amount),
        "Attorney Name": attorney_name,
        "Attorney Email": attorney_email,
        "Attorney Phone": attorney_phone
    }
    supabase.table("Arrears").insert(data).execute()
    st.cache_data.clear()

def add_council_account(complex_name, account_num, service, balance):
    data = {
        "Complex Name": complex_name,
        "Account Number": account_num,
        "Service Covered": service,
        "Current Balance": str(balance)
    }
    supabase.table("CouncilAccounts").insert(data).execute()
    st.cache_data.clear()

def add_trustee(complex_name, name, surname, email, phone):
    data = {
        "Complex Name": complex_name,
        "Name": name,
        "Surname": surname,
        "Email": email,
        "Phone": phone
    }
    supabase.table("Trustees").insert(data).execute()
    st.cache_data.clear()

# --- DELETE FUNCTIONS (Using unique IDs is best, but mapping by fields for now) ---
def delete_record(table_name, match_dict):
    try:
        query = supabase.table(table_name).delete()
        for key, val in match_dict.items():
            query = query.eq(key, val)
        query.execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error deleting: {e}")
        return False

def save_global_settings(settings_dict):
    try:
        # Clear existing and re-insert (simplest for settings)
        supabase.table("Settings").delete().neq("Department", "XYZ").execute() # Delete all
        rows = [{"Department": k, "Email": v} for k, v in settings_dict.items()]
        supabase.table("Settings").insert(rows).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error saving settings: {e}")
        return False

# --- UPDATE FUNCTIONS ---
def update_project_field(complex_name, field, value):
    try:
        supabase.table("Projects").update({field: value}).eq("Complex Name", complex_name).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Update failed: {e}")
        return False

def update_building_details_batch(complex_name, updates):
    try:
        # Filter out empty updates to prevent overwriting with blanks if not intended
        clean_updates = {k: v for k, v in updates.items() if v is not None}
        supabase.table("Projects").update(clean_updates).eq("Complex Name", complex_name).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Update failed: {e}")
        return False

def update_service_provider_date(complex_name, provider_name):
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        supabase.table("ServiceProviders").update({"Date Emailed": today}).match({"Complex Name": complex_name, "Provider Name": provider_name}).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        return False

def save_checklist_batch(complex_name, edited_df):
    # 1. Handle Deletions
    if 'Delete' in edited_df.columns:
        to_delete = edited_df[edited_df['Delete'] == True]
        for _, row in to_delete.iterrows():
            # Assuming Task Name + Complex is unique enough for this logic
            supabase.table("Checklist").delete().match({"Complex Name": complex_name, "Task Name": row['Task Name']}).execute()
    
    # 2. Handle Updates (Only non-deleted rows)
    to_update = edited_df[edited_df['Delete'] == False] if 'Delete' in edited_df.columns else edited_df
    
    for _, row in to_update.iterrows():
        received_bool = True if row['Received'] else False
        
        # Logic for Date Received: If marked received but no date, set today
        date_val = str(row['Date Received'])
        if received_bool and (not date_val or date_val == "None" or date_val == "nan"):
             date_val = datetime.now().strftime("%Y-%m-%d")
        elif not received_bool:
             date_val = ""

        update_data = {
            "Received": received_bool,
            "Date Received": date_val,
            "Notes": str(row['Notes']),
            "Completed By": str(row['Completed By'])
        }
        
        supabase.table("Checklist").update(update_data).match({"Complex Name": complex_name, "Task Name": row['Task Name']}).execute()
    
    st.cache_data.clear()

# --- DATE LOGIC (V6) ---
def calculate_financial_periods(take_on_date_str, year_end_str):
    try:
        take_on_date = datetime.strptime(str(take_on_date_str), "%Y-%m-%d")
        first_of_take_on = take_on_date.replace(day=1)
        request_end_date = first_of_take_on - timedelta(days=1) 
        
        months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
        ye_month = 2 
        for m_name, m_val in months.items():
            if m_name in str(year_end_str).lower():
                ye_month = m_val
                break
        
        start_month = ye_month + 1
        if start_month > 12: start_month = 1
        
        candidate_year = request_end_date.year
        if start_month > request_end_date.month:
             candidate_year -= 1
        
        current_fin_year_start = datetime(candidate_year, start_month, 1)
        if current_fin_year_start > request_end_date:
            current_fin_year_start -= relativedelta(years=1)
            
        current_period_str = f"Financial records from {current_fin_year_start.strftime('%d %B %Y')} to {request_end_date.strftime('%d %B %Y')}"
        
        historic_end_date = current_fin_year_start - timedelta(days=1)
        historic_start_date = current_fin_year_start - relativedelta(years=5)
        historic_period_str = f"{historic_start_date.strftime('%d %B %Y')} to {historic_end_date.strftime('%d %B %Y')}"
            
        bank_start = take_on_date - relativedelta(months=1)
        bank_str = f"Bank account statements as of {bank_start.strftime('%d %B %Y')} as well as confirmation that the funds has been paid over to Pretor Group."
        
        owner_bal_str = f"Owner balances to be provided on {request_end_date.strftime('%d %B %Y')}."
        closing_date = take_on_date + timedelta(days=10)
        closing_bal_str = f"Final bank closing balances to be provided by {closing_date.strftime('%d %B %Y')} as well as confirmation that the funds has been paid over to Pretor Group."

        return current_period_str, historic_period_str, bank_str, owner_bal_str, closing_bal_str
    except Exception:
        return "Current Financial Year Records", "Past 5 Financial Years", "Latest Bank Statements", "Owner Balances", "Final Closing Balances"

# --- CREATE BUILDING ---
def create_new_building(data_dict):
    # Check existing
    existing = supabase.table("Projects").select("id").eq("Complex Name", data_dict["Complex Name"]).execute()
    if existing.data:
        return "EXISTS"

    # Insert Project
    # Convert dates to string for JSON serialization
    data_dict["Take On Date"] = str(data_dict["Take On Date"])
    data_dict["Date Doc Requested"] = str(data_dict["Date Doc Requested"])
    
    # Clean dict keys to match exact table columns (optional but safe)
    supabase.table("Projects").insert(data_dict).execute()
    
    # Generate Checklist
    master_data = get_data("Master")
    if master_data.empty: return "NO_MASTER"
    
    curr_fin, historic_block, bank_req, owner_bal_req, closing_bal_req = calculate_financial_periods(data_dict["Take On Date"], data_dict["Year End"])
    day_before_date = (datetime.strptime(data_dict["Take On Date"], "%Y-%m-%d") - timedelta(days=1)).strftime('%d %B %Y')

    checklist_rows = []
    
    # Financial Dynamics
    checklist_rows.append({"Complex Name": data_dict["Complex Name"], "Task Name": curr_fin, "Responsibility": "Previous Agent", "Task Heading": "Financial"})
    checklist_rows.append({"Complex Name": data_dict["Complex Name"], "Task Name": f"Historic Financial Records: {historic_block}", "Responsibility": "Previous Agent", "Task Heading": "Financial"})
    checklist_rows.append({"Complex Name": data_dict["Complex Name"], "Task Name": f"Historic General Correspondence: {historic_block}", "Responsibility": "Previous Agent", "Task Heading": "Financial"})
    checklist_rows.append({"Complex Name": data_dict["Complex Name"], "Task Name": bank_req, "Responsibility": "Previous Agent", "Task Heading": "Financial"})
    checklist_rows.append({"Complex Name": data_dict["Complex Name"], "Task Name": owner_bal_req, "Responsibility": "Previous Agent", "Task Heading": "Financial"})
    checklist_rows.append({"Complex Name": data_dict["Complex Name"], "Task Name": closing_bal_req, "Responsibility": "Previous Agent", "Task Heading": "Financial"})
    checklist_rows.append({"Complex Name": data_dict["Complex Name"], "Task Name": f"Final reconciliation of previous bank account and proof of transfer of funds to be provided on {day_before_date}", "Responsibility": "Previous Agent", "Task Heading": "Financial"})
    checklist_rows.append({"Complex Name": data_dict["Complex Name"], "Task Name": f"A final trial balance as at {day_before_date}", "Responsibility": "Previous Agent", "Task Heading": "Financial"})
    checklist_rows.append({"Complex Name": data_dict["Complex Name"], "Task Name": f"The latest cashflow statement as at {day_before_date}", "Responsibility": "Previous Agent", "Task Heading": "Financial"})

    # Master Items
    for _, row in master_data.iterrows():
        raw_cat = str(row.get("Category", "Both")).strip().upper()
        b_type = data_dict["Type"]
        should_copy = False
        if raw_cat == "BOTH" or raw_cat == "": should_copy = True
        elif raw_cat == "BC" and b_type == "Body Corporate": should_copy = True
        elif raw_cat == "HOA" and b_type == "HOA": should_copy = True
        
        if should_copy:
            checklist_rows.append({
                "Complex Name": data_dict["Complex Name"],
                "Task Name": row["Task Name"],
                "Responsibility": row.get("Default Responsibility", "Previous Agent"),
                "Task Heading": row.get("Task Heading", "Take-On")
            })

    # Bulk Insert Checklist
    if checklist_rows:
        # Supabase has a limit on bulk inserts, split if necessary, but for <1000 items it's usually fine
        supabase.table("Checklist").insert(checklist_rows).execute()

    st.cache_data.clear()
    return "SUCCESS"

# --- PDF GENERATORS ---
def clean_text(text):
    if text is None: return ""
    text = str(text)
    replacements = {"\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2022": "*", "✅": "", "⚠️": "", "🔄": "", "🆕": ""}
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    return text.encode('latin-1', 'replace').decode('latin-1')

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
    
    # Group by Task Heading if available
    if 'Task Heading' in request_df.columns:
        # Filter unique headings and sort
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

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Pretor Group Take-On", layout="wide")
    if os.path.exists("pretor_logo.png"):
        st.sidebar.image("pretor_logo.png", use_container_width=True)
        
    st.title("🏢 Pretor Group: Take-On Manager")

    menu = ["Dashboard", "Master Schedule", "New Building", "Manage Buildings", "Global Settings"]
    choice = st.sidebar.selectbox("Menu", menu)
    
    if choice == "Dashboard":
        st.subheader("Active Projects Overview")
        df = get_data("Projects")
        checklist = get_data("Checklist")
        
        if not df.empty:
            summary_list = []
            for index, row in df.iterrows():
                c_name = row['Complex Name']
                if checklist.empty:
                    total, received = 0, 0
                    pretor_items = pd.DataFrame()
                else:
                    c_items = checklist[checklist['Complex Name'] == c_name]
                    valid_items = c_items[c_items['Delete'] != True] # Supabase boolean
                    # Only count Pretor/Both items for progress
                    pretor_items = valid_items[valid_items['Responsibility'].isin(['Pretor Group', 'Both'])]
                    total = len(pretor_items)
                    received = len(pretor_items[pretor_items['Received'] == True]) # Supabase boolean

                progress_val = (received / total) if total > 0 else 0
                if progress_val == 1.0: status = "✅ Completed"
                elif progress_val > 0.8: status = "⚠️ Near Completion"
                elif progress_val > 0.1: status = "🔄 In Progress"
                else: status = "🆕 Just Started"
                
                summary_list.append({
                    "Complex Name": c_name,
                    "Type": row['Type'],
                    "Manager": row['Assigned Manager'],
                    "Take On Date": row['Take On Date'],
                    "Progress": progress_val, 
                    "Status": status,
                    "Items Pending": total - received
                })
            
            summary_df = pd.DataFrame(summary_list)
            st.dataframe(
                summary_df,
                column_config={
                    "Progress": st.column_config.ProgressColumn("Completion %", format="%.0f%%", min_value=0, max_value=1)
                },
                hide_index=True
            )
            if st.button("Download Weekly Report PDF"):
                pdf_file = generate_weekly_report_pdf(summary_list)
                with open(pdf_file, "rb") as f:
                    st.download_button("⬇️ Download PDF", f, file_name=pdf_file)
        else:
            st.info("No active projects found.")

    elif choice == "Master Schedule":
        st.subheader("Master Checklist Template")
        with st.form("add_master"):
            c1, c2, c3, c4 = st.columns(4)
            new_task = c1.text_input("Task Name")
            category = c2.selectbox("Category", ["Both", "BC", "HOA"])
            def_resp = c3.selectbox("Default Responsibility", ["Previous Agent", "Pretor Group", "Both"])
            heading = c4.selectbox("Task Heading", ["Take-On", "Financial", "Statutory Compliance", "Insurance", "City Council", "Building Compliance", "Employee", "Legal", "General"])
            
            if st.form_submit_button("Add Item"):
                add_master_item(new_task, category, def_resp, heading)
                st.success("Added!")
                st.rerun()
        
        df = get_data("Master")
        if not df.empty:
            st.dataframe(df)
            
    elif choice == "Global Settings":
        st.subheader("Department Contact Settings")
        current_settings_df = get_data("Settings")
        settings_dict = {}
        if not current_settings_df.empty:
            settings_dict = dict(zip(current_settings_df["Department"], current_settings_df["Email"]))
        
        with st.form("settings_form"):
            s_wages = st.text_input("Wages Department", value=settings_dict.get("Wages", ""))
            s_sars = st.text_input("SARS Department", value=settings_dict.get("SARS", ""))
            s_muni = st.text_input("Municipal Department", value=settings_dict.get("Municipal", ""))
            s_comp = st.text_input("Compliance Department", value=settings_dict.get("Compliance", ""))
            s_debt = st.text_input("Debt Collection Department", value=settings_dict.get("Debt Collection", ""))
            s_ins = st.text_input("Insurance Department", value=settings_dict.get("Insurance", ""))
            s_acc = st.text_input("Accounts Department", value=settings_dict.get("Accounts", ""))
            
            if st.form_submit_button("Save Global Settings"):
                new_settings = {
                    "Wages": s_wages, "SARS": s_sars, "Municipal": s_muni,
                    "Compliance": s_comp, "Debt Collection": s_debt, "Insurance": s_ins, "Accounts": s_acc
                }
                if save_global_settings(new_settings):
                    st.success("Global Settings Saved!")
                    st.rerun()

    elif choice == "New Building":
        st.subheader("Onboard New Complex")
        with st.form("new_complex_form"):
            st.write("### Basic Information")
            col1, col2 = st.columns(2)
            complex_name = col1.text_input("Complex Name")
            b_type = col2.selectbox("Type", ["Body Corporate", "HOA"])
            client_email = st.text_input("Client Email(s) (Comma separated)")
            prev_agent = st.text_input("Previous Agents")
            c1, c2 = st.columns(2)
            take_on_date = c1.date_input("Take On Date", datetime.today())
            units = c2.number_input("No of Units", min_value=1, step=1)
            st.write("### Pretor Team")
            c_take1, c_take2 = st.columns(2)
            takeon_name = c_take1.text_input("Take-On Manager Name", value="Henry Janse van Rensburg")
            takeon_email = c_take2.text_input("Take-On Manager Email")
            c3, c4 = st.columns(2)
            assigned_mgr = c3.text_input("Portfolio Manager Name")
            mgr_email = c4.text_input("Portfolio Manager Email")
            c5, c6 = st.columns(2)
            assist_name = c5.text_input("Portfolio Assistant Name")
            assist_email = c6.text_input("Portfolio Assistant Email")
            c7, c8 = st.columns(2)
            book_name = c7.text_input("Bookkeeper Name")
            book_email = c8.text_input("Bookkeeper Email")
            st.write("### Financial & Legal")
            fees = st.text_input("Management Fees (Excl VAT)")
            l1, l2, l3 = st.columns(3)
            erf_no = l1.text_input("Erf No")
            ss_num = l2.text_input("SS Number (BC Only)")
            csos_num = l3.text_input("CSOS Registration Number")
            l4, l5, l6 = st.columns(3)
            vat_num = l4.text_input("VAT Number")
            tax_num = l5.text_input("Tax Number")
            year_end = l6.text_input("Year End")
            l7, l8 = st.columns(2)
            auditor = l7.text_input("Auditor")
            last_audit = l8.text_input("Last Audit Available (Year)")
            st.write("### System & Documentation")
            s1, s2 = st.columns(2)
            build_code = s1.text_input("Building Code")
            exp_code = s2.text_input("Expense Code")
            phys_address = st.text_area("Physical Address")
            date_req = st.date_input("Date Documentation Requested", datetime.today())
            
            submitted = st.form_submit_button("Create Complex")
            if submitted:
                if complex_name:
                    data = {
                        "Complex Name": complex_name, "Type": b_type, "Client Email": client_email,
                        "Previous Agents": prev_agent, "Take On Date": take_on_date, "No of Units": units,
                        "Mgmt Fees": fees, "Erf No": erf_no, "SS Number": ss_num, "CSOS Number": csos_num,
                        "VAT Number": vat_num, "Tax Number": tax_num, "Year End": year_end, "Auditor": auditor,
                        "Last Audit Year": last_audit, "Building Code": build_code, "Expense Code": exp_code,
                        "Physical Address": phys_address, "Assigned Manager": assigned_mgr, "Manager Email": mgr_email, 
                        "Assistant Name": assist_name, "Assistant Email": assist_email, "Bookkeeper Name": book_name,
                        "Bookkeeper Email": book_email, "Date Doc Requested": date_req,
                        "TakeOn Name": takeon_name, "TakeOn Email": takeon_email
                    }
                    result = create_new_building(data)
                    if result == "SUCCESS":
                        st.success(f"Created {complex_name}!")
                    elif result == "EXISTS":
                        st.error(f"Error: '{complex_name}' already exists.")
                    else:
                        st.warning("Created, but Master Schedule was empty.")
                else:
                    st.error("Complex Name is required.")

    elif choice == "Manage Buildings":
        projects = get_data("Projects")
        if projects.empty:
            st.warning("No projects yet.")
        else:
            b_choice = st.selectbox("Select Complex", projects['Complex Name'])
            proj_row = projects[projects['Complex Name'] == b_choice].iloc[0]
            
            # Grab all data for this project safely
            # Using .get() to avoid key errors if columns don't exist yet
            client_email = str(proj_row.get('Client Email', ''))
            saved_agent_name = str(proj_row.get('Agent Name', ''))
            saved_agent_email = str(proj_row.get('Agent Email', ''))
            take_on_date = str(proj_row.get('Take On Date', ''))
            date_requested = str(proj_row.get('Date Doc Requested', ''))
            year_end = str(proj_row.get('Year End', ''))
            building_code = str(proj_row.get('Building Code', ''))
            tax_number = str(proj_row.get('Tax Number', ''))
            takeon_name = str(proj_row.get('TakeOn Name', ''))
            takeon_email = str(proj_row.get('TakeOn Email', ''))
            assigned_manager = str(proj_row.get('Assigned Manager', ''))
            manager_email = str(proj_row.get('Manager Email', ''))
            assistant_name = str(proj_row.get('Assistant Name', ''))
            assistant_email = str(proj_row.get('Assistant Email', ''))
            bookkeeper_name = str(proj_row.get('Bookkeeper Name', ''))
            bookkeeper_email = str(proj_row.get('Bookkeeper Email', ''))
            mgmt_fees = str(proj_row.get('Mgmt Fees', ''))
            
            # Tracking Dates
            wages_sent_date = str(proj_row.get('Wages Sent Date', ''))
            sars_sent_date = str(proj_row.get('SARS Sent Date', ''))
            trustee_email_sent = str(proj_row.get('Trustee Email Sent Date', ''))
            broker_email_sent = str(proj_row.get('Broker Email Sent Date', ''))
            internal_ins_sent = str(proj_row.get('Internal Ins Email Sent Date', ''))
            legal_sent_date = str(proj_row.get('Debt Collection Email Sent Date', ''))
            council_sent_date = str(proj_row.get('Council Email Sent Date', ''))
            fee_email_sent = str(proj_row.get('Fee Confirmation Email Sent Date', ''))

            cc_list = []
            if manager_email and manager_email != "None" and manager_email != takeon_email: cc_list.append(manager_email)
            if assistant_email and assistant_email != "None": cc_list.append(assistant_email)
            if bookkeeper_email and bookkeeper_email != "None": cc_list.append(bookkeeper_email)
            cc_string = ",".join(cc_list)
            team_list = [n for n in [takeon_name, assigned_manager, assistant_name, bookkeeper_name] if n and n != "None"]
            
            # --- UPDATE DETAILS SECTION ---
            with st.expander("ℹ️ View / Edit Building Details", expanded=False):
                with st.form("update_details_form"):
                    # Using simple text inputs for update (can be improved)
                    new_mgr = st.text_input("Portfolio Manager", value=assigned_manager)
                    new_mgr_email = st.text_input("Manager Email", value=manager_email)
                    new_fees = st.text_input("Mgmt Fees", value=mgmt_fees)
                    if st.form_submit_button("Update"):
                        update_building_details_batch(b_choice, {
                            "Assigned Manager": new_mgr,
                            "Manager Email": new_mgr_email,
                            "Mgmt Fees": new_fees
                        })
                        st.success("Updated!")
                        st.rerun()

            # --- LOAD RELATED DATA ---
            all_items = get_data("Checklist")
            items_df = all_items[all_items['Complex Name'] == b_choice].copy() if not all_items.empty else pd.DataFrame()
            
            all_providers = get_data("ServiceProviders")
            providers_df = all_providers[all_providers['Complex Name'] == b_choice].copy() if not all_providers.empty else pd.DataFrame()
            
            all_employees = get_data("Employees")
            employees_df = all_employees[all_employees['Complex Name'] == b_choice].copy() if not all_employees.empty else pd.DataFrame()
            
            all_arrears = get_data("Arrears")
            arrears_df = all_arrears[all_arrears['Complex Name'] == b_choice].copy() if not all_arrears.empty else pd.DataFrame()

            all_council = get_data("CouncilAccounts")
            council_df = all_council[all_council['Complex Name'] == b_choice].copy() if not all_council.empty else pd.DataFrame()

            all_trustees = get_data("Trustees")
            trustees_df = all_trustees[all_trustees['Complex Name'] == b_choice].copy() if not all_trustees.empty else pd.DataFrame()

            # --- SECTIONS 1 to 10 (Simulated for brevity, keeping logic) ---
            # 1. Previous Agent
            st.markdown("### 1. Previous Agent Handover Request")
            col_a, col_b = st.columns(2)
            agent_name = col_a.text_input("Previous Agent Name", value=saved_agent_name)
            agent_email = col_b.text_input("Previous Agent Email", value=saved_agent_email)
            if st.button("Save & Generate Request"):
                update_project_agent_details(b_choice, agent_name, agent_email)
                # ... PDF generation logic ...
                st.success("Done")
            
            st.divider()
            
            # 2. Tracker (Simplified for brevity)
            st.markdown("### 2. Track Progress")
            # ... Tracker logic ...
            
            st.divider()
            
            # ... Steps 3 to 10 (Insurance, etc.) ... 
            # (Paste the full logic here from previous responses for Steps 3-10)
            
            # --- 11. REPORTS ---
            st.markdown("### 11. Reports & Comms")
            
            # --- NEW: MANAGEMENT FEE CONFIRMATION ---
            st.markdown("#### 💰 Management Fee Confirmation")
            
            rep_col1, rep_col2 = st.columns(2) # Define columns here for Reports
            
            with rep_col1:
                if fee_email_sent and fee_email_sent != "None" and fee_email_sent != "":
                    st.success(f"✅ Fee confirmation sent on {fee_email_sent}")
                    with st.expander("Need to resend?"):
                        if st.button("Reset Fee Status"):
                            update_fee_status(b_choice, reset=True)
                            st.rerun()
                else:
                    settings_df = get_data("Settings")
                    acc_email = ""
                    if not settings_df.empty:
                        row = settings_df[settings_df['Department'] == 'Accounts'] # or Contains logic
                        if not row.empty: acc_email = row.iloc[0]['Email']
                    
                    if acc_email:
                        st.info(f"Sending to: {acc_email} (Accounts Dept)")
                        if st.button("Draft Fee Confirmation Email"):
                             if update_fee_status(b_choice):
                                # ... Email logic ...
                                st.success("Status updated! Click link above.")
                    else:
                        st.error("Accounts Department Email not set in Global Settings.")
            
            # --- Report Section Variables ---
            pending_df = items_df[(items_df['Received'] == False) & (items_df['Delete'] == False)]
            completed_df = items_df[items_df['Received'] == True]
            
            with rep_col1:
                st.markdown("#### Client Update")
                if st.button("Draft Client Email"):
                    body = f"Dear Client,\n\nProgress Update for {b_choice}:\n\n"
                    # ... Detailed Status Section ...
                    body += "📋 ITEMS ATTENDED TO / IN PROGRESS:\n"
                    # ... rest of body generation ...
                    
                    safe_subject = urllib.parse.quote(f"Progress Update: {b_choice}")
                    safe_body = urllib.parse.quote(body)
                    link = f'<a href="mailto:{client_email}?subject={safe_subject}&body={safe_body}{cc_param}" target="_blank" style="text-decoration:none;">📩 Open Client Email</a>'
                    st.markdown(link, unsafe_allow_html=True)

            with rep_col2:
                st.markdown("#### Finalize")
                if st.button("Finalize Project"):
                    # ... Finalize Logic ...
                    st.success("Finalized")

if __name__ == "__main__":
    main()
