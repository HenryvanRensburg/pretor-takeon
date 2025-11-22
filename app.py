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
        worksheet = sh.worksheet(worksheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()
        return df
    return pd.DataFrame()

def add_master_item(task_name):
    sh = get_google_sheet()
    ws = sh.worksheet("Master")
    ws.append_row([task_name])

def delete_master_item(task_name):
    sh = get_google_sheet()
    ws = sh.worksheet("Master")
    try:
        cell = ws.find(task_name)
        ws.delete_rows(cell.row)
    except:
        st.warning("Item not found.")

def create_new_building(name, email):
    sh = get_google_sheet()
    ws_projects = sh.worksheet("Projects")
    ws_projects.append_row([name, email, "FALSE", "", "", ""])
    
    ws_master = sh.worksheet("Master")
    all_values = ws_master.col_values(1)
    
    if len(all_values) > 1:
        master_tasks = all_values[1:] 
    else:
        master_tasks = [] 
    
    ws_checklist = sh.worksheet("Checklist")
    new_rows = []
    for task in master_tasks:
        if task and str(task).strip() != "": 
            new_rows.append([name, task, "FALSE", "", ""])
    
    if new_rows:
        ws_checklist.append_rows(new_rows)
        return True
    return False

def update_project_agent_details(building_name, agent_name, agent_email):
    sh = get_google_sheet()
    ws = sh.worksheet("Projects")
    try:
        cell = ws.find(building_name)
        ws.update_cell(cell.row, 5, agent_name)
        ws.update_cell(cell.row, 6, agent_email)
    except Exception as e:
        st.error(f"Could not save agent details: {e}")

def update_checklist_item(building_name, task_name, received, notes):
    sh = get_google_sheet()
    ws = sh.worksheet("Checklist")
    cells = ws.findall(building_name)
    target_row = None
    for cell in cells:
        task_cell_val = ws.cell(cell.row, 2).value
        if task_cell_val == task_name:
            target_row = cell.row
            break
    
    if target_row:
        date_str = datetime.now().strftime("%Y-%m-%d") if received else ""
        ws.update_cell(target_row, 3, "TRUE" if received else "FALSE")
        ws.update_cell(target_row, 4, date_str)
        ws.update_cell(target_row, 5, notes)

def finalize_project_db(building_name):
    sh = get_google_sheet()
    ws = sh.worksheet("Projects")
    cell = ws.find(building_name)
    final_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.update_cell(cell.row, 3, "TRUE")
    ws.update_cell(cell.row, 4, final_date)
    return final_date

# --- PDF GENERATORS ---
def generate_initial_request_pdf(building_name, master_items, agent_name):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Handover Request: {building_name}", ln=1, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", size=11)
    intro = (f"Attention: {agent_name}\n\n"
             f"Please kindly provide the following information and documents regarding the "
             f"handover of {building_name}. Please tick the items as you attach them.")
    pdf.multi_cell(0, 7, intro)
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(150, 10, "Required Item / Document", 1)
    pdf.cell(30, 10, "Included?", 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=10)
    for item in master_items:
        pdf.cell(150, 10, str(item)[:70], 1)
        pdf.cell(30, 10, "", 1)
        pdf.ln()
        
    filename = f"{building_name}_Handover_Request.pdf"
    pdf.output(filename)
    return filename

