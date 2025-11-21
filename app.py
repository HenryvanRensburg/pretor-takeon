import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from fpdf import FPDF
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURATION ---
DB_FILE = "pretor_takeon.db"

# --- DATABASE FUNCTIONS ---
def init_db():
    """Creates the database tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Table for the Master Schedule template
    c.execute('''CREATE TABLE IF NOT EXISTS master_schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL
                )''')
    
    # Table for Buildings/Complexes
    c.execute('''CREATE TABLE IF NOT EXISTS buildings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    client_email TEXT,
                    is_finalized BOOLEAN DEFAULT 0,
                    finalized_date TEXT
                )''')
    
    # Table for Items specific to a Building
    c.execute('''CREATE TABLE IF NOT EXISTS building_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    building_id INTEGER,
                    task_name TEXT,
                    received BOOLEAN DEFAULT 0,
                    date_received TEXT,
                    notes TEXT,
                    FOREIGN KEY (building_id) REFERENCES buildings (id)
                )''')
    conn.commit()
    conn.close()

def get_master_schedule():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT * FROM master_schedule", conn)
    conn.close()
    return df

def add_master_item(task_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO master_schedule (task_name) VALUES (?)", (task_name,))
    conn.commit()
    conn.close()

def delete_master_item(item_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM master_schedule WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

def create_new_building(name, email):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 1. Create Building
    c.execute("INSERT INTO buildings (name, client_email) VALUES (?, ?)", (name, email))
    building_id = c.lastrowid
    
    # 2. Copy Master Schedule to this Building
    master_df = get_master_schedule()
    for _, row in master_df.iterrows():
        c.execute('''INSERT INTO building_items (building_id, task_name, received, date_received, notes)
                     VALUES (?, ?, 0, NULL, '')''', (building_id, row['task_name']))
    
    conn.commit()
    conn.close()
    return building_id

def get_building_items(building_id):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT * FROM building_items WHERE building_id = ?", conn, params=(building_id,))
    conn.close()
    return df

def update_building_item(item_id, received, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    date_str = datetime.now().strftime("%Y-%m-%d") if received else None
    
    # Only update the date if it's newly checked
    c.execute('''UPDATE building_items 
                 SET received = ?, notes = ?, date_received = CASE WHEN ? = 1 THEN ? ELSE NULL END 
                 WHERE id = ?''', (received, notes, received, date_str, item_id))
    conn.commit()
    conn.close()

def finalize_project(building_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    final_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE buildings SET is_finalized = 1, finalized_date = ? WHERE id = ?", (final_date, building_id))
    conn.commit()
    conn.close()
    return final_date

# --- PDF GENERATION ---
def generate_pdf(building_name, items_df, final_date):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Final Take-On Report: {building_name}", ln=1, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Finalized on: {final_date}", ln=1, align='C')
    pdf.ln(10)
    
    # Table Header
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(80, 10, "Item", 1)
    pdf.cell(30, 10, "Date Rec.", 1)
    pdf.cell(80, 10, "Notes", 1)
    pdf.ln()
    
    # Table Rows
    pdf.set_font("Arial", size=10)
    for _, row in items_df.iterrows():
        status_date = row['date_received'] if row['received'] else "Pending"
        pdf.cell(80, 10, str(row['task_name'])[:40], 1)
        pdf.cell(30, 10, str(status_date), 1)
        pdf.cell(80, 10, str(row['notes'])[:40], 1)
        pdf.ln()
        
    filename = f"{building_name}_Final_Report.pdf"
    pdf.output(filename)
    return filename

# --- APP LAYOUT ---
def main():
    st.set_page_config(page_title="Pretor Group New Take-On", layout="wide")
    init_db()
    
    st.title("🏢 Pretor Group: New Complex New Take-On")
    
    # Sidebar Navigation
    menu = ["Dashboard", "Master Schedule", "New Building", "Manage Buildings"]
    choice = st.sidebar.selectbox("Menu", menu)
    
    conn = sqlite3.connect(DB_FILE)
    
    # --- DASHBOARD ---
    if choice == "Dashboard":
        st.subheader("Overview")
        buildings = pd.read_sql("SELECT * FROM buildings", conn)
        st.dataframe(buildings)

    # --- MASTER SCHEDULE ---
    elif choice == "Master Schedule":
        st.subheader("Edit Master Checklist Template")
        st.info("Items added here will be copied to NEW buildings created in the future.")
        
        # Add Item
        new_task = st.text_input("Add new checklist item")
        if st.button("Add Item"):
            add_master_item(new_task)
            st.success(f"Added: {new_task}")
            st.rerun()
            
        # Show/Delete Items
        master_df = get_master_schedule()
        for index, row in master_df.iterrows():
            col1, col2 = st.columns([4, 1])
            col1.write(f"• {row['task_name']}")
            if col2.button("Delete", key=row['id']):
                delete_master_item(row['id'])
                st.rerun()

    # --- NEW BUILDING ---
    elif choice == "New Building":
        st.subheader("Onboard New Complex")
        
        b_name = st.text_input("Building / Complex Name")
        b_email = st.text_input("Client Email Address")
        
        if st.button("Create Project"):
            if b_name:
                create_new_building(b_name, b_email)
                st.success(f"Created {b_name} and copied Master Schedule!")
            else:
                st.error("Please enter a name.")

    # --- MANAGE BUILDINGS (MAIN WORKFLOW) ---
    elif choice == "Manage Buildings":
        st.subheader("Update Progress")
        
        # Select Building
        buildings = pd.read_sql("SELECT id, name, is_finalized FROM buildings", conn)
        if buildings.empty:
            st.warning("No buildings found. Go to 'New Building' to create one.")
        else:
            building_choice = st.selectbox("Select Complex", buildings['name'])
            building_id = buildings[buildings['name'] == building_choice]['id'].values[0]
            is_finalized = buildings[buildings['name'] == building_choice]['is_finalized'].values[0]
            
            if is_finalized:
                st.success("🔒 This project is finalized.")
                
            # Load Items
            items_df = get_building_items(building_id)
            
            # Display as an editable data editor
            edited_df = st.data_editor(
                items_df,
                column_config={
                    "received": st.column_config.CheckboxColumn("Received?", help="Check if received"),
                    "task_name": "Item Description",
                    "date_received": "Date",
                    "notes": "Notes",
                    "id": None, # Hide ID
                    "building_id": None # Hide Building ID
                },
                disabled=["task_name", "date_received"], # Can't edit name or auto-date directly
                hide_index=True,
                key="editor"
            )
            
            # Save Changes Button
            if st.button("Save Changes"):
                # Compare edited_df with original DB state and update
                for index, row in edited_df.iterrows():
                    update_building_item(row['id'], row['received'], row['notes'])
                st.success("Progress Saved!")
                st.rerun()

            st.divider()
            
            # --- AUTOMATION ACTIONS ---
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Weekly Report")
                if st.button("Generate Email Draft"):
                    # Calculating progress
                    total = len(items_df)
                    done = len(items_df[items_df['received'] == 1])
                    remaining_df = items_df[items_df['received'] == 0]
                    
                    report_text = f"""
                    Subject: Progress Update: {building_choice}
                    
                    Dear Client,
                    
                    Here is the weekly update for the take-on of {building_choice}.
                    
                    Progress: {done}/{total} items received.
                    
                    We are still awaiting the following items:
                    """
                    for _, row in remaining_df.iterrows():
                        report_text += f"\n- {row['task_name']}"
                        
                    st.text_area("Copy this text to your email:", report_text, height=300)
                    st.info("NOTE: To send emails automatically, SMTP settings must be configured in the code.")

            with col2:
                st.subheader("Finalize Project")
                if not is_finalized:
                    # Check if all items are done
                    if items_df['received'].all():
                        if st.button("Finalize & Generate PDF"):
                            final_date = finalize_project(building_id)
                            pdf_file = generate_pdf(building_choice, items_df, final_date)
                            
                            with open(pdf_file, "rb") as f:
                                st.download_button(
                                    label="Download Final PDF",
                                    data=f,
                                    file_name=pdf_file,
                                    mime="application/pdf"
                                )
                            st.balloons()
                    else:
                        st.warning("You cannot finalize until all items are marked as received.")
                else:
                     st.info("Project already finalized.")

    conn.close()

if __name__ == "__main__":
    main()