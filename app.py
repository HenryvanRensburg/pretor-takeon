import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from fpdf import FPDF
import urllib.parse 
import re

# --- CONFIGURATION ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# --- GOOGLE SHEETS CONNECTION ---
def get_google_sheet():
    try:
        credentials_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        sheet = client.open("Pretor TakeOn DB")
        return sheet
    except Exception as e:
        st.error(f"Connection Error. Please check Secrets. Details: {e}")
        return None

# --- DATA FUNCTIONS (WITH CACHING) ---
@st.cache_data(ttl=10) 
def get_data(worksheet_name):
    sh = get_google_sheet()
    if sh:
        try:
            worksheet = sh.worksheet(worksheet_name)
            data = worksheet.get_all_values()
            if not data: return pd.DataFrame()
            headers = data.pop(0)
            df = pd.DataFrame(data, columns=headers)
            df.columns = df.columns.str.strip()
            return df
        except Exception as e:
            if worksheet_name == "ServiceProviders":
                try:
                    return pd.DataFrame(columns=["Complex Name", "Provider Name", "Service Type", "Email", "Phone", "Date Emailed"])
                except:
                    return pd.DataFrame()
            return pd.DataFrame()
    return pd.DataFrame()

def clear_cache():
    st.cache_data.clear()

def add_master_item(task_name, category, default_resp):
    sh = get_google_sheet()
    ws = sh.worksheet("Master")
    ws.append_row([task_name, category, default_resp])
    clear_cache()

def add_service_provider(complex_name, name, service, email, phone):
    sh = get_google_sheet()
    ws = sh.worksheet("ServiceProviders")
    ws.append_row([complex_name, name, service, email, phone, ""])
    clear_cache()

def update_service_provider_date(complex_name, provider_name):
    sh = get_google_sheet()
    ws = sh.worksheet("ServiceProviders")
    try:
        cell_list = ws.findall(complex_name)
        target_row = None
        for cell in cell_list:
            if ws.cell(cell.row, 2).value == provider_name:
                target_row = cell.row
                break
        
        if target_row:
            today = datetime.now().strftime("%Y-%m-%d")
            ws.update_cell(target_row, 6, today) 
            clear_cache()
            return True
    except Exception as e:
        st.error(f"Error updating provider date: {e}")
    return False

def calculate_financial_periods(take_on_date_str, year_end_str):
    try:
        take_on_date = datetime.strptime(take_on_date_str, "%Y-%m-%d")
        months = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        ye_month = 2 
        for m_name, m_val in months.items():
            if m_name in str(year_end_str).lower():
                ye_month = m_val
                break
        
        current_fin_year_start = take_on_date.replace(day=1, month=ye_month) + relativedelta(days=1)
        if current_fin_year_start > take_on_date:
            current_fin_year_start -= relativedelta(years=1)
            
        current_period_str = f"Financial records from {current_fin_year_start.strftime('%d %B %Y')} to {take_on_date.strftime('%d %B %Y')}"
        
        past_years = []
        for i in range(1, 6):
            y_end = current_fin_year_start - relativedelta(days=1) - relativedelta(years=i-1)
            past_years.append(f"Financial Year Ending: {y_end.strftime('%d %B %Y')}")
            
        bank_start = take_on_date - relativedelta(months=1)
        bank_str = f"Bank statements from {bank_start.strftime('%d %B %Y')} to date."
        
        return current_period_str, past_years, bank_str
    except Exception as e:
        return "Current Financial Year Records", ["Past 5 Financial Years"], "Latest Bank Statements"

