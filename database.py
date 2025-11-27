import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
from utils import calculate_financial_periods  # Import helper

# --- CONFIGURATION ---
if "supabase" in st.secrets:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
else:
    st.error("Supabase secrets not found. Please check your secrets.toml file.")
    st.stop()

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- READ FUNCTIONS ---
@st.cache_data(ttl=20)
def get_data(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        df = pd.DataFrame(response.data)
        # Handle empty dataframes by defining required columns to prevent KeyErrors
        if df.empty:
            if table_name == "Checklist":
                return pd.DataFrame(columns=["Complex Name", "Task Name", "Received", "Date Received", "Notes", "Responsibility", "Delete", "Completed By", "Task Heading"])
            if table_name == "Projects":
                return pd.DataFrame(columns=["Complex Name", "Type", "Previous Agents", "Take On Date", "No of Units", "Mgmt Fees", "Erf No", "SS Number", "CSOS Number", "VAT Number", "Tax Number", "Year End", "Auditor", "Last Audit Year", "Building Code", "Expense Code", "Physical Address", "Assigned Manager", "Date Doc Requested", "Is_Finalized", "Client Email", "Finalized Date", "Agent Name", "Agent Email", "Manager Email", "Assistant Name", "Assistant Email", "Bookkeeper Name", "Bookkeeper Email", "UIF Number", "COIDA Number", "SARS PAYE Number", "TakeOn Name", "TakeOn Email", "Wages Sent Date", "Wages Employee Count", "SARS Sent Date", "Trustee Email Sent Date", "Insurance Broker Name", "Insurance Broker Email", "Broker Email Sent Date", "Internal Ins Email Sent Date", "Debt Collection Email Sent Date", "Council Email Sent Date", "Fee Confirmation Email Sent Date"])
            if table_name == "ServiceProviders":
                return pd.DataFrame(columns=["Complex Name", "Provider Name", "Service Type", "Email", "Phone", "Date Emailed"])
            if table_name == "Employees":
                return pd.DataFrame(columns=["Complex Name", "Name", "Surname", "ID Number", "PAYE Number", "Contract Received", "Payslip Received", "ID Copy Received", "Bank Confirmation"])
            if table_name == "Arrears":
                return pd.DataFrame(columns=["Complex Name", "Unit Number", "Outstanding Amount", "Attorney Name", "Attorney Email", "Attorney Phone"])
            if table_name == "CouncilAccounts":
                return pd.DataFrame(columns=["Complex Name", "Account Number", "Service Covered", "Current Balance"])
            if table_name == "Trustees":
                return pd.DataFrame(columns=["Complex Name", "Name", "Surname", "Email", "Phone"])
            if table_name == "Settings":
                return pd.DataFrame(columns=["Department", "Email"])
        return df
    except Exception as e:
        return pd.DataFrame()

def clear_cache():
    st.cache_data.clear()

# --- WRITE/UPDATE FUNCTIONS ---
def add_master_item(task_name, category, default_resp, task_heading):
    supabase.table("Master").insert({"Task Name": task_name, "Category": category, "Default Responsibility": default_resp, "Task Heading": task_heading}).execute()
    clear_cache()

def add_service_provider(complex_name, name, service, email, phone):
    supabase.table("ServiceProviders").insert({"Complex Name": complex_name, "Provider Name": name, "Service Type": service, "Email": email, "Phone": phone, "Date Emailed": ""}).execute()
    clear_cache()

def add_employee(complex_name, name, surname, id_num, position, salary, payslip_bool, contract_bool, tax_ref_bool):
    """
    Adds a new employee with the specific fields required for the wages handover.
    """
    data = {
        "Complex Name": complex_name,
        "Name": name,
        "Surname": surname,
        "ID Number": id_num,
        "Position": position,
        "Salary": salary,
        "Payslip Received": payslip_bool,   # Boolean
        "Contract Received": contract_bool, # Boolean
        "Tax Ref Received": tax_ref_bool    # Boolean
    }
    
    # Execute the insert
    try:
        supabase.table("Employees").insert(data).execute()
    except Exception as e:
        print(f"Error adding employee: {e}")
        raise e

def add_arrears_item(complex_name, unit, amount, attorney_name, attorney_email, attorney_phone):
    supabase.table("Arrears").insert({"Complex Name": complex_name, "Unit Number": unit, "Outstanding Amount": str(amount), "Attorney Name": attorney_name, "Attorney Email": attorney_email, "Attorney Phone": attorney_phone}).execute()
    clear_cache()

def add_council_account(complex_name, account_num, service, balance):
    supabase.table("CouncilAccounts").insert({"Complex Name": complex_name, "Account Number": account_num, "Service Covered": service, "Current Balance": str(balance)}).execute()
    clear_cache()

def add_trustee(complex_name, name, surname, email, phone):
    supabase.table("Trustees").insert({"Complex Name": complex_name, "Name": name, "Surname": surname, "Email": email, "Phone": phone}).execute()
    clear_cache()

def delete_record_by_match(table_name, match_dict):
    try:
        query = supabase.table(table_name).delete()
        for k, v in match_dict.items():
            query = query.eq(k, v)
        query.execute()
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Delete failed: {e}")
        return False

def save_global_settings(settings_dict):
    supabase.table("Settings").delete().neq("Department", "XYZ").execute()
    rows = [{"Department": k, "Email": v} for k, v in settings_dict.items()]
    supabase.table("Settings").insert(rows).execute()
    clear_cache()
    return True

# --- COMPLEX LOGIC UPDATES ---
def create_new_building(data_dict):
    existing = supabase.table("Projects").select("id").eq("Complex Name", data_dict["Complex Name"]).execute()
    if existing.data: return "EXISTS"
    
    # Format dates for API
    data_dict["Take On Date"] = str(data_dict["Take On Date"])
    data_dict["Date Doc Requested"] = str(data_dict["Date Doc Requested"])
    supabase.table("Projects").insert(data_dict).execute()
    
    master_data = get_data("Master")
    if master_data.empty: return "NO_MASTER"
    
    curr_fin, historic_block, bank_req, owner_bal_req, closing_bal_req = calculate_financial_periods(data_dict["Take On Date"], data_dict["Year End"])
    day_before_date = (datetime.strptime(data_dict["Take On Date"], "%Y-%m-%d") - timedelta(days=1)).strftime('%d %B %Y')
    
    checklist_rows = [
        {"Complex Name": data_dict["Complex Name"], "Task Name": curr_fin, "Responsibility": "Previous Agent", "Task Heading": "Financial"},
        {"Complex Name": data_dict["Complex Name"], "Task Name": f"Historic Financial Records: {historic_block}", "Responsibility": "Previous Agent", "Task Heading": "Financial"},
        {"Complex Name": data_dict["Complex Name"], "Task Name": f"Historic General Correspondence: {historic_block}", "Responsibility": "Previous Agent", "Task Heading": "Financial"},
        {"Complex Name": data_dict["Complex Name"], "Task Name": bank_req, "Responsibility": "Previous Agent", "Task Heading": "Financial"},
        {"Complex Name": data_dict["Complex Name"], "Task Name": owner_bal_req, "Responsibility": "Previous Agent", "Task Heading": "Financial"},
        {"Complex Name": data_dict["Complex Name"], "Task Name": closing_bal_req, "Responsibility": "Previous Agent", "Task Heading": "Financial"},
        {"Complex Name": data_dict["Complex Name"], "Task Name": f"Final reconciliation of previous bank account and proof of transfer of funds to be provided on {day_before_date}", "Responsibility": "Previous Agent", "Task Heading": "Financial"},
        {"Complex Name": data_dict["Complex Name"], "Task Name": f"A final trial balance as at {day_before_date}", "Responsibility": "Previous Agent", "Task Heading": "Financial"},
        {"Complex Name": data_dict["Complex Name"], "Task Name": f"The latest cashflow statement as at {day_before_date}", "Responsibility": "Previous Agent", "Task Heading": "Financial"}
    ]

    for _, row in master_data.iterrows():
        raw_cat = str(row.get("Category", "Both")).strip().upper()
        b_type = data_dict["Type"]
        if raw_cat == "BOTH" or raw_cat == "" or (raw_cat == "BC" and b_type == "Body Corporate") or (raw_cat == "HOA" and b_type == "HOA"):
            checklist_rows.append({
                "Complex Name": data_dict["Complex Name"],
                "Task Name": row["Task Name"],
                "Responsibility": row.get("Default Responsibility", "Previous Agent"),
                "Task Heading": row.get("Task Heading", "Take-On")
            })

    if checklist_rows:
        supabase.table("Checklist").insert(checklist_rows).execute()
    clear_cache()
    return "SUCCESS"

def update_building_details_batch(complex_name, updates):
    clean_updates = {k: v for k, v in updates.items() if v is not None}
    supabase.table("Projects").update(clean_updates).eq("Complex Name", complex_name).execute()
    clear_cache()
    return True

def update_project_agent_details(complex_name, name, email):
    supabase.table("Projects").update({"Agent Name": name, "Agent Email": email}).eq("Complex Name", complex_name).execute()
    clear_cache()

def save_broker_details(complex_name, name, email):
    supabase.table("Projects").update({"Insurance Broker Name": name, "Insurance Broker Email": email}).eq("Complex Name", complex_name).execute()
    clear_cache()

def update_email_status(complex_name, field, value=None):
    """Generic updater for email status fields"""
    if value is None:
        value = datetime.now().strftime("%Y-%m-%d")
    supabase.table("Projects").update({field: value}).eq("Complex Name", complex_name).execute()
    clear_cache()
    return True

def update_service_provider_date(complex_name, provider_name):
    today = datetime.now().strftime("%Y-%m-%d")
    supabase.table("ServiceProviders").update({"Date Emailed": today}).match({"Complex Name": complex_name, "Provider Name": provider_name}).execute()
    clear_cache()
    return True

def update_wages_status(complex_name, count):
    today = datetime.now().strftime("%Y-%m-%d")
    supabase.table("Projects").update({"Wages Sent Date": today, "Wages Employee Count": str(count)}).eq("Complex Name", complex_name).execute()
    clear_cache()
    return True

def save_checklist_batch(complex_name, edited_df):
    # Deletes
    if 'Delete' in edited_df.columns:
        to_delete = edited_df[edited_df['Delete'] == True]
        for _, row in to_delete.iterrows():
            supabase.table("Checklist").delete().match({"Complex Name": complex_name, "Task Name": row['Task Name']}).execute()
    
    # Updates
    to_update = edited_df[edited_df['Delete'] == False] if 'Delete' in edited_df.columns else edited_df
    for _, row in to_update.iterrows():
        rec_bool = True if row['Received'] else False
        date_val = str(row['Date Received'])
        if rec_bool and (not date_val or date_val == "None" or date_val == "nan"):
             date_val = datetime.now().strftime("%Y-%m-%d")
        elif not rec_bool:
             date_val = ""

        update_data = {"Received": rec_bool, "Date Received": date_val, "Notes": str(row['Notes']), "Completed By": str(row.get('Completed By', ''))}
        supabase.table("Checklist").update(update_data).match({"Complex Name": complex_name, "Task Name": row['Task Name']}).execute()
    
    clear_cache()

def finalize_project_db(complex_name):
    final_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    supabase.table("Projects").update({"Is_Finalized": "TRUE", "Finalized Date": final_date}).eq("Complex Name", complex_name).execute()
    clear_cache()
    return final_date
