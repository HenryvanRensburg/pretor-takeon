import os
import pandas as pd
import streamlit as st
from supabase import create_client, Client
from datetime import datetime

# --- INITIALIZE SUPABASE CONNECTION (ROBUST) ---
url = None
key = None

# 1. Try fetching from Streamlit Secrets (various formats)
if hasattr(st, "secrets"):
    # Scenario A: Flat structure (Recommended)
    # SUPABASE_URL = "..."
    if "SUPABASE_URL" in st.secrets:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    
    # Scenario B: Nested structure (Common in docs)
    # [supabase]
    # url = "..."
    elif "supabase" in st.secrets:
        section = st.secrets["supabase"]
        # Try lowercase then uppercase keys
        url = section.get("url") or section.get("URL") or section.get("supa_url")
        key = section.get("key") or section.get("KEY") or section.get("supa_key")

# 2. Fallback to OS Environment Variables
if not url:
    url = os.environ.get("SUPABASE_URL")
if not key:
    key = os.environ.get("SUPABASE_KEY")

# 3. Final Check & Debugging Help
if not url or not key:
    st.error("🚨 **Connection Error:** Supabase credentials not found.")
    
    # DEBUG INFO (Only shows if connection fails)
    st.write("--- DEBUG INFO ---")
    if hasattr(st, "secrets"):
        st.write("Keys found in Secrets:", list(st.secrets.keys()))
        if "supabase" in st.secrets:
             st.write("Nested [supabase] keys:", list(st.secrets["supabase"].keys()))
    else:
        st.write("No secrets file found.")
    st.write("------------------")
    st.stop()

# Create the client
try:
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error(f"Failed to connect to Supabase. Check your URL/Key format. Error: {e}")
    st.stop()


# --- AUTHENTICATION ---
def login_user(email, password):
    """Attempts login. Returns (user_object, error_message)."""
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return response.user, None
    except Exception as e:
        return None, str(e)

def log_access(user_email):
    try:
        supabase.table("LoginLogs").insert({"user_email": user_email}).execute()
    except Exception as e:
        print(f"Logging failed: {e}")

# --- STORAGE & DOCUMENTS ---
def upload_file_to_supabase(file_obj, file_path):
    """Uploads a file to the 'takeon_docs' bucket and returns the public URL."""
    try:
        bucket_name = "takeon_docs"
        supabase.storage.from_(bucket_name).upload(file_path, file_obj, {"content-type": file_obj.type, "upsert": "true"})
        return supabase.storage.from_(bucket_name).get_public_url(file_path)
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None

def update_document_url(table_name, row_id, url):
    """Generic function to update the 'Document URL' column."""
    try:
        supabase.table(table_name).update({"Document URL": url}).eq("id", row_id).execute()
        return "SUCCESS"
    except Exception as e:
        return str(e)

# --- GENERIC FETCH ---
def get_data(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        data = response.data
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

# --- CHECKLIST ---
def save_checklist_batch(complex_name, edited_df, current_user_email):
    try:
        records = edited_df.to_dict('records')
        for row in records:
            if row.get('id'):
                update_data = {k: v for k, v in row.items() if k != 'id'}
                if str(row.get('Received')).lower() == 'true':
                    update_data['Completed By'] = current_user_email
                supabase.table("Checklist").update(update_data).eq("id", row['id']).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

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
def update_wages_status(c, s): passimport os
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
    st.error("🚨 Supabase Credentials Missing! Check secrets.toml")
    st.stop()

try:
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

# --- AUTHENTICATION ---
def login_user(email, password):
    """Attempts login. Returns (user_object, error_message)."""
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return response.user, None
    except Exception as e:
        return None, str(e)

def log_access(user_email):
    try:
        supabase.table("LoginLogs").insert({"user_email": user_email}).execute()
    except Exception as e:
        print(f"Logging failed: {e}")

# --- STORAGE & DOCUMENTS ---
def upload_file_to_supabase(file_obj, file_path):
    """Uploads a file and returns the public URL."""
    try:
        bucket_name = "takeon_docs"
        supabase.storage.from_(bucket_name).upload(file_path, file_obj, {"content-type": file_obj.type, "upsert": "true"})
        return supabase.storage.from_(bucket_name).get_public_url(file_path)
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None

def update_document_url(table_name, row_id, url):
    """Generic function to link a file URL to a specific record."""
    try:
        supabase.table(table_name).update({"Document URL": url}).eq("id", row_id).execute()
        return "SUCCESS"
    except Exception as e:
        return str(e)

# --- DATA FETCHING ---
def get_data(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        data = response.data
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

# --- CHECKLIST ---
def save_checklist_batch(complex_name, edited_df, current_user_email):
    try:
        records = edited_df.to_dict('records')
        for row in records:
            if row.get('id'):
                update_data = {k: v for k, v in row.items() if k != 'id'}
                if str(row.get('Received')).lower() == 'true':
                    update_data['Completed By'] = current_user_email
                supabase.table("Checklist").update(update_data).eq("id", row['id']).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

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

# --- DEPRECATED / PLACEHOLDERS ---
def add_service_provider(n, t, c): pass 
def add_trustee(c, n, e, p): pass 
def delete_record_by_match(t, c, v): pass
def update_service_provider_date(c, d): pass
def update_wages_status(c, s): pass
def finalize_project_db(c): pass # Removed as requested
