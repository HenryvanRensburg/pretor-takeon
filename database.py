import os
import pandas as pd
import streamlit as st
from supabase import create_client, Client
from datetime import datetime

# --- INITIALIZE SUPABASE ---
try:
    if "SUPABASE_URL" in st.secrets and "SUPABASE_KEY" in st.secrets:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    else:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
except (FileNotFoundError, KeyError):
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    st.error("🚨 Supabase Credentials Missing!")
    st.stop()

try:
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

# --- AUTHENTICATION & LOGGING ---
def login_user(email, password):
    """Attempts to log the user in via Supabase Auth."""
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return response.user
    except Exception as e:
        return None

def log_access(user_email):
    """Records the login time and user in the database."""
    try:
        supabase.table("LoginLogs").insert({"user_email": user_email}).execute()
    except Exception as e:
        print(f"Logging failed: {e}")

# --- GENERIC FETCH ---
def get_data(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        data = response.data
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

# --- CHECKLIST (UPDATED WITH USER TRACKING) ---
def save_checklist_batch(complex_name, edited_df, current_user_email):
    """Updates checklist items and records WHO completed them."""
    try:
        records = edited_df.to_dict('records')
        for row in records:
            if row.get('id'):
                update_data = {k: v for k, v in row.items() if k != 'id'}
                
                # If item is marked Received, tag the user
                if str(row.get('Received')).lower() == 'true':
                    update_data['Completed By'] = current_user_email
                
                supabase.table("Checklist").update(update_data).eq("id", row['id']).execute()
        return "SUCCESS"
    except Exception as e:
        return str(e)

# --- PROJECTS ---
def create_new_building(data):
    try:
        existing = supabase.table("Projects").select("*").eq("Complex Name", data["Complex Name"]).execute()
        if existing.data: return "EXISTS"
        supabase.table("Projects").insert(data).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

def update_building_details_batch(complex_name, updates):
    try:
        supabase.table("Projects").update(updates).eq("Complex Name", complex_name).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

def update_project_agent_details(complex_name, agent_name, agent_email):
    return update_building_details_batch(complex_name, {"Agent Name": agent_name, "Agent Email": agent_email})

def save_broker_details(complex_name, broker_name, broker_email):
    return update_building_details_batch(complex_name, {"Insurance Broker Name": broker_name, "Insurance Broker Email": broker_email})

def update_email_status(complex_name, column_name, value=None):
    date_val = value if value is not None else str(datetime.now().date())
    return update_building_details_batch(complex_name, {column_name: date_val})

def finalize_project_db(complex_name):
    return update_building_details_batch(complex_name, {"Status": "Finalized", "Finalized Date": str(datetime.now().date())})

# --- EMPLOYEES ---
def add_employee(complex_name, name, surname, id_num, position, salary, payslip_bool, contract_bool, tax_ref_bool):
    try:
        data = {
            "Complex Name": complex_name, "Name": name, "Surname": surname, "ID Number": id_num,
            "Position": position, "Salary": salary, "Payslip Received": payslip_bool,
            "Contract Received": contract_bool, "Tax Ref Received": tax_ref_bool
        }
        supabase.table("Employees").insert(data).execute()
    except Exception as e: raise e

def update_employee_batch(edited_df):
    try:
        records = edited_df.to_dict('records')
        for row in records:
            if row.get('id'):
                update_data = {k: v for k, v in row.items() if k != 'id'}
                supabase.table("Employees").update(update_data).eq("id", row['id']).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

# --- COUNCIL ---
def add_council_account(complex_name, acc_num, service, balance):
    try:
        supabase.table("Council").insert({"Complex Name": complex_name, "Account Number": acc_num, "Service": service, "Balance": balance}).execute()
    except Exception as e: print(f"Error adding council: {e}")

def update_council_batch(edited_df):
    try:
        records = edited_df.to_dict('records')
        for row in records:
            if row.get('id'):
                update_data = {k: v for k, v in row.items() if k != 'id'}
                supabase.table("Council").update(update_data).eq("id", row['id']).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

# --- ARREARS ---
def add_arrears_item(complex_name, unit, amount, att_name, att_email, att_phone):
    try:
        data = {
            "Complex Name": complex_name, "Unit Number": unit, "Outstanding Amount": amount,
            "Attorney Name": att_name, "Attorney Email": att_email, "Attorney Phone": att_phone
        }
        supabase.table("Arrears").insert(data).execute()
    except Exception as e: raise e

def update_arrears_batch(edited_df):
    try:
        records = edited_df.to_dict('records')
        for row in records:
            if row.get('id'):
                update_data = {k: v for k, v in row.items() if k != 'id'}
                supabase.table("Arrears").update(update_data).eq("id", row['id']).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

# --- MASTER & SETTINGS ---
def add_master_item(task_name, category, responsibility, heading):
    try:
        supabase.table("Master").insert({"Task Name": task_name, "Category": category, "Responsibility": responsibility, "Heading": heading}).execute()
    except Exception as e: print(e)

def save_global_settings(settings_dict):
    try:
        supabase.table("Settings").delete().neq("id", 0).execute() 
        for dept, email in settings_dict.items():
            supabase.table("Settings").insert({"Department": dept, "Email": email}).execute()
    except Exception as e: print(e)

# --- PLACEHOLDERS ---
def add_service_provider(n, t, c): pass 
def add_trustee(c, n, e, p): pass 
def delete_record_by_match(t, c, v): pass
def update_service_provider_date(c, d): pass
def update_wages_status(c, s): pass