def create_new_building(data_dict):
    sh = get_google_sheet()
    ws_projects = sh.worksheet("Projects")
    
    existing_names = ws_projects.col_values(1)
    if data_dict["Complex Name"] in existing_names:
        return "EXISTS"

    row_data = [
        data_dict["Complex Name"],
        data_dict["Type"],
        data_dict["Previous Agents"],
        str(data_dict["Take On Date"]),
        data_dict["No of Units"],
        data_dict["Mgmt Fees"],
        data_dict["Erf No"],
        data_dict["SS Number"],
        data_dict["CSOS Number"],
        data_dict["VAT Number"],
        data_dict["Tax Number"],
        data_dict["Year End"],
        data_dict["Auditor"],
        data_dict["Last Audit Year"],
        data_dict["Building Code"],
        data_dict["Expense Code"],
        data_dict["Physical Address"],
        data_dict["Assigned Manager"],
        str(data_dict["Date Doc Requested"]),
        "", 
        data_dict["Client Email"],
        "FALSE", 
        "", 
        "", 
        "",
        data_dict["Manager Email"],
        data_dict["Assistant Name"],
        data_dict["Assistant Email"],
        data_dict["Bookkeeper Name"],
        data_dict["Bookkeeper Email"]
    ]
    ws_projects.append_row(row_data)
    
    ws_master = sh.worksheet("Master")
    raw_master = ws_master.get_all_values()
    if not raw_master: return False
    headers = raw_master.pop(0)
    master_data = [dict(zip(headers, row)) for row in raw_master]
    
    b_type = data_dict["Type"] 
    ws_checklist = sh.worksheet("Checklist")
    new_rows = []
    
    curr_fin, past_years, bank_req = calculate_financial_periods(str(data_dict["Take On Date"]), data_dict["Year End"])
    
    new_rows.append([data_dict["Complex Name"], curr_fin, "FALSE", "", "", "Previous Agent", "FALSE", ""])
    for p_year in past_years:
        new_rows.append([data_dict["Complex Name"], f"Historic Records: {p_year}", "FALSE", "", "", "Previous Agent", "FALSE", ""])
    new_rows.append([data_dict["Complex Name"], bank_req, "FALSE", "", "", "Previous Agent", "FALSE", ""])

    for item in master_data:
        raw_cat = str(item.get("Category", "Both")).strip().upper()
        task = item.get("Task Name")
        default_resp = str(item.get("Default Responsibility", "Previous Agent")).strip()
        if not default_resp: default_resp = "Previous Agent"
        
        should_copy = False
        if raw_cat == "BOTH" or raw_cat == "": should_copy = True
        elif raw_cat == "BC" and b_type == "Body Corporate": should_copy = True
        elif raw_cat == "HOA" and b_type == "HOA": should_copy = True
            
        if should_copy and task:
            new_rows.append([data_dict["Complex Name"], task, "FALSE", "", "", default_resp, "FALSE", ""])
    
    if new_rows:
        ws_checklist.append_rows(new_rows)
        
    clear_cache() 
    return "SUCCESS"

def update_building_details_batch(complex_name, updates):
    sh = get_google_sheet()
    ws = sh.worksheet("Projects")
    try:
        cell = ws.find(complex_name)
        row_num = cell.row
        headers = ws.row_values(1) 
        
        cells_to_update = []
        
        for col_name, new_value in updates.items():
            if new_value and col_name in headers:
                col_index = headers.index(col_name) + 1
                cells_to_update.append(gspread.Cell(row_num, col_index, new_value))
        
        if cells_to_update:
            ws.update_cells(cells_to_update)
            clear_cache()
            return True
    except Exception as e:
        st.error(f"Update failed: {e}")
    return False

def update_project_agent_details(building_name, agent_name, agent_email):
    sh = get_google_sheet()
    ws = sh.worksheet("Projects")
    try:
        cell = ws.find(building_name)
        ws.update_cell(cell.row, 24, agent_name)
        ws.update_cell(cell.row, 25, agent_email)
        clear_cache()
    except Exception as e:
        st.error(f"Could not save agent details: {e}")