def generate_final_pdf(building_name, items_df, final_date):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Final Take-On Report: {building_name}", ln=1, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Finalized on: {final_date}", ln=1, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(80, 10, "Item", 1)
    pdf.cell(30, 10, "Date Rec.", 1)
    pdf.cell(80, 10, "Notes", 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=10)
    for _, row in items_df.iterrows():
        status_date = row['Date Received'] if row['Received'] else "Pending"
        pdf.cell(80, 10, str(row['Task Name'])[:40], 1)
        pdf.cell(30, 10, str(status_date), 1)
        pdf.cell(80, 10, str(row['Notes'])[:40], 1)
        pdf.ln()
    filename = f"{building_name}_Final_Report.pdf"
    pdf.output(filename)
    return filename

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Pretor Group Take-On", layout="wide")
    st.title("🏢 Pretor Group: Cloud Take-On Manager")

    menu = ["Dashboard", "Master Schedule", "New Building", "Manage Buildings"]
    choice = st.sidebar.selectbox("Menu", menu)
    
    if choice == "Dashboard":
        st.subheader("Active Projects Overview")
        df = get_data("Projects")
        if not df.empty:
            st.dataframe(df)
        else:
            st.info("No projects found.")

    elif choice == "Master Schedule":
        st.subheader("Master Checklist Template")
        new_task = st.text_input("Add new item")
        if st.button("Add Item"):
            add_master_item(new_task)
            st.success("Added!")
            st.rerun()
        df = get_data("Master")
        if not df.empty:
            if "Task Name" in df.columns:
                for task in df['Task Name']:
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"• {task}")
                    if c2.button("Delete", key=task):
                        delete_master_item(task)
                        st.rerun()

    elif choice == "New Building":
        st.subheader("Onboard New Complex")
        b_name = st.text_input("Building Name")
        # UPDATED INPUT: Prompt for comma separation
        b_email = st.text_input("Client Email(s) (separate multiple with commas, e.g., a@test.com, b@test.com)")
        
        if st.button("Create Project"):
            if b_name:
                success = create_new_building(b_name, b_email)
                if success:
                    st.success(f"Project {b_name} created!")
                else:
                    st.warning("Created, but Master Schedule was empty.")
            else:
                st.error("Please enter a name.")

    elif choice == "Manage Buildings":
        projects = get_data("Projects")
        if projects.empty:
            st.warning("No projects yet.")
        else:
            b_choice = st.selectbox("Select Complex", projects['Building Name'])
            proj_row = projects[projects['Building Name'] == b_choice].iloc[0]
            
            client_emails_raw = str(proj_row.get('Email', ''))
            saved_agent_name = str(proj_row.get('Agent Name', ''))
            saved_agent_email = str(proj_row.get('Agent Email', ''))
            is_finalized = str(proj_row.get('Is_Finalized', 'FALSE')).upper() == "TRUE"
            finalized_date = str(proj_row.get('Finalized_Date', ''))
            
            all_items = get_data("Checklist")
            items_df = all_items[all_items['Building Name'] == b_choice].copy()
            
            # --- SECTION 1: AGENT REQUEST ---
            with st.expander("📄 Step 1: Request Info from Previous Agent", expanded=False):
                st.write("Enter or update the previous agent's details:")
                
                col_a, col_b = st.columns(2)
                agent_name = col_a.text_input("Previous Managing Agent Name", value=saved_agent_name)
                agent_email = col_b.text_input("Previous Managing Agent Email", value=saved_agent_email)
                
                if st.button("Save Agent & Generate Request"):
                    if agent_email and agent_name:
                        update_project_agent_details(b_choice, agent_name, agent_email)
                        st.success("Agent details saved to database.")
                        
                        request_items = items_df['Task Name'].tolist()
                        pdf_file = generate_initial_request_pdf(b_choice, request_items, agent_name)
                        with open(pdf_file, "rb") as f:
                            st.download_button("1. Download PDF Checklist", f, file_name=pdf_file)
                        
                        subject = f"Handover Requirements: {b_choice}"
                        body = f"Dear {agent_name},\n\nPlease find attached the handover checklist for {b_choice}.\n\nKindly provide these items at your earliest convenience.\n\nRegards,\nPretor Group"
                        safe_subject = urllib.parse.quote(subject)
                        safe_body = urllib.parse.quote(body)
                        
                        mailto_link = f'<a href="mailto:{agent_email}?subject={safe_subject}&body={safe_body}" target="_blank" style="background-color:#FF4B4B; color:white; padding:10px; text-decoration:none; border-radius:5px; display:inline-block; margin-top:10px;">2. Open Email Draft</a>'
                        st.markdown(mailto_link, unsafe_allow_html=True)
                    else:
                        st.error("Please enter the Agent's Name and Email.")

            st.divider()

            # --- SECTION 2: CHECKLIST ---
            st.subheader("Step 2: Track Progress")
            if is_finalized:
                st.success(f"🔒 Finalized on {finalized_date}")

            display_df = items_df[['Task Name', 'Received', 'Date Received', 'Notes']].copy()
            display_df['Received'] = display_df['Received'].apply(lambda x: True if str(x).upper() == "TRUE" else False)

            edited_df = st.data_editor(
                display_df,
                column_config={
                    "Received": st.column_config.CheckboxColumn(required=True),
                    "Date Received": st.column_config.TextColumn(disabled=True)
                },
                disabled=["Task Name"],
                hide_index=True,
                key="editor"
            )
            
            if st.button("Save Changes"):
                for index, row in edited_df.iterrows():
                    update_checklist_item(b_choice, row['Task Name'], row['Received'], row['Notes'])
                st.success("Saved!")
                st.rerun()
            
            st.divider()
            
            # --- SECTION 3: REPORTS ---
            col1, col2 = st.columns(2)
            
            pending_df = items_df[items_df['Received'] == "FALSE"]
            completed_df = items_df[items_df['Received'] == "TRUE"]

            with col1:
                st.subheader("Weekly Reports")
                
                # Button 1: Client Report
                st.markdown("#### 1. Client Update")
                if st.button("Draft Client Email"):
                    body = f"Dear Client,\n\nHere is the progress update for the take-on of {b_choice}.\n\n"
                    
                    body += "⚠️ OUTSTANDING ITEMS:\n"
                    if pending_df.empty:
                        body += "- None (All items received)\n"
                    else:
                        for _, row in pending_df.iterrows():
                            body += f"- {row['Task Name']}\n"
                    
                    body += "\n"
                    
                    body += "✅ ITEMS RECEIVED:\n"
                    if completed_df.empty:
                        body += "- None yet\n"
                    else:
                        for _, row in completed_df.iterrows():
                            body += f"- {row['Task Name']} (Received: {row['Date Received']})\n"
                    
                    body += "\nRegards,\nPretor Group"
                    
                    safe_subject = urllib.parse.quote(f"Progress Update: {b_choice}")
                    safe_body = urllib.parse.quote(body)
                    
                    # LOGIC UPDATE: Format the email string to be mailto-safe (replace semicolons with commas)
                    safe_emails = client_emails_raw.replace(";", ",")
                    
                    link = f'<a href="mailto:{safe_emails}?subject={safe_subject}&body={safe_body}" target="_blank" style="text-decoration:none;">📩 Open Client Email</a>'
                    st.markdown(link, unsafe_allow_html=True)
                
                st.markdown("---")
                
                # Button 2: Agent Reminder
                st.markdown("#### 2. Agent Reminder")
                if st.button("Draft Agent Reminder"):
                    if saved_agent_email and saved_agent_name:
                        body = f"Dear {saved_agent_name},\n\nRe: {b_choice} Handover - Outstanding Items\n\nPlease note that we are still awaiting the following items to complete the handover:\n"
                        for _, row in pending_df.iterrows():
                            body += f"- {row['Task Name']}\n"
                        body += "\nYour urgent attention to this matter would be appreciated.\n\nRegards,\nPretor Group"
                        
                        safe_subject = urllib.parse.quote(f"Outstanding Items: {b_choice}")
                        safe_body = urllib.parse.quote(body)
                        
                        link = f'<a href="mailto:{saved_agent_email}?subject={safe_subject}&body={safe_body}" target="_blank" style="background-color:#FF4B4B; color:white; padding:5px; text-decoration:none; border-radius:5px;">📩 Open Agent Reminder</a>'
                        st.markdown(link, unsafe_allow_html=True)
                    else:
                        st.error("No Agent Email found. Please save agent details in 'Step 1' first.")

            with col2:
                st.subheader("Finalize")
                if not is_finalized:
                    if st.button("Finalize Project"):
                         if not any(items_df['Received'] == "FALSE"):
                             date = finalize_project_db(b_choice)
                             pdf = generate_final_pdf(b_choice, items_df, date)
                             with open(pdf, "rb") as f:
                                st.download_button("Download Final PDF", f, file_name=pdf)
                             st.balloons()
                         else:
                             st.error("Complete all items first.")

if __name__ == "__main__":
    main()
