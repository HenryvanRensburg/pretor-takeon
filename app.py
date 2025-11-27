import streamlit as st
import pandas as pd
from database import (
    get_data, add_master_item, add_service_provider, add_employee, add_arrears_item, 
    add_council_account, add_trustee, delete_record_by_match, save_global_settings, 
    update_building_details_batch, create_new_building, update_project_agent_details, 
    save_checklist_batch, finalize_project_db, save_broker_details, update_email_status, 
    update_service_provider_date, update_wages_status
)
from pdf_generator import generate_appointment_pdf, generate_report_pdf, generate_weekly_report_pdf
import urllib.parse
from datetime import datetime
import os

# --- PAGE CONFIG ---
# This must remain outside main() as the very first command
st.set_page_config(page_title="Pretor Take-On", layout="wide")

def main():
    if os.path.exists("pretor_logo.png"):
        st.sidebar.image("pretor_logo.png", use_container_width=True)
    st.title("🏢 Pretor Group: Take-On Manager")

    # --- MENU ---
    menu = ["Dashboard", "Master Schedule", "New Building", "Manage Buildings", "Global Settings"]
    choice = st.sidebar.selectbox("Menu", menu)

    # --- DASHBOARD ---
    if choice == "Dashboard":
        st.subheader("Active Projects Overview")
        df = get_data("Projects")
        checklist = get_data("Checklist")
        
        if not df.empty:
            summary_list = []
            for index, row in df.iterrows():
                c_name = row['Complex Name']
                if checklist.empty:
                    total, received = 0, 0
                else:
                    c_items = checklist[checklist['Complex Name'] == c_name]
                    # Ensure boolean comparison is safe
                    valid = c_items[c_items['Delete'] != True] 
                    pretor = valid[valid['Responsibility'].isin(['Pretor Group', 'Both'])]
                    total = len(pretor)
                    # Check for explicit True (handling Supabase bools or string 'True')
                    received = len(pretor[pretor['Received'].apply(lambda x: str(x).lower() == 'true')])
                
                progress_val = (received / total) if total > 0 else 0
                status = "✅ Completed" if progress_val == 1.0 else "⚠️ Near Completion" if progress_val > 0.8 else "🔄 In Progress" if progress_val > 0.1 else "🆕 Just Started"
                summary_list.append({
                    "Complex Name": c_name, 
                    "Manager": row.get('Assigned Manager', ''), 
                    "Take On Date": row.get('Take On Date', ''), 
                    "Progress": progress_val, "Status": status, "Items Pending": total - received
                })
            
            summ_df = pd.DataFrame(summary_list)
            st.dataframe(summ_df, column_config={"Progress": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=1)}, hide_index=True)
            
            if st.button("Download Weekly Report PDF"):
                pdf = generate_weekly_report_pdf(summary_list)
                with open(pdf, "rb") as f:
                    st.download_button("⬇️ Download PDF", f, file_name=pdf)
        else:
            st.info("No projects found.")

    # --- MASTER SCHEDULE ---
    elif choice == "Master Schedule":
        st.subheader("Master Checklist")
        with st.form("add_m"):
            c1, c2, c3, c4 = st.columns(4)
            tn = c1.text_input("Task Name")
            cat = c2.selectbox("Category", ["Both", "BC", "HOA"])
            resp = c3.selectbox("Responsibility", ["Previous Agent", "Pretor Group", "Both"])
            head = c4.selectbox("Heading", ["Take-On", "Financial", "Legal", "Statutory Compliance", "Insurance", "City Council", "Building Compliance", "Employee", "General"])
            if st.form_submit_button("Add"):
                add_master_item(tn, cat, resp, head)
                st.success("Added!")
                st.rerun()
        st.dataframe(get_data("Master"))

    # --- GLOBAL SETTINGS ---
    elif choice == "Global Settings":
        st.subheader("Department Emails")
        settings = get_data("Settings")
        s_dict = dict(zip(settings["Department"], settings["Email"])) if not settings.empty else {}
        with st.form("glob_set"):
            wages = st.text_input("Wages", value=s_dict.get("Wages", ""))
            sars = st.text_input("SARS", value=s_dict.get("SARS", ""))
            muni = st.text_input("Municipal", value=s_dict.get("Municipal", ""))
            debt = st.text_input("Debt Collection", value=s_dict.get("Debt Collection", ""))
            ins = st.text_input("Insurance", value=s_dict.get("Insurance", ""))
            acc = st.text_input("Accounts", value=s_dict.get("Accounts", ""))
            if st.form_submit_button("Save"):
                save_global_settings({"Wages": wages, "SARS": sars, "Municipal": muni, "Debt Collection": debt, "Insurance": ins, "Accounts": acc})
                st.success("Saved!")
                st.rerun()

    # --- NEW BUILDING ---
    elif choice == "New Building":
        st.subheader("Onboard New Complex")
        with st.form("new_b"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Complex Name")
            b_type = c2.selectbox("Type", ["Body Corporate", "HOA"])
            
            # Basic Fields
            c3, c4 = st.columns(2)
            tod = c3.date_input("Take On Date", datetime.today())
            units = c4.number_input("Units", min_value=1)
            
            # Team
            c5, c6 = st.columns(2)
            tom = c5.text_input("Take-On Manager", "Henry Janse van Rensburg")
            pm = c6.text_input("Portfolio Manager")
            
            # Financials
            c7, c8, c9 = st.columns(3)
            ye = c7.text_input("Year End")
            fees = c8.text_input("Mgmt Fees")
            bcode = c9.text_input("Building Code")
            
            if st.form_submit_button("Create"):
                if name:
                    data = {
                        "Complex Name": name, "Type": b_type, "Take On Date": str(tod), "No of Units": units,
                        "TakeOn Name": tom, "Assigned Manager": pm, "Year End": ye, "Mgmt Fees": fees, "Building Code": bcode,
                        "Date Doc Requested": str(datetime.today())
                    }
                    res = create_new_building(data)
                    if res == "SUCCESS": st.success("Created!"); st.rerun()
                    elif res == "EXISTS": st.error("Exists already.")
                else:
                    st.error("Name required.")

    # --- MANAGE BUILDINGS ---
    elif choice == "Manage Buildings":
        projs = get_data("Projects")
        if projs.empty:
            st.warning("No projects.")
        else:
            b_choice = st.selectbox("Select Complex", projs['Complex Name'])
            p_row = projs[projs['Complex Name'] == b_choice].iloc[0]
            
            # Helper to get field safely
            def get_val(col): return str(p_row.get(col, ''))

            # Tabs for cleaner UI
            tab1, tab2, tab3 = st.tabs(["Overview", "Progress Tracker", "Department Handovers"])

            with tab1:
                with st.expander("Edit Details"):
                    with st.form("edit_det"):
                        nm = st.text_input("Manager", value=get_val("Assigned Manager"))
                        em = st.text_input("Email", value=get_val("Manager Email"))
                        if st.form_submit_button("Update"):
                            update_building_details_batch(b_choice, {"Assigned Manager": nm, "Manager Email": em})
                            st.success("Updated")
                            st.rerun()
                
                st.markdown("### Previous Agent Request")
                c1, c2 = st.columns(2)
                an = c1.text_input("Agent Name", value=get_val("Agent Name"))
                ae = c2.text_input("Agent Email", value=get_val("Agent Email"))
                if st.button("Generate Request PDF"):
                    update_project_agent_details(b_choice, an, ae)
                    items = get_data("Checklist")
                    req_items = items[(items['Complex Name'] == b_choice) & (items['Responsibility'] != 'Pretor Group')]
                    pdf = generate_appointment_pdf(b_choice, req_items, an, get_val("Take On Date"), get_val("Year End"), get_val("Building Code"))
                    with open(pdf, "rb") as f:
                        st.download_button("Download PDF", f, file_name=pdf)

            with tab2:
                st.markdown("### Checklist")
                items = get_data("Checklist")
                if not items.empty:
                    c_items = items[items['Complex Name'] == b_choice].copy()
                    view = st.radio("View", ["Agent Items", "Internal Items"], horizontal=True)
                    
                    if view == "Agent Items":
                        df_view = c_items[c_items['Responsibility'].isin(['Previous Agent', 'Both'])]
                        cols = ['Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes']
                    else:
                        df_view = c_items
                        cols = ['Task Heading', 'Task Name', 'Received', 'Date Received', 'Completed By', 'Notes', 'Delete']
                    
                    # Ensure bools (Handles Supabase True/False or string "true"/"false")
                    df_view['Received'] = df_view['Received'].apply(lambda x: True if str(x).lower() == 'true' else False)
                    if 'Delete' in df_view.columns:
                         df_view['Delete'] = df_view['Delete'].apply(lambda x: True if str(x).lower() == 'true' else False)
                    
                    # Sorter
                    sections = ["Take-On", "Financial", "Legal", "Statutory Compliance", "Insurance", "City Council", "Building Compliance", "Employee", "General"]
                    df_view['Sort'] = df_view['Task Heading'].apply(lambda x: sections.index(x) if x in sections else 99)
                    df_view = df_view.sort_values(by=['Sort', 'Task Name'])

                    edited = st.data_editor(
                        df_view[cols], 
                        hide_index=True, 
                        height=600,
                        column_config={
                            "Task Heading": st.column_config.TextColumn(disabled=True),
                            "Task Name": st.column_config.TextColumn(disabled=True)
                        }
                    )
                    if st.button("Save Changes"):
                        save_checklist_batch(b_choice, edited)
                        st.success("Saved!")
                        st.rerun()

            with tab3:
                # SARS
                st.markdown("#### SARS")
                s_date = get_val("SARS Sent Date")
                if s_date and s_date != "None":
                    st.success(f"Sent: {s_date}")
                    if st.button("Reset SARS"): update_email_status(b_choice, "SARS Sent Date", ""); st.rerun()
                else:
                    if st.button("Mark SARS Sent"): update_email_status(b_choice, "SARS Sent Date"); st.rerun()
                
                st.divider()
                
                # Council
                st.markdown("#### Council")
                with st.expander("Add Account"):
                    with st.form("add_c"):
                        an = st.text_input("Acc Number")
                        sv = st.text_input("Service")
                        bl = st.number_input("Balance")
                        if st.form_submit_button("Add"):
                            add_council_account(b_choice, an, sv, bl)
                            st.rerun()
                
                c_date = get_val("Council Email Sent Date")
                if c_date and c_date != "None":
                    st.success(f"Sent: {c_date}")
                    if st.button("Reset Council"): update_email_status(b_choice, "Council Email Sent Date", ""); st.rerun()
                else:
                    if st.button("Mark Council Sent"): update_email_status(b_choice, "Council Email Sent Date"); st.rerun()

                st.divider()
                
                # Insurance
                st.markdown("#### Insurance")
                with st.expander("Broker Details"):
                    with st.form("brok"):
                        bn = st.text_input("Name", value=get_val("Insurance Broker Name"))
                        be = st.text_input("Email", value=get_val("Insurance Broker Email"))
                        if st.form_submit_button("Save"):
                            save_broker_details(b_choice, bn, be)
                            st.success("Saved")
                            st.rerun()
                
                c1, c2 = st.columns(2)
                with c1:
                    b_date = get_val("Broker Email Sent Date")
                    if b_date and b_date != "None":
                        st.success(f"Broker: {b_date}")
                    else:
                        if st.button("Mark Broker Sent"): update_email_status(b_choice, "Broker Email Sent Date"); st.rerun()
                with c2:
                    i_date = get_val("Internal Ins Email Sent Date")
                    if i_date and i_date != "None":
                        st.success(f"Internal: {i_date}")
                    else:
                        if st.button("Mark Internal Sent"): update_email_status(b_choice, "Internal Ins Email Sent Date"); st.rerun()
                
                st.divider()

                # Reports
                st.markdown("### Reports & Finalize")
                
                # Fee Confirmation
                f_date = get_val("Fee Confirmation Email Sent Date")
                if f_date and f_date != "None":
                     st.success(f"Fee Confirmation Sent: {f_date}")
                else:
                     if st.button("Mark Fee Email Sent"): update_email_status(b_choice, "Fee Confirmation Email Sent Date"); st.rerun()

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Draft Client Update Email"):
                        # FIX: Define client_email properly
                        client_email = get_val("Manager Email")
                        
                        # Generate comprehensive status string
                        items = get_data("Checklist")
                        if not items.empty:
                             # FIX: Use string comparison safe for Supabase bools
                             c_items = items[(items['Complex Name'] == b_choice) & (items['Received'].apply(lambda x: str(x).lower() == 'true'))]
                             received_count = len(c_items)
                        else: received_count = 0
                        
                        body = f"Progress Update for {b_choice}:\n\n"
                        body += f"- Insurance: {'Done' if i_date else 'Pending'}\n"
                        body += f"- SARS: {'Done' if s_date else 'Pending'}\n"
                        body += f"- Checklist Items Received: {received_count}\n"
                        
                        subject = urllib.parse.quote(f"Update: {b_choice}")
                        body = urllib.parse.quote(body)
                        link = f'<a href="mailto:{client_email}?subject={subject}&body={body}">Send Email</a>'
                        st.markdown(link, unsafe_allow_html=True)

                with col2:
                    if st.button("Finalize Project"):
                        finalize_project_db(b_choice)
                        st.balloons()

# --- ENTRY POINT ---
if __name__ == "__main__":
    main()