def save_checklist_batch(ws, building_name, edited_df):
    all_rows = ws.get_all_values()
    task_row_map = {}
    for idx, row in enumerate(all_rows):
        if len(row) > 1 and row[0] == building_name:
            task_row_map[row[1]] = idx + 1

    cells_to_update = []
    rows_to_delete = []

    for i, row in edited_df.iterrows():
        task = row['Task Name']
        row_idx = task_row_map.get(task)
        if not row_idx: continue 

        if row['Delete']:
            rows_to_delete.append(row_idx)
            continue

        current_date_in_ui = str(row['Date Received']).strip()
        
        user_val = str(row.get('Completed By', '')).strip()
        if user_val == "None": user_val = ""

        if row['Received']:
            if not current_date_in_ui or current_date_in_ui == "None" or current_date_in_ui == "":
                date_val = datetime.now().strftime("%Y-%m-%d")
            else:
                date_val = current_date_in_ui
            rec_val = "TRUE"
        else:
            date_val = ""
            user_val = ""
            rec_val = "FALSE"

        cells_to_update.append(gspread.Cell(row_idx, 3, rec_val))
        cells_to_update.append(gspread.Cell(row_idx, 4, date_val))
        cells_to_update.append(gspread.Cell(row_idx, 5, row.get('Notes', '')))
        if 'Responsibility' in row:
            cells_to_update.append(gspread.Cell(row_idx, 6, row['Responsibility']))
        cells_to_update.append(gspread.Cell(row_idx, 7, "FALSE"))
        cells_to_update.append(gspread.Cell(row_idx, 8, user_val))

    if cells_to_update:
        ws.update_cells(cells_to_update)

    if rows_to_delete:
        for r in sorted(rows_to_delete, reverse=True):
            ws.delete_rows(r)
            
    clear_cache() 

def finalize_project_db(building_name):
    sh = get_google_sheet()
    ws = sh.worksheet("Projects")
    cell = ws.find(building_name)
    final_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.update_cell(cell.row, 22, "TRUE")
    ws.update_cell(cell.row, 23, final_date)
    ws.update_cell(cell.row, 20, final_date)
    clear_cache()
    return final_date

# --- PDF GENERATORS ---

