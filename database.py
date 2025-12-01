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

# --- AUTHENTICATION ---
def login_user(email, password):
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return response.user, None
    except Exception as e:
        return None, str(e)

def log_access(user_email):
    try:
        supabase.table("LoginLogs").insert({"user_email": user_email}).execute()
    except Exception as e:
        pass

# --- STORAGE ---
def upload_file_to_supabase(file_obj, file_path):
    try:
        bucket_name = "takeon_docs"
        supabase.storage.from_(bucket_name).upload(file_path, file_obj, {"content-type": file_obj.type, "upsert": "true"})
        return supabase.storage.from_(bucket_name).get_public_url(file_path)
    except Exception as e:
        return None

def update_document_url(table_name, row_id, url):
    try:
        supabase.table(table_name).update({"Document URL": url}).eq("id", row_id).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

# --- FETCH ---
def get_data(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        data = response.data
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e: return pd.DataFrame()

# --- CHECKLIST LOGIC (FIXED) ---
def find_val(row, targets, default=""):
    """Finds value in row dictionary by checking multiple key variations."""
    # 1. Exact match
    for t in targets:
        if t in row: return row[t]
    
    # 2. Case-insensitive & stripped match
    row_lower = {k.lower().strip(): v for k, v in row.items()}
    for t in targets:
        t_clean = t.lower().strip()
        if t_clean in row_lower: return row_lower[t_clean]
    
    return default

def initialize_checklist(complex_name, building_type_code):
    """
    Copies items from Master to Checklist.
    Logic:
    1. Deletes existing items for this complex to prevent duplicates.
    2. Reads ALL Master items.
    3. Filters: If Category matches Building Type OR is 'Both' OR is Empty.
    4. Inserts into Checklist.
    """
    try:
        # 1. Cleanup old data
        supabase.table("Checklist").delete().eq("Complex Name", complex_name).execute()
        
        # 2. Get Master
        master_res = supabase.table("Master").select("*").execute()
        master_items = master_res.data
        if not master_items: return "NO_MASTER_DATA"

        new_rows = []
        for item in master_items:
            # ROBUST MAPPING
            # Use wide net for keys to catch "responsibility", "Responsibility", etc.
            cat  = find_val(item, ["Category", "category", "Cat"], "Both")
            name = find_val(item, ["Task Name", "task_name", "Task", "task"])
            head = find_val(item, ["Heading", "heading", "Task Heading"], "General")
            resp = find_val(item, ["Responsibility", "responsibility", "Resp", "Action By"], "Both") # Default to Both if missing
            time = find_val(item, ["Timing", "timing", "Time"], "Immediate")

            # Handle None values
            if cat is None: cat = "Both"
            if resp is None: resp = "Both"
            
            # FILTER LOGIC
            b_type = building_type_code.lower().strip() # 'bc' or 'hoa'
            i_cat = str(cat).lower().strip()
            
            # Include if:
            # 1. Master item category is 'both'
            # 2. Master item category is empty/null (assume applies to all)
            # 3. Master item category matches the building type
            is_match = False
            if "both" in i_cat or i_cat == "" or i_cat == "none": is_match = True
            elif b_type == "bc" and ("body" in i_cat or "bc" in i_cat): is_match = True
            elif b_type == "hoa" and "hoa" in i_cat: is_match = True

            if is_match and name:
                new_rows.append({
                    "Complex Name": complex_name,
                    "Task Name": name,
                    "Task Heading": head,
                    "Responsibility": resp,
                    "Timing": time,
                    "Received": False,
                    "Delete": False
                })

        # 3. Insert
        if new_rows:
            # Split into chunks of 100 to avoid timeouts
            chunk_size = 100
            for i in range(0, len(new_rows), chunk_size):
                batch = new_rows[i:i + chunk_size]
                supabase.table("Checklist").insert(batch).execute()
            return "SUCCESS"
        
        return "NO_MATCHING_ITEMS"

    except Exception as e:
        return f"Error: {str(e)}"

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

# --- OTHER CRUD ---
def create_new_building(data):
    try:
        existing = supabase.table("Projects").select("*").eq("Complex Name", data["Complex Name"]).execute()
        if existing.data: return "EXISTS"
        supabase.table("Projects").insert(data).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

def update_building_details_batch(complex_name, updates):
    try: supabase.table("Projects").update(updates).eq("Complex Name", complex_name).execute(); return "SUCCESS"
    except Exception as e: return str(e)

def update_project_agent_details(c, n, e): return update_building_details_batch(c, {"Agent Name": n, "Agent Email": e})
def save_broker_details(c, n, e): return update_building_details_batch(c, {"Insurance Broker Name": n, "Insurance Broker Email": e})
def update_email_status(c, col, v=None): return update_building_details_batch(c, {col: v if v else str(datetime.now().date())})
def finalize_project_db(c): return update_building_details_batch(c, {"Status": "Finalized", "Finalized Date": str(datetime.now().date())})

# --- SUB-TABLES ---
def add_employee(c, n, s, i, p, sal, pb, cb, tb):
    try: supabase.table("Employees").insert({"Complex Name": c, "Name": n, "Surname": s, "ID Number": i, "Position": p, "Salary": sal, "Payslip Received": pb, "Contract Received": cb, "Tax Ref Received": tb}).execute()
    except Exception as e: raise e
def update_employee_batch(df):
    try:
        for r in df.to_dict('records'): 
            if r.get('id'): supabase.table("Employees").update({k:v for k,v in r.items() if k!='id'}).eq("id", r['id']).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

def add_council_account(c, a, s, b):
    try: supabase.table("Council").insert({"Complex Name": c, "Account Number": a, "Service": s, "Balance": b}).execute()
    except Exception as e: print(e)
def update_council_batch(df):
    try:
        for r in df.to_dict('records'): 
            if r.get('id'): supabase.table("Council").update({k:v for k,v in r.items() if k!='id'}).eq("id", r['id']).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

def add_arrears_item(c, u, a, n, e, p):
    try: supabase.table("Arrears").insert({"Complex Name": c, "Unit Number": u, "Outstanding Amount": a, "Attorney Name": n, "Attorney Email": e, "Attorney Phone": p}).execute()
    except Exception as e: raise e
def update_arrears_batch(df):
    try:
        for r in df.to_dict('records'): 
            if r.get('id'): supabase.table("Arrears").update({k:v for k,v in r.items() if k!='id'}).eq("id", r['id']).execute()
        return "SUCCESS"
    except Exception as e: return str(e)

def add_master_item(n, cat, resp, head, time):
    try: supabase.table("Master").insert({"Task Name": n, "Category": cat, "Responsibility": resp, "Heading": head, "Timing": time}).execute()
    except Exception as e: print(e)

def save_global_settings(s):
    try:
        supabase.table("Settings").delete().neq("id", 0).execute()
        for k, v in s.items(): supabase.table("Settings").insert({"Department": k, "Email": v}).execute()
    except Exception as e: print(e)

# --- PLACEHOLDERS ---
def add_service_provider(n, t, c): pass 
def add_trustee(c, n, e, p): pass 
def delete_record_by_match(t, c, v): pass
def update_service_provider_date(c, d): pass
def update_wages_status(c, s): pass
