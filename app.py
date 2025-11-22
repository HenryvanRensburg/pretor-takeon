import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from fpdf import FPDF
import urllib.parse # Needed for the email link

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
        # Clean columns to avoid whitespace errors
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
        st.warning("Item not found in Sheet to delete.")

def create_new_building(name, email):
    sh = get_google_sheet()
    ws_projects = sh.worksheet("Projects")
    ws_projects.append_row([name, email, "FALSE", ""])
    
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

def generate_initial_request_pdf(building_name, master_items):
    """Generates a checklist for the previous agent."""
    pdf = FPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Handover Request: {building_name}", ln=1, align='C')
    pdf.ln(10)
    
    # Intro Text
    pdf.set_font("Arial", size=11)
    intro = (f"Dear Managing Agent,\n\n"
             f"Please kindly provide the following information and documents regarding the "
             f"handover of {building_name}. Please tick the items as you attach them.")
    pdf.multi_cell(0, 7, intro)
    pdf.ln(10)
    
    # Table Header
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(150, 10, "Required Item / Document", 1)
    pdf.cell(30, 10, "Included?", 1)
    pdf.ln()
    
    # Items
    pdf.set_font("Arial", size=10)
    for item in master_items:
        pdf.cell(150, 10, str(item)[:70], 1) # Truncate if too long
        pdf.cell(30, 10, "", 1) # Empty box for them to tick
        pdf.ln()
        
    filename = f"{building_name}_Handover_Request.pdf"
    pdf.output(filename)
    return filename

def generate_final_pdf(building_name, items_df, final_date):
    """Generates the final report for the client."""
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
    
    # --- DASHBOARD ---
    if choice == "Dashboard":
        st.subheader("Active Projects Overview")
        df = get_data("Projects")
        if not df.empty:
            st.dataframe(df)
        else:
            st.info("No projects found.")

    # --- MASTER SCHEDULE ---
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

    # --- NEW BUILDING ---
    elif choice == "New Building":
        st.subheader("Onboard New Complex")
        b_name = st.text_input("Building Name")
        b_email = st.text_input("Client Email")
        
        if st.button("Create Project"):
            if b_name:
                success = create_new_building(b_name, b_email)
                if success:
                    st.success(f"Project {b_name} created!")
                else:
                    st.warning("Created, but Master Schedule was empty.")
            else:
                st.error("Please enter a name.")

    # --- MANAGE BUILDINGS ---
    elif choice == "Manage Buildings":
        projects = get_data("Projects")
        if projects.empty:
            st.warning("No projects yet.")
        else:
            b_choice = st.selectbox("Select Complex", projects['Building Name'])
            
            # Get Project Data
            proj_row = projects[projects['Building Name'] == b_choice].iloc[0]
            client_email = str(proj_row['Email']) # Get email for the mailto link
            is_finalized = str(proj_row['Is_Finalized']).upper() == "TRUE"
            
            # Get Items
            all_items = get_data("Checklist")
            items_df = all_items[all_items['Building Name'] == b_choice].copy()
            
            # --- NEW: AGENT REQUEST SECTION ---
            with st.expander("📄 Step 1: Request Info from Previous Agent", expanded=False):
                st.write("Generate a PDF checklist to send to the previous agent.")
                
                if st.button("Generate Agent Request PDF"):
                    # Get master items for this specific building from the current checklist
                    # (Using the checklist ensures we use the items relevant to THIS building)
                    request_items = items_df['Task Name'].tolist()
                    
                    pdf_file = generate_initial_request_pdf(b_choice, request_items)
                    
                    with open(pdf_file, "rb") as f:
                        st.download_button("Download PDF Checklist", f, file_name=pdf_file)
                    
                    # Generate Mailto Link for Outlook
                    subject = f"Handover Requirements: {b_choice}"
                    body = f"Dear Managing Agent,\n\nPlease find attached the handover checklist for {b_choice}.\n\nKindly provide these items at your earliest convenience.\n\nRegards,\nPretor Group"
                    
                    # URL Encode the strings for the link
                    safe_subject = urllib.parse.quote(subject)
                    safe_body = urllib.parse.quote(body)
                    
                    # Note: We cannot auto-attach files in web links (browser security).
                    mailto_link = f'<a href="mailto:?subject={safe_subject}&body={safe_body}" target="_blank" style="background-color:#FF4B4B; color:white; padding:10px; text-decoration:none; border-radius:5px;">Open Email Draft in Outlook</a>'
                    
                    st.markdown(mailto_link, unsafe_allow_html=True)
                    st.caption("⚠️ Click 'Download' first, then click 'Open Email'. Drag the PDF into the email.")

            st.divider()

            # --- CHECKLIST EDITOR ---
            st.subheader("Step 2: Track Progress")
            if is_finalized:
                st.success(f"🔒 Finalized on {proj_row['Finalized_Date']}")

            # Prepare dataframe for editor
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
            
            # --- WEEKLY REPORT & FINALIZATION ---
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Weekly Report")
                if st.button("Draft Client Email"):
                    received_count = len(items_df[items_df['Received'] == "TRUE"])
                    total = len(items_df)
                    pending_df = items_df[items_df['Received'] == "FALSE"]
                    
                    body = f"Dear Client,\n\nProgress Update for {b_choice}:\n{received_count}/{total} items received.\n\nOutstanding items:\n"
                    for _, row in pending_df.iterrows():
                        body += f"- {row['Task Name']}\n"
                    
                    safe_subject = urllib.parse.quote(f"Update: {b_choice}")
                    safe_body = urllib.parse.quote(body)
                    
                    # Mailto link using the client email from database
                    link = f'<a href="mailto:{client_email}?subject={safe_subject}&body={safe_body}" target="_blank" style="text-decoration:none;">📩 Click here to open Email</a>'
                    st.markdown(link, unsafe_allow_html=True)

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