def clean_text(text):
    if text is None: return ""
    text = str(text)
    replacements = {
        "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'", 
        "\u201c": '"', "\u201d": '"', "\u2022": "*"
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    return text.encode('latin-1', 'replace').decode('latin-1')

def generate_appointment_pdf(building_name, master_items, agent_name, take_on_date, year_end, building_code):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    
    pdf.cell(0, 10, txt=clean_text(f"RE: {building_name} - APPOINTMENT AS MANAGING AGENT"), ln=1)
    pdf.ln(5)
    
    pdf.set_font("Arial", size=10)
    intro = (
        f"ATTENTION: {agent_name}\n\n"
        f"We confirm that we have been appointed as Managing Agents of {building_name} effective from {take_on_date}.\n"
        f"In terms of this appointment, we request you to make all documentation in your possession pertaining to "
        f"{building_name} available for collection by us."
    )
    pdf.multi_cell(0, 5, clean_text(intro))
    pdf.ln(5)
    
    curr_fin, past_years, bank_req = calculate_financial_periods(take_on_date, year_end)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, "REQUIRED DOCUMENTATION:", ln=1)
    pdf.set_font("Arial", size=9)
    
    # Filter applied in main() before calling this, so master_items is clean
    for item in master_items:
        pdf.cell(5, 5, "-", ln=0)
        pdf.multi_cell(0, 5, clean_text(str(item)))
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, "BANKING DETAILS FOR TRANSFER OF FUNDS:", ln=1)
    pdf.set_font("Arial", size=9)
    
    banking_info = (
        "Account Name: Pretor Group (Pty) Ltd\n"
        "Bank: First National Bank\n"
        "Branch: Pretoria (251445)\n"
        "Account Number: 514 242 794 08\n"
        f"Reference: S{building_code}12005X"
    )
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
    
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "2. Service Providers Loaded", ln=1)
    
    if not providers_df.empty:
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(50, 10, "Provider Name", 1)
        pdf.cell(50, 10, "Service", 1)
        pdf.cell(50, 10, "Email", 1)
        pdf.cell(40, 10, "Phone", 1)
        pdf.ln()
        
        pdf.set_font("Arial", size=9)
        for _, row in providers_df.iterrows():
            pdf.cell(50, 10, clean_text(str(row['Provider Name'])[:25]), 1)
            pdf.cell(50, 10, clean_text(str(row['Service Type'])[:25]), 1)
            pdf.cell(50, 10, clean_text(str(row['Email'])[:25]), 1)
            pdf.cell(40, 10, clean_text(str(row['Phone'])[:20]), 1)
            pdf.ln()
    else:
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 10, "No service providers recorded.", ln=1)
        
    filename = clean_text(f"{building_name}_Report.pdf")
    pdf.output(filename)
    return filename

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Pretor Group Take-On", layout="wide")
    st.title("🏢 Pretor Group: Take-On Manager")

    menu = ["Dashboard", "Master Schedule", "New Building", "Manage Buildings"]
    choice = st.sidebar.selectbox("Menu", menu)
    
    if choice == "Dashboard":
        st.subheader("Active Projects Overview")
        df = get_data("Projects")
        if not df.empty:
            display_cols = ["Complex Name", "Type", "Assigned Manager", "Take On Date", "Is_Finalized"]
            available_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available_cols])
        else:
            st.info("No projects found.")

    elif choice == "Master Schedule":
        st.subheader("Master Checklist Template")
        with st.form("add_master"):
            c1, c2, c3 = st.columns([3, 1, 1])
            new_task = c1.text_input("Task Name")
            category = c2.selectbox("Category", ["Both", "BC", "HOA"])
            # UPDATED: Default Responsibility
            def_resp = c3.selectbox("Default Responsibility", ["Previous Agent", "Pretor Group", "Both"])
            if st.form_submit_button("Add Item"):
                add_master_item(new_task, category, def_resp)
                st.success("Added!")
                st.rerun()
        df = get_data("Master")
        if not df.empty:
            st.dataframe(df)

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
                        "Bookkeeper Email": book_email, "Date Doc Requested": date_req
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
            client_email = str(proj_row.get('Client Email', ''))
            saved_agent_name = str(proj_row.get('Agent Name', ''))
            saved_agent_email = str(proj_row.get('Agent Email', ''))
            take_on_date = str(proj_row.get('Take On Date', ''))
            assigned_manager = str(proj_row.get('Assigned Manager', ''))
            manager_email = str(proj_row.get('Manager Email', ''))
            assistant_name = str(proj_row.get('Assistant Name', ''))
            assistant_email = str(proj_row.get('Assistant Email', ''))
            bookkeeper_name = str(proj_row.get('Bookkeeper Name', ''))
            bookkeeper_email = str(proj_row.get('Bookkeeper Email', ''))
            year_end = str(proj_row.get('Year End', ''))
            building_code = str(proj_row.get('Building Code', ''))
            team_emails = [e for e in [manager_email, assistant_email, bookkeeper_email] if e and e != "None" and "@" in e]
            cc_string = ",".join(team_emails)
            team_list = [n for n in [assigned_manager, assistant_name, bookkeeper_name] if n and n != "None"]
            
            # --- GAP FILLING FORM (EDIT DETAILS) ---
            with st.expander("ℹ️ View / Edit Building Details", expanded=False):
                st.caption("Fields in GREY are locked. Fields in WHITE can be updated.")
                with st.form("update_details_form"):
                    def smart_input(label, col_name):
                        val = str(proj_row.get(col_name, ''))
                        is_locked = bool(val.strip() != "" and val != "None")
                        return st.text_input(label, value=val, disabled=is_locked), col_name

                    st.markdown("**Basic Info**")
                    c1, c2 = st.columns(2)
                    u_type, k_type = smart_input("Type", "Type")
                    u_prev, k_prev = smart_input("Previous Agent", "Previous Agents")
                    c3, c4 = st.columns(2)
                    u_date, k_date = smart_input("Take On Date", "Take On Date")
                    u_unit, k_unit = smart_input("No of Units", "No of Units")

                    st.markdown("**Internal Team**")
                    c5, c6 = st.columns(2)
                    u_mgr, k_mgr = smart_input("Manager Name", "Assigned Manager")
                    u_mgre, k_mgre = smart_input("Manager Email", "Manager Email")
                    c7, c8 = st.columns(2)
                    u_ast, k_ast = smart_input("Assistant Name", "Assistant Name")
                    u_aste, k_aste = smart_input("Assistant Email", "Assistant Email")
                    c9, c10 = st.columns(2)
                    u_bk, k_bk = smart_input("Bookkeeper Name", "Bookkeeper Name")
                    u_bke, k_bke = smart_input("Bookkeeper Email", "Bookkeeper Email")

                    st.markdown("**Financial & Legal**")
                    u_fees, k_fees = smart_input("Mgmt Fees", "Mgmt Fees")
                    l1, l2, l3 = st.columns(3)
                    u_erf, k_erf = smart_input("Erf No", "Erf No")
                    u_ss, k_ss = smart_input("SS Number", "SS Number")
                    u_csos, k_csos = smart_input("CSOS Number", "CSOS Number")
                    l4, l5, l6 = st.columns(3)
                    u_vat, k_vat = smart_input("VAT Number", "VAT Number")
                    u_tax, k_tax = smart_input("Tax Number", "Tax Number")
                    u_ye, k_ye = smart_input("Year End", "Year End")
                    l7, l8 = st.columns(2)
                    u_aud, k_aud = smart_input("Auditor", "Auditor")
                    u_last, k_last = smart_input("Last Audit Year", "Last Audit Year")

                    st.markdown("**System Info**")
                    s1, s2 = st.columns(2)
                    u_bcode, k_bcode = smart_input("Building Code", "Building Code")
                    u_ecode, k_ecode = smart_input("Expense Code", "Expense Code")
                    u_addr, k_addr = smart_input("Physical Address", "Physical Address")
                    u_dreq, k_dreq = smart_input("Date Docs Requested", "Date Doc Requested")
                    u_cli, k_cli = smart_input("Client Email(s)", "Client Email")

                    if st.form_submit_button("Update Details"):
                        updates = {
                            k_type: u_type, k_prev: u_prev, k_date: u_date, k_unit: u_unit,
                            k_mgr: u_mgr, k_mgre: u_mgre, k_ast: u_ast, k_aste: u_aste,
                            k_bk: u_bk, k_bke: u_bke, k_fees: u_fees, k_erf: u_erf,
                            k_ss: u_ss, k_csos: u_csos, k_vat: u_vat, k_tax: u_tax,
                            k_ye: u_ye, k_aud: u_aud, k_last: u_last, k_bcode: u_bcode,
                            k_ecode: u_ecode, k_addr: u_addr, k_dreq: u_dreq, k_cli: u_cli
                        }
                        if update_building_details_batch(b_choice, updates):
                            st.success("Details updated!")
                            st.rerun()
            
            all_items = get_data("Checklist")
            items_df = all_items[all_items['Complex Name'] == b_choice].copy()
            
            all_providers = get_data("ServiceProviders")
            if not all_providers.empty:
                providers_df = all_providers[all_providers['Complex Name'] == b_choice].copy()
            else:
                providers_df = pd.DataFrame()
            
            st.markdown("### 1. Previous Agent Handover Request")
            col_a, col_b = st.columns(2)
            agent_name = col_a.text_input("Previous Agent Name", value=saved_agent_name)
            agent_email = col_b.text_input("Previous Agent Email", value=saved_agent_email)
            if st.button("Save & Generate Request"):
                if agent_email and agent_name:
                    update_project_agent_details(b_choice, agent_name, agent_email)
                    st.success("Agent details saved.")
                    # UPDATED FILTER FOR AGENT PDF: Exclude 'Pretor Group' (Include 'Both' & 'Previous Agent')
                    request_df = items_df[items_df['Responsibility'] != 'Pretor Group']
                    request_items = request_df['Task Name'].tolist()
                    pdf_file = generate_appointment_pdf(b_choice, request_items, agent_name, take_on_date, year_end, building_code)
                    with open(pdf_file, "rb") as f:
                        st.download_button("⬇️ Download Appointment Letter & Checklist", f, file_name=pdf_file)
                    subject = f"APPOINTMENT OF MANAGING AGENTS: {b_choice}"
                    body = (f"Dear {agent_name},\n\nPlease accept this email as confirmation that Pretor Group has been appointed "
                            f"as Managing Agents for {b_choice} effective from {take_on_date}.\n\n"
                            f"Please find attached our formal handover checklist.\n\n"
                            f"Regards,\nPretor Group")
                    safe_subject = urllib.parse.quote(subject)
                    safe_body = urllib.parse.quote(body)
                    cc_param = f"&cc={cc_string}" if cc_string else ""
                    link = f'<a href="mailto:{agent_email}?subject={safe_subject}&body={safe_body}{cc_param}" target="_blank" style="background-color:#FF4B4B; color:white; padding:10px; text-decoration:none; border-radius:5px; display:inline-block; margin-top:10px;">📧 Open Email Draft to Agent</a>'
                    st.markdown(link, unsafe_allow_html=True)
            st.divider()
            
            st.markdown("### 2. Track Progress")
            items_df['Received'] = items_df['Received'].apply(lambda x: True if str(x).upper() == "TRUE" else False)
            items_df['Delete'] = items_df['Delete'].apply(lambda x: True if str(x).upper() == "TRUE" else False)
            
            view_choice = st.radio("Select View:", ["Previous Agent Tracker", "Internal Team Tracker"], horizontal=True, key="view_selector")
            
            if view_choice == "Previous Agent Tracker":
                st.caption("Items to be received from the Previous Agent")
                # UPDATED FILTER FOR TRACKER: Include 'Previous Agent' AND 'Both'
                agent_view = items_df[
                    (items_df['Responsibility'].isin(['Previous Agent', 'Both'])) & 
                    (items_df['Delete'] == False)
                ].copy()
                if 'Completed By' not in agent_view.columns: agent_view['Completed By'] = ""
                
                agent_cols = ['Task Name', 'Received', 'Date Received', 'Completed By', 'Notes']
                edited_agent = st.data_editor(
                    agent_view[agent_cols],
                    column_config={
                        "Received": st.column_config.CheckboxColumn(label="Received?"),
                        "Date Received": st.column_config.TextColumn(disabled=True),
                        # UPDATED: Options include "Both"
                        "Responsibility": st.column_config.SelectboxColumn("Action By", options=["Previous Agent", "Pretor Group", "Both"]),
                        "Completed By": st.column_config.SelectboxColumn("Completed By", options=team_list, required=False)
                    },
                    disabled=["Task Name", "Date Received"], hide_index=True, key="agent_editor"
                )
                if st.button("Save Agent Updates"):
                    sh = get_google_sheet()
                    if sh:
                        ws = sh.worksheet("Checklist")
                        save_df = edited_agent.copy()
                        # Note: We are editing a subset. If we save, we need to ensure we don't overwrite 
                        # the responsibility of these items with a hardcoded value if they vary (Both vs Prev Agent).
                        # Simpler approach: Just assume the view's logic holds or rely on task name matching.
                        # The batch saver matches by Task Name, so as long as Task Name is unique per complex, it's safe.
                        # We assume Responsibility doesn't change here, or if it does, we'd need it in the view.
                        # Let's rely on the existing Responsibility in the main dataframe for the save if not in view.
                        # Actually, 'Responsibility' is NOT in agent_cols, so it won't be updated/broken.
                        save_df['Delete'] = False
                        with st.spinner("Saving..."):
                            save_checklist_batch(ws, b_choice, save_df)
                        st.success("Agent Tracker Saved!")
                        st.rerun()
            else:
                st.caption("Full Master Tracker (Internal & External)")
                full_view = items_df[items_df['Delete'] == False].copy()
                if 'Completed By' not in full_view.columns: full_view['Completed By'] = ""
                
                full_cols = ['Task Name', 'Received', 'Date Received', 'Responsibility', 'Completed By', 'Notes', 'Delete']
                edited_full = st.data_editor(
                    full_view[full_cols],
                    column_config={
                        "Received": st.column_config.CheckboxColumn(label="Completed?"),
                        "Date Received": st.column_config.TextColumn(label="Date Completed", disabled=True),
                        "Responsibility": st.column_config.SelectboxColumn("Action By", options=["Previous Agent", "Pretor Group", "Both"]),
                        "Delete": st.column_config.CheckboxColumn(),
                        "Completed By": st.column_config.SelectboxColumn("Completed By", options=team_list, required=False)
                    },
                    disabled=["Task Name", "Date Received"], hide_index=True, key="full_editor"
                )
                if st.button("Save Internal Tracker"):
                    sh = get_google_sheet()
                    if sh:
                        ws = sh.worksheet("Checklist")
                        with st.spinner("Saving..."):
                            save_checklist_batch(ws, b_choice, edited_full)
                        st.success("Internal Tracker Saved!")
                        st.rerun()
            
            st.divider()
            st.markdown("### 3. Service Providers")
            with st.expander("Add New Service Provider", expanded=False):
                with st.form("add_provider"):
                    p_name = st.text_input("Provider Company Name")
                    p_service = st.text_input("Service Delivered (e.g. Garden Service)")
                    c1, c2 = st.columns(2)
                    p_email = c1.text_input("Email Address")
                    p_phone = c2.text_input("Telephone Number")
                    if st.form_submit_button("Add Provider"):
                        if p_name and p_service:
                            add_service_provider(b_choice, p_name, p_service, p_email, p_phone)
                            st.success("Provider Added!")
                            st.rerun()
                        else:
                            st.error("Name and Service Type are required.")
            if not providers_df.empty:
                st.write("Current Providers:")
                st.dataframe(providers_df[["Provider Name", "Service Type", "Email", "Phone", "Date Emailed"]], hide_index=True)
                st.markdown("#### Send Appointment Notice")
                provider_list = providers_df['Provider Name'].tolist()
                selected_provider = st.selectbox("Select Provider to Email", provider_list)
                prov_data = providers_df[providers_df['Provider Name'] == selected_provider].iloc[0]
                sent_date = str(prov_data['Date Emailed'])
                p_mail = str(prov_data['Email'])
                if sent_date and sent_date != "None" and sent_date != "":
                    st.success(f"✅ Email confirmation sent to {selected_provider} on: {sent_date}")
                    st.info("To resend, clear the date in the Google Sheet.")
                else:
                    if st.button("Draft Email & Mark as Sent"):
                        if p_mail:
                            success = update_service_provider_date(b_choice, selected_provider)
                            if success:
                                subj = f"Notice of Appointment: Pretor Group - {b_choice}"
                                body = (f"Dear {selected_provider},\n\n"
                                        f"Please be advised that Pretor Group has been appointed as managing agents for {b_choice} "
                                        f"effective {take_on_date}.\n\n"
                                        f"Please update your records accordingly.\n\n"
                                        f"Your Portfolio Manager is {assigned_manager} ({manager_email}). Please direct future correspondence regarding "
                                        f"service delivery and invoicing to them.\n\n"
                                        f"Regards,\nPretor Group")
                                safe_subject = urllib.parse.quote(subj)
                                safe_body = urllib.parse.quote(body)
                                cc_param = f"&cc={cc_string}" if cc_string else ""
                                link = f'<a href="mailto:{p_mail}?subject={safe_subject}&body={safe_body}{cc_param}" target="_blank" style="background-color:#FF4B4B; color:white; padding:10px; text-decoration:none; border-radius:5px;">📧 Open Email for {selected_provider}</a>'
                                st.markdown(link, unsafe_allow_html=True)
                                st.rerun()
                        else:
                            st.error("This provider has no email address saved.")
            else:
                st.caption("No providers loaded yet.")
            
            st.divider()
            st.markdown("### 4. Agent Follow-up (Urgent)")
            # UPDATED FILTER FOR URGENT EMAIL: Include 'Both'
            agent_pending_df = items_df[
                (items_df['Received'] == False) & 
                (items_df['Delete'] == False) & 
                (items_df['Responsibility'].isin(['Previous Agent', 'Both']))
            ]
            if agent_pending_df.empty:
                st.success("✅ No outstanding items marked for Previous Agent.")
            else:
                st.write(f"**{len(agent_pending_df)} items outstanding from Previous Agent.**")
                if st.button("Draft Urgent Follow-up Email"):
                    if saved_agent_email:
                        body = f"Dear {saved_agent_name},\n\nRE: URGENT - OUTSTANDING INFORMATION: {b_choice}\n\n" \
                               "Please note that the following items are still outstanding:\n\n"
                        for _, row in agent_pending_df.iterrows():
                            body += f"- {row['Task Name']}\n"
                        body += "\nYour urgent cooperation is appreciated.\n\nRegards,\nPretor Group"
                        subject = f"URGENT: Outstanding Handover Items - {b_choice}"
                        safe_subject = urllib.parse.quote(subject)
                        safe_body = urllib.parse.quote(body)
                        cc_param = f"&cc={cc_string}" if cc_string else ""
                        link = f'<a href="mailto:{saved_agent_email}?subject={safe_subject}&body={safe_body}{cc_param}" target="_blank" style="background-color:#FF4B4B; color:white; padding:10px; text-decoration:none; border-radius:5px;">📧 Open Urgent Email</a>'
                        st.markdown(link, unsafe_allow_html=True)
            
            st.divider()
            st.markdown("### 5. Reports & Comms")
            col1, col2 = st.columns(2)
            pending_df = items_df[(items_df['Received'] == False) & (items_df['Delete'] == False)]
            completed_df = items_df[items_df['Received'] == True]
            with col1:
                st.subheader("Client Update")
                if st.button("Draft Client Email"):
                    body = f"Dear Client,\n\nProgress Update for {b_choice}:\n\n⚠️ OUTSTANDING:\n"
                    if pending_df.empty: body += "- None\n"
                    else:
                        for _, row in pending_df.iterrows():
                            note_text = f" -- (Note: {row['Notes']})" if row['Notes'] else ""
                            body += f"- {row['Task Name']} (Action: {row['Responsibility']}){note_text}\n"
                    body += "\n✅ RECEIVED:\n"
                    for _, row in completed_df.iterrows():
                        note_text = f" -- (Note: {row['Notes']})" if row['Notes'] else ""
                        body += f"- {row['Task Name']} (Date: {row['Date Received']}){note_text}\n"
                    body += "\n📋 SERVICE PROVIDERS STATUS:\n"
                    if providers_df.empty:
                        body += "- None loaded yet\n"
                    else:
                        for _, row in providers_df.iterrows():
                            name = row['Provider Name']
                            service = row['Service Type']
                            date_sent = str(row['Date Emailed'])
                            status = f"✅ Notified ({date_sent})" if (date_sent and date_sent != "None") else "⚠️ Pending Notification"
                            body += f"- {service}: {name} [{status}]\n"
                    body += "\nRegards,\nPretor Group"
                    safe_subject = urllib.parse.quote(f"Progress Update: {b_choice}")
                    safe_body = urllib.parse.quote(body)
                    safe_emails = client_email.replace(";", ",")
                    cc_param = f"&cc={cc_string}" if cc_string else ""
                    link = f'<a href="mailto:{safe_emails}?subject={safe_subject}&body={safe_body}{cc_param}" target="_blank" style="text-decoration:none;">📩 Open Client Email</a>'
                    st.markdown(link, unsafe_allow_html=True)
            with col2:
                st.subheader("Finalize")
                if st.button("Finalize Project"):
                    if pending_df.empty:
                        date = finalize_project_db(b_choice)
                        pdf = generate_report_pdf(b_choice, items_df, providers_df, "Final Report")
                        with open(pdf, "rb") as f:
                            st.download_button("Download Final PDF", f, file_name=pdf)
                        st.balloons()
                    else:
                        st.error(f"Cannot finalize. {len(pending_df)} items pending.")

if __name__ == "__main__":
    main()
