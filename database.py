import os
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# Initialize Supabase
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("Supabase URL and Key must be set in environment variables.")

supabase: Client = create_client(url, key)

# --- GENERIC FETCH ---
def get_data(table_name):
    """Fetch all data from a table and return as DataFrame."""
    try:
        response = supabase.table(table_name).select("*").execute()
        data = response.data
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e:
        print(f"Error fetching {table_name}: {e}")
        return pd.DataFrame()

# --- PROJECTS & BUILDINGS ---
def create_new_building(data):
    """Creates a new project if it doesn't exist."""
    try:
        # Check for duplicates
        existing = supabase.table("Projects").select("*").eq("Complex Name", data["Complex Name"]).execute()
        if existing.data:
            return "EXISTS"
        
        supabase.table("Projects").insert(data).execute()
        return "SUCCESS"
    except Exception as e:
        return str(e)

def update_building_details_batch(complex_name, updates):
    """Updates fields in the Projects table for a specific complex."""
    try:
        supabase.table("Projects").update(updates).eq("Complex Name", complex_name).execute()
        return "SUCCESS"
    except Exception as e:
        return str(e)

def update_project_agent_details(complex_name, agent_name, agent_email):
    """Updates the previous agent details."""
    updates = {"Agent Name": agent_name, "Agent Email": agent_email}
    return update_building_details_batch(complex_name, updates)

def save_broker_details(complex_name, broker_name, broker_email):
    """Updates insurance broker details."""
    updates = {"Insurance Broker Name": broker_name, "Insurance Broker Email": broker_email}
    return update_building_details_batch(complex_name, updates)

def update_email_status(complex_name, column_name, value=None):
    """Updates a specific email sent date column (defaults to today)."""
    date_val = value if value is not None else str(datetime.now().date())
    return update_building_details_batch(complex_name, {column_name: date_val})

def finalize_project_db(complex_name):
    """Marks a project as finalized."""
    return update_building_details_batch(complex_name, {"Status": "Finalized", "Finalized Date": str(datetime.now().date())})

# --- EMPLOYEES / STAFF ---
def add_employee(complex_name, name, surname, id_num, position, salary, payslip_bool, contract_bool, tax_ref_bool):
    """Adds a new employee with specific document flags."""
    data = {
        "Complex Name": complex_name,
        "Name": name,
        "Surname": surname,
        "ID Number": id_num,
        "Position": position,
        "Salary": salary,
        "Payslip Received": payslip_bool,
        "Contract Received": contract_bool,
        "Tax Ref Received": tax_ref_bool
    }
    try:
        supabase.table("Employees").insert(data).execute()
    except Exception as e:
        print(f"Error adding employee: {e}")
        raise e

def update_employee_batch(edited_df):
    """Updates employee records from the grid."""
    try:
        records = edited_df.to_dict('records')
        for row in records:
            row_id = row.get('id')
            if row_id:
                update_data = {k: v for k, v in row.items() if k != 'id'}
                supabase.table("Employees").update(update_data).eq("id", row_id).execute()
        return "SUCCESS"
    except Exception as e:
        return str(e)

# --- COUNCIL ---
def add_council_account(complex_name, acc_num, service, balance):
    """Adds a council account."""
    data = {
        "Complex Name": complex_name,
        "Account Number": acc_num,
        "Service": service,
        "Balance": balance
    }
    try:
        supabase.table("Council").insert(data).execute()
    except Exception as e:
        print(f"Error adding council: {e}")

def update_council_batch(edited_df):
    """Updates council records from the grid."""
    try:
        records = edited_df.to_dict('records')
        for row in records:
            row_id = row.get('id')
            if row_id:
                update_data = {k: v for k, v in row.items() if k != 'id'}
                supabase.table("Council").update(update_data).eq("id", row_id).execute()
        return "SUCCESS"
    except Exception as e:
        return str(e)

# --- ARREARS / DEBT COLLECTION ---
def add_arrears_item(complex_name, unit, amount, att_name, att_email, att_phone):
    """Adds a new arrears record."""
    data = {
        "Complex Name": complex_name,
        "Unit Number": unit,
        "Outstanding Amount": amount,
        "Attorney Name": att_name,
        "Attorney Email": att_email,
        "Attorney Phone": att_phone
    }
    try:
        supabase.table("Arrears").insert(data).execute()
    except Exception as e:
        print(f"Error adding arrears: {e}")
        raise e

def update_arrears_batch(edited_df):
    """Updates arrears records from the grid."""
    try:
        records = edited_df.to_dict('records')
        for row in records:
            row_id = row.get('id')
            if row_id:
                update_data = {k: v for k, v in row.items() if k != 'id'}
                supabase.table("Arrears").update(update_data).eq("id", row_id).execute()
        return "SUCCESS"
    except Exception as e:
        return str(e)

# --- CHECKLIST ---
def save_checklist_batch(complex_name, edited_df):
    """Updates checklist items."""
    try:
        records = edited_df.to_dict('records')
        for row in records:
            # Assuming uniqueness by Task Name + Complex Name or ID. 
            # Ideally Checklist has an ID.
            row_id = row.get('id')
            if row_id:
                update_data = {k: v for k, v in row.items() if k != 'id'}
                supabase.table("Checklist").update(update_data).eq("id", row_id).execute()
        return "SUCCESS"
    except Exception as e:
        return str(e)

# --- MASTER ITEMS ---
def add_master_item(task_name, category, responsibility, heading):
    """Adds item to Master table."""
    try:
        data = {"Task Name": task_name, "Category": category, "Responsibility": responsibility, "Heading": heading}
        supabase.table("Master").insert(data).execute()
    except Exception as e:
        print(e)

# --- GLOBAL SETTINGS ---
def save_global_settings(settings_dict):
    """Updates the Settings table."""
    try:
        # Clear existing and insert new (or update if you have fixed IDs)
        # Simple approach: Delete all, Insert all
        supabase.table("Settings").delete().neq("id", 0).execute() 
        
        for dept, email in settings_dict.items():
            supabase.table("Settings").insert({"Department": dept, "Email": email}).execute()
    except Exception as e:
        print(e)

# --- MISC / PLACEHOLDERS (To prevent import errors) ---
def add_service_provider(name, type, contact):
    pass # Add implementation if needed

def add_trustee(complex, name, email, phone):
    pass # Add implementation if needed

def delete_record_by_match(table, col, val):
    try:
        supabase.table(table).delete().eq(col, val).execute()
    except:
        pass

def update_service_provider_date(complex, date):
    pass

def update_wages_status(complex, status):
    pass
