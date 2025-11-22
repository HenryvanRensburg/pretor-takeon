import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURATION ---
# We look for the credentials in Streamlit's "Secrets" storage
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# --- GOOGLE SHEETS CONNECTION ---
def get_google_sheet():
    """Connects to Google Sheets using credentials from Streamlit Secrets."""
    try:
        # Load credentials from Streamlit secrets
        credentials_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        
        # Open the specific Google Sheet by name (You must create this sheet first!)
        sheet = client.open("Pretor TakeOn DB")
        return sheet
    except Exception as e:
        st.error(f"Could not connect to Google Sheets. Error: {e}")
        return None

# --- DATA FUNCTIONS ---

def get_data(worksheet_name):
    sh = get_google_sheet()
    if sh:
        worksheet = sh.worksheet(worksheet_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    return pd.DataFrame()

def add_master_item(task_name):
    sh = get_google_sheet()
    ws = sh.worksheet("Master")
    ws.append_row([task_name])

def delete_master_item(task_name):
    sh = get_google_sheet()
    ws = sh.worksheet("Master")
    cell = ws.find(task_name)
    ws.delete_rows(cell.row)

def create_new_building(name, email):
    sh = get_google_sheet()
    
    # 1. Add to Projects Tab
    ws_projects = sh.worksheet("Projects")
    # Columns: Building Name, Email, Is_Finalized, Finalized_Date
    ws_projects.append_row([name, email, "FALSE", ""])
    
    # 2. Read Master Schedule (Improved Logic)
    ws_master = sh.worksheet("Master")
    
    # Get all values from Column A
    all_values = ws_master.col_values(1)
    
    # Slicing: [1:] means "start from the 2nd item and take the rest"
    # This automatically skips the header (row 1), whatever it is named.
    if len(all_values) > 1:
        master_tasks = all_values[1:] 
    else:
        master_tasks = [] # Sheet is empty
    
    # 3. Add items to Checklist Tab
    ws_checklist = sh.worksheet("Checklist")
    
    new_rows = []
    for task in master_tasks:
        # distinct check to ensure we don't copy empty blank lines
        if task and str(task).strip() != "": 
            # [Building Name, Task Name, Received, Date, Notes]
            new_rows.append([name, task, "FALSE", "", ""])
    
    if new_rows:
        ws_checklist.append_rows(new_rows)
        return True # Return success
    else:
        return False # Return failure (no tasks found)

def update_checklist_item(building_name, task_name, received, notes):
    sh = get_google_sheet()
    ws = sh.worksheet("Checklist")
    
    # Find the row that matches both Building Name and Task Name
    # Note: This search can be slow if the sheet is huge. 
    # For a production app, we usually use unique IDs, but Name is easier for now.
    
    cells = ws.findall(building_name)
    target_row = None
    for cell in cells:
        # Check if the task name in this row matches
        task_cell_val = ws.cell(cell.row, 2).value # Column 2 is Task Name
        if task_cell_val == task_name:
            target_row = cell.row
            break
    
    if target_row:
        date_str = datetime.now().strftime("%Y-%m-%d") if received else ""
        # Update Received (Col 3), Date (Col 4), Notes (Col 5)
        ws.update_cell(target_row, 3, "TRUE" if received else "FALSE")
        ws.update_cell(target_row, 4, date_str)
        ws.update_cell(target_row, 5, notes)

def finalize_project_db(building_name):
    sh = get_google_sheet()
    ws = sh.worksheet("Projects")
    cell = ws.find(building_name)
    final_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Update Is_Finalized (Col 3) and Date (Col 4)
    ws.update_cell(cell.row, 3, "TRUE")
    ws.update_cell(cell.row, 4, final_date)
    return final_date

# --- PDF GENERATION (Same as before) ---
def generate_pdf(building_name, items_df, final_date):
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
        status_date = row['Date Received'] if row['Received'] == "TRUE" else "Pending"
        pdf.cell(80, 10, str(row['Task Name'])[:40], 1)
        pdf.cell(30, 10, str(status_date), 1)
        pdf.cell(80, 10, str(row['Notes'])[:40], 1)
        pdf.ln()
    filename = f"{building_name}_Final_Report.pdf"
    pdf.output(filename)
    return filename

# --- MAIN APP LAYOUT ---
def main():
    st.set_page_config(page_title="Pretor Group Take-On", layout="wide")
    
    st.title("🏢 Pretor Group: Cloud Take-On Manager")

    # Sidebar
    menu = ["Dashboard", "Master Schedule", "New Building", "Manage Buildings"]
    choice = st.sidebar.selectbox("Menu", menu)
    
    # --- DASHBOARD ---
    if choice == "Dashboard":
        st.subheader("Active Projects Overview")
        df = get_data("Projects")
        if not df.empty:
            st.dataframe(df)
        else:
            st.info("No projects found. Create one in 'New Building'.")

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
                # We call the function and check the result
                success = create_new_building(b_name, b_email)
                
                if success:
                    st.success(f"Project {b_name} created and Master Schedule copied!")
                else:
                    st.warning(f"Project {b_name} created, BUT Master Schedule was empty. Please add items to Master Schedule.")
            else:
                st.error("Please enter a building name.")

    # --- MANAGE BUILDINGS ---
    elif choice == "Manage Buildings":
        projects = get_data("Projects")
        if projects.empty:
            st.warning("No projects yet.")
        else:
            b_choice = st.selectbox("Select Complex", projects['Building Name'])
            
            # Get Project Status
            proj_row = projects[projects['Building Name'] == b_choice].iloc[0]
            is_finalized = str(proj_row['Is_Finalized']).upper() == "TRUE"
            
            if is_finalized:
                st.success(f"🔒 Finalized on {proj_row['Finalized_Date']}")

            # Get Checklist Items
            all_items = get_data("Checklist")
            # Filter for this building
            items_df = all_items[all_items['Building Name'] == b_choice]
            
            # Display Editor
            # We construct a simpler dataframe for the editor
            display_df = items_df[['Task Name', 'Received', 'Date Received', 'Notes']].copy()
            
            # Convert "TRUE"/"FALSE" strings to Booleans for the checkbox to work
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
                # We must find what changed. 
                # For simplicity in this version, we iterate and update.
                for index, row in edited_df.iterrows():
                    # Compare with original logic or just push updates
                    # Convert boolean back to string for storage logic
                    update_checklist_item(b_choice, row['Task Name'], row['Received'], row['Notes'])
                st.success("Saved to Google Sheets!")
                st.rerun()
            
            st.divider()
            
            # Weekly Report
            if st.button("Generate Weekly Report Email"):
                received_count = len(items_df[items_df['Received'] == "TRUE"])
                total = len(items_df)
                pending_df = items_df[items_df['Received'] == "FALSE"]
                
                email_text = f"""Subject: Progress Update: {b_choice}\n\nProgress: {received_count}/{total} items received.\n\nPending Items:\n"""
                for _, row in pending_df.iterrows():
                    email_text += f"- {row['Task Name']}\n"
                st.text_area("Email Draft", email_text, height=200)
            
            # Finalize
            if not is_finalized and st.button("Finalize Project"):
                 # Check if all true
                 if not any(items_df['Received'] == "FALSE"):
                     date = finalize_project_db(b_choice)
                     pdf = generate_pdf(b_choice, items_df, date)
                     with open(pdf, "rb") as f:
                        st.download_button("Download PDF", f, file_name=pdf)
                     st.balloons()
                 else:
                     st.error("Complete all items first.")

if __name__ == "__main__":
    main()

