import streamlit as st
import pandas as pd
from database import (
    get_data, add_master_item, add_service_provider, add_employee, add_arrears_item, 
    add_council_account, add_trustee, delete_record_by_match, save_global_settings, 
    update_building_details_batch, create_new_building, update_project_agent_details, 
    save_checklist_batch, finalize_project_db, save_broker_details, update_email_status, 
    update_service_provider_date, update_wages_status, update_employee_batch
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

            # TABS
            tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Progress Tracker", "Staff Details", "Department Handovers"])

            # --- TAB 1: OVERVIEW ---
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

            # --- TAB 2: PROGRESS TRACKER ---
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
                    
                    # Ensure bools
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

            v
            # --- TAB 4: DEPARTMENT HANDOVERS ---
            with tab4:
                st.markdown("### Department Handovers")
                
                settings = get_data("Settings")
                s_dict = dict(zip(settings["Department"], settings["Email"])) if not settings.empty else {}

                def render_handover_section(dept_name, db_column, email_key, custom_body=None):
                    st.markdown(f"#### {dept_name}")
                    sent_date = get_val(db_column)
                    target_email = s_dict.get(email_key, "")
                    
                    if sent_date and sent_date != "None":
                        st.success(f"✅ Sent on: {sent_date}")
                        if st.button(f"Reset {dept_name}", key=f"rst_{dept_name}"):
                            update_email_status(b_choice, db_column, "")
                            st.rerun()
                    else:
                        st.info(f"Pending | Target: {target_email if target_email else 'No Email Set'}")
                        col_a, col_b = st.columns([1, 1])
                        with col_a:
                            if target_email:
                                subject = urllib.parse.quote(f"Handover: {b_choice} - {dept_name}")
                                body = urllib.parse.quote(custom_body if custom_body else f"Dear {dept_name} Team,\n\nPlease find attached the handover documents for {b_choice}.\n\nRegards,\nPretor Take-On Team")
                                link = f'<a href="mailto:{target_email}?subject={subject}&body={body}" target="_blank" style="text-decoration:none; color:white; background-color:#FF4B4B; padding:8px 12px; border-radius:5px;">📧 Draft Email</a>'
                                st.markdown(link, unsafe_allow_html=True)
                            else:
                                st.warning("⚠️ Set Email in Global Settings")
                        with col_b:
                            if st.button(f"Mark {dept_name} Sent", key=f"btn_{dept_name}"):
                                update_email_status(b_choice, db_column)
                                st.rerun()
                    st.divider()

                # 1. SARS
                render_handover_section("SARS", "SARS Sent Date", "SARS")

                # 2. Council
                st.markdown("#### Council")
                with st.expander("➕ Add Council Account Details"):
                    with st.form("add_c_new"):
                        an = st.text_input("Acc Number")
                        sv = st.text_input("Service")
                        bl = st.number_input("Balance")
                        if st.form_submit_button("Add Account"):
                            add_council_account(b_choice, an, sv, bl)
                            st.success("Added")
                            st.rerun()
                render_handover_section("Council", "Council Email Sent Date", "Municipal")

                # 3. Insurance
                st.markdown("#### Insurance")
                with st.expander("📝 Edit Broker Details"):
                    with st.form("brok_new"):
                        bn = st.text_input("Name", value=get_val("Insurance Broker Name"))
                        be = st.text_input("Email", value=get_val("Insurance Broker Email"))
                        if st.form_submit_button("Save Details"):
                            save_broker_details(b_choice, bn, be)
                            st.success("Saved")
                            st.rerun()
                
                # Broker
                st.markdown("**External Broker**")
                broker_email = get_val("Insurance Broker Email")
                b_date = get_val("Broker Email Sent Date")
                if b_date and b_date != "None":
                    st.success(f"Sent: {b_date}")
                else:
                    if broker_email:
                        subj = urllib.parse.quote(f"Insurance Appointment: {b_choice}")
                        lnk = f'<a href="mailto:{broker_email}?subject={subj}" style="margin-right:15px;">📧 Draft Broker Email</a>'
                        st.markdown(lnk, unsafe_allow_html=True)
                    if st.button("Mark Broker Sent"): update_email_status(b_choice, "Broker Email Sent Date"); st.rerun()
                
                # Internal Insurance
                st.markdown("**Internal Insurance Dept**")
                render_handover_section("Internal Insurance", "Internal Ins Email Sent Date", "Insurance")

                # 4. Wages (UPDATED WITH NEW DETAILS)
                wages_body = f"Dear Wages Team,\n\nPlease find attached the handover documents for {b_choice}.\n\n"
                wages_body += "--- PROJECT STATUTORY NUMBERS ---\n"
                wages_body += f"UIF: {get_val('UIF Number')}\nPAYE: {get_val('PAYE Number')}\nCOIDA: {get_val('COIDA Number')}\n\n"
                wages_body += "--- STAFF DETAILS ---\n"
                
                all_staff_email = get_data("Employees")
                if not all_staff_email.empty:
                    c_staff = all_staff_email[all_staff_email['Complex Name'] == b_choice]
                    if not c_staff.empty:
                        for _, emp in c_staff.iterrows():
                            # Parse bools
                            has_pay = "YES" if str(emp.get('Payslip Received', False)).lower() == 'true' else "NO"
                            has_con = "YES" if str(emp.get('Contract Received', False)).lower() == 'true' else "NO"
                            has_tax = "YES" if str(emp.get('Tax Ref Received', False)).lower() == 'true' else "NO"
                            
                            wages_body += f"Employee: {emp.get('Name','')} {emp.get('Surname','')}\n"
                            wages_body += f"ID: {emp.get('ID Number','')}\n"
                            wages_body += f"Position: {emp.get('Position','')} | Salary: R{emp.get('Salary', 0)}\n"
                            wages_body += f"[Docs: Payslip:{has_pay} | Contract:{has_con} | TaxRef:{has_tax}]\n\n"
                    else:
                        wages_body += "(No staff loaded on system)\n"
                else:
                    wages_body += "(No staff loaded on system)\n"
                
                wages_body += "Regards,\nPretor Take-On Team"
                
                render_handover_section("Wages", "Wages Sent Date", "Wages", custom_body=wages_body)

                # 5. Debt Collection
                render_handover_section("Debt Collection", "Debt Collection Sent Date", "Debt Collection")

                # 6. Accounts
                render_handover_section("Accounts", "Accounts Sent Date", "Accounts")

                # 7. Fee Confirmation
                st.markdown("#### Fee Confirmation")
                pm_email = get_val("Manager Email")
                fee_body = f"Please confirm the management fees for {b_choice}.\n\nAgreed Fees: {get_val('Mgmt Fees')}"
                
                f_date = get_val("Fee Confirmation Email Sent Date")
                if f_date and f_date != "None":
                    st.success(f"Sent: {f_date}")
                else:
                    col_f1, col_f2 = st.columns([1,1])
                    with col_f1:
                        if pm_email:
                            s_fee = urllib.parse.quote(f"Fee Confirmation: {b_choice}")
                            b_fee = urllib.parse.quote(fee_body)
                            l_fee = f'<a href="mailto:{pm_email}?subject={s_fee}&body={b_fee}" target="_blank" style="text-decoration:none; color:white; background-color:#FF4B4B; padding:8px 12px; border-radius:5px;">📧 Draft Fee Email</a>'
                            st.markdown(l_fee, unsafe_allow_html=True)
                    with col_f2:
                        if st.button("Mark Fee Email Sent"): 
                            update_email_status(b_choice, "Fee Confirmation Email Sent Date")
                            st.rerun()

                st.divider()

                # 8. Finalize
                st.markdown("### 🏁 Final Actions")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Finalize Project"):
                        finalize_project_db(b_choice)
                        st.balloons()

# --- ENTRY POINT ---
if __name__ == "__main__":
    main()






