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
            st.error(f"Error reading {worksheet_name}: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

def add_master_item(task_name, category):
    sh = get_google_sheet()
    ws = sh.worksheet("Master")
    ws.append_row([task_name, category])

def delete_master_item(task_name):
    sh = get_google_sheet()
    ws = sh.worksheet("Master")
    try:
        cell = ws.find(task_name)
        ws.delete_rows(cell.row)
    except:
        st.warning("Item not found.")

def create_new_building(data_dict):
    sh = get_google_sheet()
    ws_projects = sh.worksheet("Projects")
    
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
        "", # Date Final Doc Received
        data_dict["Client Email"],
        "FALSE", # Is_Finalized
        "", # Finalized_Date
        "", # Agent Name
        ""  # Agent Email
    ]
    ws_projects.append_row(row_data)
    
    ws_master = sh.worksheet("Master")
    master_data = ws_master.get_all_records()
    
    b_type = data_dict["Type"] 
    ws_checklist = sh.worksheet("Checklist")
    new_rows = []
    
    for item in master_data:
        category = item.get("Category", "Both")
        task = item.get("Task Name")
        
        should_copy = False
        if category == "Both": should_copy = True
        elif category == "BC" and b_type == "Body Corporate": should_copy = True
        elif category == "HOA" and b_type == "HOA": should_copy = True
            
        if should_copy and task:
            new_rows.append([data_dict["Complex Name"], task, "FALSE", "", "", "Previous Agent", "FALSE"])
    
    if new_rows:
        ws_checklist.append_rows(new_rows)
        return True
    return False

def update_project_agent_details(building_name, agent_name, agent_email):
    sh = get_google_sheet()
    ws = sh.worksheet("Projects")
    try:
        cell = ws.find(building_name)
        ws.update_cell(cell.row, 24, agent_name)
        ws.update_cell(cell.row, 25, agent_email)
    except Exception as e:
        st.error(f"Could not save agent details: {e}")

def update_checklist_item(building_name, task_name, received, notes, responsibility, delete_flag):
    sh = get_google_sheet()
    ws = sh.worksheet("Checklist")
    cells = ws.findall(building_name)
    target_row = None
    for cell in cells:
        if ws.cell(cell.row, 2).value == task_name:
            target_row = cell.row
            break
            
    if target_row:
        if delete_flag:
            ws.delete_rows(target_row)
        else:
            # AUTO-DATE LOGIC
            date_str = datetime.now().strftime("%Y-%m-%d") if received else ""
            ws.update_cell(target_row, 3, "TRUE" if received else "FALSE")
            ws.update_cell(target_row, 4, date_str)
            ws.update_cell(target_row, 5, notes)
            ws.update_cell(target_row, 6, responsibility)
            ws.update_cell(target_row, 7, "FALSE")

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

def generate_appointment_pdf(building_name, master_items, agent_name, take_on_date):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, txt=f"HANDOVER REQUEST: {building_name}", ln=1, align='C')
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
    pdf.multi_cell(0, 7, letter_text)
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(140, 10, "Required Item / Document", 1)
    pdf.cell(40, 10, "Included?", 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=10)
    for item in master_items:
        pdf.cell(140, 10, str(item)[:65], 1)
        pdf.cell(40, 10, "", 1)
        pdf.ln()
        
    filename = f"{building_name}_Handover_Request.pdf"
    pdf.output(filename)
    return filename

def generate_report_pdf(building_name, items_df, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt=f"{title}: {building_name}", ln=1, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(80, 10, "Item", 1)
    pdf.cell(30, 10, "Status", 1)
    pdf.cell(40, 10, "Action By", 1)
    pdf.cell(40, 10, "Notes", 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=9)
    for _, row in items_df.iterrows():
        status = "Received" if row['Received'] else "Pending"
        pdf.cell(80, 10, str(row['Task Name'])[:40], 1)
        pdf.cell(30, 10, status, 1)
        pdf.cell(40, 10, str(row['Responsibility'])[:20], 1)
        pdf.cell(40, 10, str(row['Notes'])[:20], 1)
        pdf.ln()
        
    filename = f"{building_name}_Report.pdf"
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
                    success = create_new_building(data)
                    if success:
                        st.success(f"Created {complex_name}!")
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
            
            all_items = get_data("Checklist")
            items_df = all_items[all_items['Complex Name'] == b_choice].copy()
            
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
                    body = (
                        f"Dear {agent_name},\n\n"
                        f"Please accept this email as confirmation that Pretor Group has been appointed "
                        f"as Managing Agents for {b_choice} effective from {take_on_date}.\n\n"
                        f"Please find attached our formal handover checklist.\n\n"
                        f"Kindly provide the requested documentation at your earliest convenience to ensure a smooth transition.\n\n"
                        f"Regards,\nPretor Group"
                    )
                    safe_subject = urllib.parse.quote(subject)
                    safe_body = urllib.parse.quote(body)
                    link = f'<a href="mailto:{agent_email}?subject={safe_subject}&body={safe_body}" target="_blank" style="background-color:#FF4B4B; color:white; padding:10px; text-decoration:none; border-radius:5px; display:inline-block; margin-top:10px;">📧 Open Email Draft to Agent</a>'
                    st.markdown(link, unsafe_allow_html=True)
                else:
                    st.error("Please enter Agent Name and Email.")
            
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
                hide_index=True,
                key="editor"
            )
            
            if st.button("Save Changes"):
                for index, row in edited_df.iterrows():
                    update_checklist_item(
                        b_choice, row['Task Name'], row['Received'], row['Notes'],
                        row['Responsibility'], row['Delete']
                    )
                st.success("Checklist Updated!")
                st.rerun()

            st.divider()
            
            # --- STEP 3: REPORTS ---
            col1, col2 = st.columns(2)
            
            pending_df = items_df[(items_df['Received'] == False) & (items_df['Delete'] == False)]
            completed_df = items_df[items_df['Received'] == True]
            
            with col1:
                st.subheader("Client Communications")
                if st.button("Draft Client Update"):
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
                        pdf = generate_report_pdf(b_choice, items_df, "Final Report")
                        with open(pdf, "rb") as f:
                            st.download_button("Download Final PDF", f, file_name=pdf)
                        st.balloons()
                    else:
                        st.error(f"Cannot finalize. {len(pending_df)} items pending.")

if __name__ == "__main__":
    main()
