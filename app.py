import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from fpdf import FPDF
import urllib.parse 

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

# --- DATA FUNCTIONS ---
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
                    sh.add_worksheet("ServiceProviders", 100, 5)
                    sh.worksheet("ServiceProviders").append_row(["Complex Name", "Provider Name", "Service Type", "Email", "Phone"])
                    return pd.DataFrame(columns=["Complex Name", "Provider Name", "Service Type", "Email", "Phone"])
                except:
                    return pd.DataFrame()
            st.error(f"Error reading {worksheet_name}: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

def add_master_item(task_name, category):
    sh = get_google_sheet()
    ws = sh.worksheet("Master")
    ws.append_row([task_name, category])

def add_service_provider(complex_name, name, service, email, phone):
    sh = get_google_sheet()
    ws = sh.worksheet("ServiceProviders")
    ws.append_row([complex_name, name, service, email, phone])

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
        ""  
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
    
    for item in master_data:
        raw_cat = str(item.get("Category", "Both")).strip().upper()
        task = item.get("Task Name")
        should_copy = False
        
        if raw_cat == "BOTH" or raw_cat == "": should_copy = True
        elif raw_cat == "BC" and b_type == "Body Corporate": should_copy = True
        elif raw_cat == "HOA" and b_type == "HOA": should_copy = True
            
        if should_copy and task:
            new_rows.append([data_dict["Complex Name"], task, "FALSE", "", "", "Previous Agent", "FALSE"])
    
    if new_rows:
        ws_checklist.append_rows(new_rows)
        return "SUCCESS"
    return "EMPTY_MASTER"

def update_project_agent_details(building_name, agent_name, agent_email):
    sh = get_google_sheet()
    ws = sh.worksheet("Projects")
    try:
        cell = ws.find(building_name)
        ws.update_cell(cell.row, 24, agent_name)
        ws.update_cell(cell.row, 25, agent_email)
    except Exception as e:
        st.error(f"Could not save agent details: {e}")

# --- NEW BATCH SAVE FUNCTION (CRASH PROOF) ---
def save_checklist_batch(ws, building_name, edited_df):
    """
    Downloads the sheet ONCE, maps the rows, prepares all changes, 
    and sends ONE update command. Prevents API Error.
    """
    # 1. Get all data (One Read)
    all_rows = ws.get_all_values()
    
    # 2. Create a map: {Task Name : Row Number}
    # We assume column 1 (index 0) is Complex Name, column 2 (index 1) is Task Name
    task_row_map = {}
    for idx, row in enumerate(all_rows):
        # idx is 0-based, Google Sheets is 1-based.
        if len(row) > 1 and row[0] == building_name:
            task_row_map[row[1]] = idx + 1

    cells_to_update = []
    rows_to_delete = []

    # 3. Iterate through user changes
    for i, row in edited_df.iterrows():
        task = row['Task Name']
        row_idx = task_row_map.get(task)

        if not row_idx: 
            continue # Skip if not found (shouldn't happen)

        if row['Delete']:
            rows_to_delete.append(row_idx)
            continue

        # Date Logic: Keep existing date if available, else set today if checked
        current_date_in_ui = str(row['Date Received']).strip()
        if row['Received']:
            if not current_date_in_ui or current_date_in_ui == "None":
                date_val = datetime.now().strftime("%Y-%m-%d")
            else:
                date_val = current_date_in_ui
            rec_val = "TRUE"
        else:
            date_val = ""
            rec_val = "FALSE"

        # 4. Prepare Updates (Columns 3, 4, 5, 6, 7)
        # Received (3), Date (4), Notes (5), Responsibility (6), Delete (7)
        cells_to_update.append(gspread.Cell(row_idx, 3, rec_val))
        cells_to_update.append(gspread.Cell(row_idx, 4, date_val))
        cells_to_update.append(gspread.Cell(row_idx, 5, row['Notes']))
        cells_to_update.append(gspread.Cell(row_idx, 6, row['Responsibility']))
        cells_to_update.append(gspread.Cell(row_idx, 7, "FALSE")) # Reset delete flag

    # 5. Execute Updates (One Write)
    if cells_to_update:
        ws.update_cells(cells_to_update)

    # 6. Execute Deletes (Bottom up)
    if rows_to_delete:
        for r in sorted(rows_to_delete, reverse=True):
            ws.delete_rows(r)

def finalize_project_db(building_name):
    sh = get_google_sheet()
    ws = sh.worksheet("Projects")
    cell = ws.find(building_name)
    final_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.update_cell(cell.row, 22, "TRUE")
    ws.update_cell(cell.row, 23, final_date)
    ws.update_cell(cell.row, 20, final_date)
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

def generate_appointment_pdf(building_name, master_items, agent_name, take_on_date):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, txt=clean_text(f"HANDOVER REQUEST: {building_name}"), ln=1, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", size=11)
    letter_text = (
        f"ATTENTION: {agent_name}\n\n"
        f"RE: APPOINTMENT OF PRETOR GROUP AS MANAGING AGENTS\n\n"
        f"Please be advised that Pretor Group has been appointed as the Managing Agents "
        f"for {building_name} effective from {take_on_date}.\n\n"
        f"In order to facilitate a smooth transition, kindly provide us with the documentation "
        f"and information listed in the schedule below. Please check off items as they are included."
    )
    pdf.multi_cell(0, 7, clean_text(letter_text))
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(140, 10, "Required Item / Document", 1)
    pdf.cell(40, 10, "Included?", 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=10)
    for item in master_items:
        pdf.cell(140, 10, clean_text(str(item)[:65]), 1)
        pdf.cell(40, 10, "", 1)
        pdf.ln()
        
    filename = clean_text(f"{building_name}_Handover_Request.pdf")
    pdf.output(filename)
    return filename

def generate_report_pdf(building_name, items_df, providers_df, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt=clean_text(f"{title}: {building_name}"), ln=1, align='C')
    pdf.ln(10)
    
    # Checklist Section
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
    
    # Service Providers Section
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
            c1, c2 = st.columns([3, 1])
            new_task = c1.text_input("Task Name")
            category = c2.selectbox("Category", ["Both", "BC", "HOA"])
            if st.form_submit_button("Add Item"):
                add_master_item(new_task, category)
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
            
            c3, c4 = st.columns(2)
            fees = c3.text_input("Management Fees (Excl VAT)")
            assigned_mgr = c4.text_input("Assigned Manager")
            
            st.write("### Legal & Financial")
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
                        "Complex Name": complex_name,
                        "Type": b_type,
                        "Client Email": client_email,
                        "Previous Agents": prev_agent,
                        "Take On Date": take_on_date,
                        "No of Units": units,
                        "Mgmt Fees": fees,
                        "Erf No": erf_no,
                        "SS Number": ss_num,
                        "CSOS Number": csos_num,
                        "VAT Number": vat_num,
                        "Tax Number": tax_num,
                        "Year End": year_end,
                        "Auditor": auditor,
                        "Last Audit Year": last_audit,
                        "Building Code": build_code,
                        "Expense Code": exp_code,
                        "Physical Address": phys_address,
                        "Assigned Manager": assigned_mgr,
                        "Date Doc Requested": date_req
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
            
            # Load Data
            all_items = get_data("Checklist")
            items_df = all_items[all_items['Complex Name'] == b_choice].copy()
            
            all_providers = get_data("ServiceProviders")
            if not all_providers.empty:
                providers_df = all_providers[all_providers['Complex Name'] == b_choice].copy()
            else:
                providers_df = pd.DataFrame()
            
            # --- STEP 1: PREVIOUS AGENT HANDOVER ---
            st.markdown("### 1. Previous Agent Handover Request")
            col_a, col_b = st.columns(2)
            agent_name = col_a.text_input("Previous Agent Name", value=saved_agent_name)
            agent_email = col_b.text_input("Previous Agent Email", value=saved_agent_email)
            
            if st.button("Save & Generate Request"):
                if agent_email and agent_name:
                    update_project_agent_details(b_choice, agent_name, agent_email)
                    st.success("Agent details saved.")
                    request_items = items_df['Task Name'].tolist()
                    pdf_file = generate_appointment_pdf(b_choice, request_items, agent_name, take_on_date)
                    with open(pdf_file, "rb") as f:
                        st.download_button("⬇️ Download Appointment Letter & Checklist", f, file_name=pdf_file)
                    subject = f"APPOINTMENT OF MANAGING AGENTS: {b_choice}"
                    body = (f"Dear {agent_name},\n\nPlease accept this email as confirmation that Pretor Group has been appointed "
                            f"as Managing Agents for {b_choice} effective from {take_on_date}.\n\n"
                            f"Please find attached our formal handover checklist.\n\n"
                            f"Regards,\nPretor Group")
                    safe_subject = urllib.parse.quote(subject)
                    safe_body = urllib.parse.quote(body)
                    link = f'<a href="mailto:{agent_email}?subject={safe_subject}&body={safe_body}" target="_blank" style="background-color:#FF4B4B; color:white; padding:10px; text-decoration:none; border-radius:5px; display:inline-block; margin-top:10px;">📧 Open Email Draft to Agent</a>'
                    st.markdown(link, unsafe_allow_html=True)
            
            st.divider()
            
            # --- STEP 2: CHECKLIST ---
            st.markdown("### 2. Track Progress")
            items_df['Received'] = items_df['Received'].apply(lambda x: True if str(x).upper() == "TRUE" else False)
            items_df['Delete'] = items_df['Delete'].apply(lambda x: True if str(x).upper() == "TRUE" else False)
            
            display_cols = ['Task Name', 'Received', 'Date Received', 'Responsibility', 'Notes', 'Delete']
            edited_df = st.data_editor(
                items_df[display_cols],
                column_config={
                    "Received": st.column_config.CheckboxColumn(),
                    "Date Received": st.column_config.TextColumn(disabled=True),
                    "Responsibility": st.column_config.SelectboxColumn("Action By", options=["Previous Agent", "Pretor Group"]),
                    "Delete": st.column_config.CheckboxColumn()
                },
                disabled=["Task Name", "Date Received"], 
                hide_index=True, key="editor"
            )
            
            # OPTIMIZED SAVE BUTTON
            if st.button("Save Changes"):
                sh = get_google_sheet()
                if sh:
                    ws = sh.worksheet("Checklist")
                    with st.spinner("Saving changes..."):
                        # Pass dataframe to batch function
                        save_checklist_batch(ws, b_choice, edited_df)
                    st.success("Checklist Updated!")
                    st.rerun()

            st.divider()

            # --- STEP 3: SERVICE PROVIDERS ---
            st.markdown("### 3. Service Providers")
            st.info("Capture details of service providers (Security, Gardening, Maintenance, etc.)")
            
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
                st.dataframe(providers_df[["Provider Name", "Service Type", "Email", "Phone"]], hide_index=True)
            else:
                st.caption("No providers loaded yet.")

            st.divider()
            
            # --- STEP 4: AGENT FOLLOW-UP ---
            st.markdown("### 4. Agent Follow-up (Urgent)")
            agent_pending_df = items_df[(items_df['Received'] == False) & (items_df['Delete'] == False) & (items_df['Responsibility'] == 'Previous Agent')]
            
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
                        link = f'<a href="mailto:{saved_agent_email}?subject={safe_subject}&body={safe_body}" target="_blank" style="background-color:#FF4B4B; color:white; padding:10px; text-decoration:none; border-radius:5px;">📧 Open Urgent Email</a>'
                        st.markdown(link, unsafe_allow_html=True)
            
            st.divider()
            
            # --- STEP 5: REPORTS ---
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
                            body += f"- {row['Task Name']} (Action: {row['Responsibility']})\n"
                    body += "\n✅ RECEIVED:\n"
                    for _, row in completed_df.iterrows():
                        body += f"- {row['Task Name']} (Date: {row['Date Received']})\n"
                    body += "\nRegards,\nPretor Group"
                    safe_subject = urllib.parse.quote(f"Progress Update: {b_choice}")
                    safe_body = urllib.parse.quote(body)
                    safe_emails = client_email.replace(";", ",")
                    link = f'<a href="mailto:{safe_emails}?subject={safe_subject}&body={safe_body}" target="_blank" style="text-decoration:none;">📩 Open Client Email</a>'
                    st.markdown(link, unsafe_allow_html=True)

            with col2:
                st.subheader("Finalize")
                if st.button("Finalize Project"):
                    if pending_df.empty:
                        date = finalize_project_db(b_choice)
                        # Updated to include providers_df in PDF
                        pdf = generate_report_pdf(b_choice, items_df, providers_df, "Final Report")
                        with open(pdf, "rb") as f:
                            st.download_button("Download Final PDF", f, file_name=pdf)
                        st.balloons()
                    else:
                        st.error(f"Cannot finalize. {len(pending_df)} items pending.")

if __name__ == "__main__":
    main()
