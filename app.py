import streamlit as st
import pandas as pd
from database import (
    get_data, add_master_item, add_service_provider, add_employee, add_arrears_item, 
    add_council_account, add_trustee, delete_record_by_match, save_global_settings, 
    update_building_details_batch, create_new_building, update_project_agent_details, 
    save_checklist_batch, finalize_project_db, save_broker_details, update_email_status, 
    update_service_provider_date, update_wages_status, update_employee_batch, 
    update_council_batch, update_arrears_batch
)
from pdf_generator import generate_appointment_pdf, generate_report_pdf, generate_weekly_report_pdf
import urllib.parse
from datetime import datetime
import os

# --- PAGE CONFIG ---
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
                    valid = c_items[c_items['Delete'] != True] 
                    pretor = valid[valid['Responsibility'].isin(['Pretor Group', 'Both'])]
                    total = len(pretor)
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
                st.cache_data.clear()
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
                st.cache_data.clear()
                st.success("Saved!")
                st.rerun()

    # --- NEW BUILDING ---
    elif choice == "New Building":
        st.subheader("Onboard New Complex")
        with st.form("new_b"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Complex Name")
            b_type = c2.selectbox("Type", ["Body Corporate", "HOA"])
            
            c3, c4 = st.columns(2)
            tod = c3.date_input("Take On Date", datetime.today())
            units = c4.number_input("Units", min_value=1)
            
            c5, c6 = st.columns(2)
            tom = c5.text_input("Take-On Manager", "Henry Janse van Rensburg")
            pm = c6.text_input("Portfolio Manager")
            
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
                    st.cache_data.clear()
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
            
            def get_val(col): return str(p_row.get(col, ''))

            # NAVIGATION
            st.divider()
            sub_nav = st.radio(
                "Section Navigation", 
                ["Overview", "Progress Tracker", "Staff Details", "Arrears Details", "Council Details", "Department Handovers"], 
                horizontal=True,
                label_visibility="collapsed"
            )
            st.divider()

            # --- SUB SECTION 1: OVERVIEW ---
            if sub_nav == "Overview":
                st.subheader(f"Project Overview: {b_choice}")
                
                with st.form("project_overview_form"):
                    st.caption("Fields with existing data are locked 🔒. Please fill in any missing details.")
                    
                    def smart_input(label, col_name, col_obj=st):
                        curr_val = str(p_row.get(col_name, ''))
                        has_data = bool(curr_val and curr_val.lower() not in ["none", "nan", ""])
                        return col_obj.text_input(
                            label, 
                            value=curr_val if has_data else "", 
                            disabled=has_data,
                            key=f"ov_{col_name}",
                            placeholder="Enter detail..."
                        )

                    # --- SECTION 1: GENERAL & ADDRESS ---
                    st.markdown("#### 📍 General & Address")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        u_code = smart_input("Building Code", "Building Code", c1)
                        u_type = smart_input("Type (BC/HOA)", "Type", c1)
                    with c2:
                        u_units = smart_input("No of Units", "No of Units", c2)
                        u_ss = smart_input("SS Number", "SS Number", c2)
                    with c3:
                        u_erf = smart_input("Erf Number", "Erf Number", c3)
                        u_csos = smart_input("CSOS Number", "CSOS Number", c3)
                    
                    st.markdown("")
                    u_addr = smart_input("Physical Address", "Physical Address", st)

                    # --- SECTION 2: FINANCIAL & COMPLIANCE ---
                    st.divider()
                    st.markdown("#### 💰 Financial & Compliance")
                    c4, c5, c6 = st.columns(3)
                    with c4:
                        u_ye = smart_input("Year End", "Year End", c4)
                        u_fees = smart_input("Mgmt Fees", "Mgmt Fees", c4)
                        u_exp = smart_input("Expense Code", "Expense Code", c4)
                    with c5:
                        u_vat = smart_input("VAT Number", "VAT Number", c5)
                        u_tax = smart_input("Tax Number", "Tax Number", c5)
                        u_tod = smart_input("Take On Date", "Take On Date", c5)
                    with c6:
                        u_aud = smart_input("Auditor", "Auditor", c6)
                        u_last_aud = smart_input("Last Audit", "Last Audit", c6)

                    # --- SECTION 3: THE TEAM ---
                    st.divider()
                    st.markdown("#### 👥 The Team")
                    c7, c8, c9 = st.columns(3)
                    with c7:
                        u_pm = smart_input("Portfolio Manager", "Assigned Manager", c7)
                        u_pm_e = smart_input("PM Email", "Manager Email", c7)
                        u_client_e = smart_input("Client Email", "Client Email", c7)
                    with c8:
                        u_pa = smart_input("Portfolio Assistant", "Portfolio Assistant", c8)
                        u_pa_e = smart_input("PA Email", "Portfolio Assistant Email", c8)
                        u_tom = smart_input("Take-On Manager", "TakeOn Name", c8)
                    with c9:
                        u_bk = smart_input("Bookkeeper", "Bookkeeper", c9)
                        u_bk_e = smart_input("Bookkeeper Email", "Bookkeeper Email", c9)

                    st.markdown("---")
                    
                    if st.form_submit_button("💾 Save Missing Details"):
                        updates = {
                            "Building Code": u_code, "Type": u_type, "No of Units": u_units,
                            "SS Number": u_ss, "Erf Number": u_erf, "CSOS Number": u_csos,
                            "Physical Address": u_addr,
                            "Year End": u_ye, "Mgmt Fees": u_fees, "Expense Code": u_exp,
                            "VAT Number": u_vat, "Tax Number": u_tax, "Take On Date": u_tod,
                            "Auditor": u_aud, "Last Audit": u_last_aud,
                            "Assigned Manager": u_pm, "Manager Email": u_pm_e, "Client Email": u_client_e,
                            "Portfolio Assistant": u_pa, "Portfolio Assistant Email": u_pa_e, "TakeOn Name": u_tom,
                            "Bookkeeper": u_bk, "Bookkeeper Email": u_bk_e
                        }
                        update_building_details_batch(b_choice, updates)
                        st.cache_data.clear()
                        st.success("Project details updated.")
                        st.rerun()

                st.markdown("### Previous Agent Request")
                c1, c2 = st.columns(2)
                an = c1.text_input("Agent Name", value=get_val("Agent Name"))
                ae = c2.text_input("Agent Email", value=get_val("Agent Email"))
                
                if st.button("Generate Request PDF"):
                    update_project_agent_details(b_choice, an, ae)
                    st.cache_data.clear()
                    items = get_data("Checklist")
                    req_items = items[(items['Complex Name'] == b_choice) & (items['Responsibility'] != 'Pretor Group')]
                    pdf = generate_appointment_pdf(b_choice, req_items, an, get_val("Take On Date"), get_val("Year End"), get_val("Building Code"))
                    with open(pdf, "rb") as f:
                        st.download_button("Download PDF", f, file_name=pdf)

            # --- SUB SECTION 2: PROGRESS TRACKER ---
            elif sub_nav == "Progress Tracker":
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
                    
                    df_view['Received'] = df_view['Received'].apply(lambda x: True if str(x).lower() == 'true' else False)
                    if 'Delete' in df_view.columns:
                         df_view['Delete'] = df_view['Delete'].apply(lambda x: True if str(x).lower() == 'true' else False)
                    
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
                        st.cache_data.clear()
                        st.success("Saved!")
                        st.rerun()

            # --- SUB SECTION 3: STAFF DETAILS ---
            elif sub_nav == "Staff Details":
                st.subheader(f"Staff Management: {b_choice}")
                
                # A. Statutory Numbers
                st.markdown("#### 🏢 Project Statutory Numbers")
                uif_val = get_val("UIF Number") if "UIF Number" in p_row.index else ""
                paye_val = get_val("PAYE Number") if "PAYE Number" in p_row.index else ""
                coida_val = get_val("COIDA Number") if "COIDA Number" in p_row.index else ""

                def is_filled(val):
                    return val and str(val).lower() not in ["none", "nan", ""]

                locked = is_filled(uif_val) or is_filled(paye_val) or is_filled(coida_val)

                if locked:
                    st.success("🔒 Statutory details are locked.")
                    c1, c2, c3 = st.columns(3)
                    c1.text_input("UIF Number", value=uif_val, disabled=True, key="uif_lock")
                    c2.text_input("PAYE Number", value=paye_val, disabled=True, key="paye_lock")
                    c3.text_input("COIDA / Workmens Comp", value=coida_val, disabled=True, key="coida_lock")
                else:
                    st.info("ℹ️ Enter carefully. Once saved, these will be locked.")
                    with st.form("stat_nums"):
                        c1, c2, c3 = st.columns(3)
                        uif_n = c1.text_input("UIF Number", value=uif_val)
                        paye_n = c2.text_input("PAYE Number", value=paye_val)
                        coida_n = c3.text_input("COIDA / Workmens Comp", value=coida_val)
                        
                        if st.form_submit_button("💾 Save & Lock"):
                            update_building_details_batch(b_choice, {
                                "UIF Number": uif_n, "PAYE Number": paye_n, "COIDA Number": coida_n
                            })
                            st.cache_data.clear()
                            st.success("Saved and locked.")
                            st.rerun()

                st.divider()

                # B. Staff List
                st.markdown("#### 👥 Employee List (Editable)")
                all_staff = get_data("Employees")
                
                if not all_staff.empty:
                    if 'Complex Name' in all_staff.columns:
                        current_staff = all_staff[all_staff['Complex Name'] == b_choice].copy()
                    else:
                        current_staff = pd.DataFrame()
                else:
                    current_staff = pd.DataFrame()

                if not current_staff.empty:
                    for col in ['Payslip Received', 'Contract Received', 'Tax Ref Received']:
                        if col in current_staff.columns:
                            current_staff[col] = current_staff[col].apply(lambda x: True if str(x).lower() == 'true' else False)

                    display_cols = ['id', 'Name', 'Surname', 'ID Number', 'Position', 'Salary', 'Payslip Received', 'Contract Received', 'Tax Ref Received']
                    final_cols = [c for c in display_cols if c in current_staff.columns]

                    edited_df = st.data_editor(
                        current_staff[final_cols],
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "id": st.column_config.Column(disabled=True, width="small"),
                            "Salary": st.column_config.NumberColumn(format="R %.2f"),
                            "Payslip Received": st.column_config.CheckboxColumn("Payslip"),
                            "Contract Received": st.column_config.CheckboxColumn("Contract"),
                            "Tax Ref Received": st.column_config.CheckboxColumn("Tax Ref")
                        },
                        key="staff_editor"
                    )

                    if st.button("💾 Save Changes to Staff List"):
                        update_employee_batch(edited_df)
                        st.cache_data.clear()
                        st.success("Staff list updated successfully!")
                        st.rerun()
                else:
                    st.info("No staff loaded yet.")

                st.divider()

                # C. Add New Employee Form
                st.markdown("#### ➕ Add New Employee")
                
                with st.form("add_emp", clear_on_submit=True):
                    c1, c2, c3 = st.columns(3)
                    e_name = c1.text_input("Name", key="new_name")
                    e_sur = c2.text_input("Surname", key="new_sur")
                    e_id = c3.text_input("ID Number", key="new_id")

                    c4, c5 = st.columns(2)
                    e_pos = c4.text_input("Position", key="new_pos")
                    e_sal = c5.number_input("Gross Salary", min_value=0.0, key="new_sal")
                    
                    st.markdown("**Documents Received:**")
                    col_a, col_b, col_c = st.columns(3)
                    chk_pay = col_a.checkbox("Latest Payslip", key="new_chk_pay")
                    chk_con = col_b.checkbox("Employment Contract", key="new_chk_con")
                    chk_tax = col_c.checkbox("Indiv Tax Number", key="new_chk_tax")
                    
                    if st.form_submit_button("Add Employee"):
                        if e_name and e_sur and e_id:
                            try:
                                add_employee(b_choice, e_name, e_sur, e_id, e_pos, float(e_sal), chk_pay, chk_con, chk_tax)
                                st.cache_data.clear()
                                st.success("Employee Added")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error adding employee: {e}")
                        else:
                            st.error("Name, Surname and ID are required.")

            # --- SUB SECTION 4: ARREARS DETAILS ---
            elif sub_nav == "Arrears Details":
                st.subheader(f"Arrears Management: {b_choice}")
                st.markdown("Manage the list of units with outstanding levies below.")
                
                arrears_data = get_data("Arrears")
                
                if not arrears_data.empty:
                    rename_map_arr = {
                        'complex_name': 'Complex Name',
                        'unit_number': 'Unit Number',
                        'outstanding_amount': 'Outstanding Amount',
                        'attorney_name': 'Attorney Name',
                        'attorney_email': 'Attorney Email',
                        'attorney_phone': 'Attorney Phone',
                        'Complex_Name': 'Complex Name'
                    }
                    arrears_data.rename(columns=rename_map_arr, inplace=True)

                if not arrears_data.empty and 'Complex Name' in arrears_data.columns:
                    curr_arrears = arrears_data[arrears_data['Complex Name'] == b_choice].copy()
                    
                    if not curr_arrears.empty:
                        st.markdown("#### 📝 Arrears List (Editable)")
                        
                        arr_cols = ['id', 'Unit Number', 'Outstanding Amount', 'Attorney Name', 'Attorney Email', 'Attorney Phone']
                        arr_cols = [c for c in arr_cols if c in curr_arrears.columns]
                        
                        edited_arrears = st.data_editor(
                            curr_arrears[arr_cols],
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "id": st.column_config.Column(disabled=True, width="small"),
                                "Outstanding Amount": st.column_config.NumberColumn(format="R %.2f"),
                                "Unit Number": st.column_config.TextColumn("Unit No")
                            },
                            key="arrears_editor"
                        )
                        
                        if st.button("💾 Save Changes to Arrears"):
                            update_arrears_batch(edited_arrears)
                            st.cache_data.clear()
                            st.success("Arrears updated.")
                            st.rerun()
                    else:
                        st.info("No arrears loaded yet.")
                else:
                    st.info("No arrears data available.")

                st.divider()

                with st.expander("➕ Add New Arrears Record", expanded=True):
                    with st.form("add_arr_form", clear_on_submit=True):
                        c1, c2 = st.columns(2)
                        a_unit = c1.text_input("Unit Number", key="new_a_u")
                        a_amt = c2.number_input("Outstanding Amount", min_value=0.0, key="new_a_a")
                        
                        c3, c4, c5 = st.columns(3)
                        a_att = c3.text_input("Attorney Name", key="new_a_n")
                        a_mail = c4.text_input("Attorney Email", key="new_a_e")
                        a_ph = c5.text_input("Attorney Phone", key="new_a_p")
                        
                        if st.form_submit_button("Add Record"):
                            if a_unit:
                                add_arrears_item(b_choice, a_unit, a_amt, a_att, a_mail, a_ph)
                                st.cache_data.clear()
                                st.success("Added")
                                st.rerun()
                            else:
                                st.error("Unit Number required")

            # --- SUB SECTION 5: COUNCIL DETAILS (FIXED) ---
            elif sub_nav == "Council Details":
                st.subheader(f"Council Management: {b_choice}")
                st.markdown("Manage municipal accounts for this complex.")
                
                # Fetch both 'Council' and 'council' to be safe
                council_data = get_data("Council")
                if council_data.empty:
                    council_data = get_data("council")
                
                if not council_data.empty:
                    # Clean column names (strip spaces, normalize)
                    council_data.columns = [c.strip() for c in council_data.columns]
                    
                    rename_map = {
                        'complex_name': 'Complex Name',
                        'account_number': 'Account Number',
                        'service': 'Service',
                        'balance': 'Balance',
                        'Complex Name': 'Complex Name',
                        'Account Number': 'Account Number',
                        'complex name': 'Complex Name',
                        'account number': 'Account Number'
                    }
                    council_data.rename(columns=rename_map, inplace=True)
                
                if not council_data.empty and 'Complex Name' in council_data.columns:
                    curr_council = council_data[council_data['Complex Name'] == b_choice].copy()
                    
                    if not curr_council.empty:
                        st.markdown("#### 📝 Council Accounts (Editable)")
                        c_cols = ['id', 'Account Number', 'Service', 'Balance']
                        c_cols = [c for c in c_cols if c in curr_council.columns]
                        
                        edited_council = st.data_editor(
                            curr_council[c_cols],
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "id": st.column_config.Column(disabled=True, width="small"),
                                "Balance": st.column_config.NumberColumn(format="R %.2f")
                            },
                            key="council_editor"
                        )
                        
                        if st.button("💾 Save Changes to Accounts"):
                            update_council_batch(edited_council)
                            st.cache_data.clear()
                            st.success("Council accounts updated.")
                            st.rerun()
                    else:
                        st.info(f"No council accounts found for {b_choice}.")
                else:
                    st.info("No council data available in the database.")

                st.divider()

                with st.expander("➕ Add New Council Account", expanded=True):
                    with st.form("add_c_form", clear_on_submit=True):
                        c1, c2, c3 = st.columns(3)
                        an = c1.text_input("Acc Number", key="new_c_an")
                        sv = c2.text_input("Service", key="new_c_sv")
                        bl = c3.number_input("Balance", key="new_c_bl")
                        
                        if st.form_submit_button("Add Account"):
                            add_council_account(b_choice, an, sv, bl)
                            st.cache_data.clear()
                            st.success("Added")
                            st.rerun()

            # --- SUB SECTION 6: DEPARTMENT HANDOVERS ---
            elif sub_nav == "Department Handovers":
                st.markdown("### Department Handovers")
                
                settings = get_data("Settings")
                s_dict = dict(zip(settings["Department"], settings["Email"])) if not settings.empty else {}

                # 1. Custom SARS Section
                st.markdown("#### SARS")
                sars_email = s_dict.get("SARS", "")
                sars_sent_date = get_val("SARS Sent Date")
                
                if sars_sent_date and sars_sent_date != "None":
                    st.success(f"✅ Sent on: {sars_sent_date}")
                    if st.button("Reset SARS", key="rst_sars_cust"):
                        update_email_status(b_choice, "SARS Sent Date", "")
                        st.cache_data.clear()
                        st.rerun()
                else:
                    tax_num = get_val("Tax Number")
                    sars_body = f"Dear SARS Team,\n\nPlease find attached the handover documents for {b_choice}.\n\n"
                    has_tax_num = tax_num and str(tax_num).lower() not in ['none', 'nan', '']
                    
                    if has_tax_num:
                        st.success(f"📌 **Confirmed Tax Number:** {tax_num}")
                        sars_body += f"Confirmed Tax Number: {tax_num}\n\n"
                    else:
                        st.warning("⚠️ No Tax Number on file.")
                        sars_option = st.radio("Select Status for Email:", ["Awaiting Tax Number", "Please Register Scheme"], key="sars_rad")
                        sars_body += f"Note regarding Tax Number: {sars_option}\n\n"
                    
                    sars_body += "Regards,\nPretor Take-On Team"
                    
                    col_s1, col_s2 = st.columns([1,1])
                    with col_s1:
                        if sars_email:
                            s_sub = urllib.parse.quote(f"Handover: {b_choice} - SARS")
                            s_bod = urllib.parse.quote(sars_body)
                            lnk = f'<a href="mailto:{sars_email}?subject={s_sub}&body={s_bod}" target="_blank" style="text-decoration:none; color:white; background-color:#FF4B4B; padding:8px 12px; border-radius:5px;">📧 Draft Email</a>'
                            st.markdown(lnk, unsafe_allow_html=True)
                        else:
                            st.warning("Set SARS Email in Global Settings")
                    
                    with col_s2:
                        if st.button("Mark SARS Sent", key="btn_sars_cust"):
                            update_email_status(b_choice, "SARS Sent Date")
                            st.cache_data.clear()
                            st.rerun()
                st.divider()

                # 2. CUSTOM COUNCIL SECTION (Handover Only)
                st.markdown("#### Council")
                muni_email = s_dict.get("Municipal", "")
                c_sent_date = get_val("Council Email Sent Date")
                
                # Fetch Data for Email Body (Try both cases)
                council_data = get_data("Council")
                if council_data.empty: council_data = get_data("council")
                
                if not council_data.empty:
                    council_data.columns = [c.strip() for c in council_data.columns]
                    rename_map = {
                        'complex_name': 'Complex Name', 'account_number': 'Account Number',
                        'service': 'Service', 'balance': 'Balance',
                        'complex name': 'Complex Name', 'account number': 'Account Number'
                    }
                    council_data.rename(columns=rename_map, inplace=True)
                
                # UPDATED EMAIL BODY FOR COUNCIL
                council_path = f"Y:\\HenryJ\\NEW BUSINESS & DEVELOPMENTS\\{b_choice}\\council"
                
                c_body_str = f"Dear Council Team,\n\nPlease note that the latest council accounts and documents received from the previous agents can be found at the following location:\n{council_path}\n\n"
                c_body_str += f"Please proceed with the handover for {b_choice}.\n\n--- ACCOUNTS LIST ---\n"
                
                if not council_data.empty and 'Complex Name' in council_data.columns:
                    curr_council = council_data[council_data['Complex Name'] == b_choice].copy()
                    if not curr_council.empty:
                        # Display Read-only list
                        st.dataframe(curr_council[['Account Number', 'Service', 'Balance']], hide_index=True)
                        for _, acc in curr_council.iterrows():
                            c_body_str += f"Acc: {acc.get('Account Number','')} | Svc: {acc.get('Service','')} | Bal: R{acc.get('Balance', 0)}\n"
                    else:
                        c_body_str += "(No accounts loaded)\n"
                else:
                    c_body_str += "(No accounts loaded)\n"
                c_body_str += "\nRegards,\nPretor Take-On Team"

                if c_sent_date and c_sent_date != "None":
                    st.success(f"✅ Sent on: {c_sent_date}")
                    if st.button("Reset Council Handover", key="rst_council_cust"):
                        update_email_status(b_choice, "Council Email Sent Date", "")
                        st.cache_data.clear()
                        st.rerun()
                else:
                    col_cm1, col_cm2 = st.columns([1,1])
                    with col_cm1:
                        if muni_email:
                            c_sub = urllib.parse.quote(f"Handover: {b_choice} - Council")
                            c_bod = urllib.parse.quote(c_body_str)
                            lnk = f'<a href="mailto:{muni_email}?subject={c_sub}&body={c_bod}" target="_blank" style="text-decoration:none; color:white; background-color:#FF4B4B; padding:8px 12px; border-radius:5px;">📧 Draft Email</a>'
                            st.markdown(lnk, unsafe_allow_html=True)
                        else:
                            st.warning("Set Municipal Email in Global Settings")
                    with col_cm2:
                        if st.button("Mark Council Sent", key="btn_council_cust"):
                            update_email_status(b_choice, "Council Email Sent Date")
                            st.cache_data.clear()
                            st.rerun()
                
                st.divider()

                # 3. Generic Function for REMAINING departments
                def render_handover_section(dept_name, db_column, email_key, custom_body=None):
                    st.markdown(f"#### {dept_name}")
                    sent_date = get_val(db_column)
                    target_email = s_dict.get(email_key, "")
                    
                    if sent_date and sent_date != "None":
                        st.success(f"✅ Sent on: {sent_date}")
                        if st.button(f"Reset {dept_name}", key=f"rst_{dept_name}"):
                            update_email_status(b_choice, db_column, "")
                            st.cache_data.clear()
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
                                st.cache_data.clear()
                                st.rerun()
                    st.divider()

                # 4. Insurance
                st.markdown("#### Insurance")
                with st.expander("📝 Edit Broker Details"):
                    with st.form("brok_new"):
                        bn = st.text_input("Name", value=get_val("Insurance Broker Name"))
                        be = st.text_input("Email", value=get_val("Insurance Broker Email"))
                        if st.form_submit_button("Save Details"):
                            save_broker_details(b_choice, bn, be)
                            st.cache_data.clear()
                            st.success("Saved")
                            st.rerun()
                
                st.markdown("**External Broker**")
                broker_email = get_val("Insurance Broker Email")
                b_date = get_val("Broker Email Sent Date")
                
                if b_date and b_date != "None":
                    st.success(f"Sent: {b_date}")
                else:
                    if broker_email:
                        pm_name = get_val("Assigned Manager")
                        pm_email = get_val("Manager Email")
                        
                        broker_body = f"Dear Broker,\n\nPlease take note that Pretor Group has been appointed as the managing agents for {b_choice}.\n\n"
                        broker_body += "We kindly request the following documents for our records:\n"
                        broker_body += "1. The latest Insurance Policy Schedule.\n"
                        broker_body += "2. A 3-year Claims History.\n\n"
                        broker_body += "Please note that all future communication regarding the insurance should be directed to the appointed Portfolio Manager:\n"
                        broker_body += f"Name: {pm_name}\nEmail: {pm_email}\n\n"
                        broker_body += "Regards,\nPretor Take-On Team"

                        subj = urllib.parse.quote(f"Insurance Appointment: {b_choice}")
                        bod = urllib.parse.quote(broker_body)
                        
                        lnk = f'<a href="mailto:{broker_email}?subject={subj}&body={bod}" target="_blank" style="text-decoration:none; color:white; background-color:#FF4B4B; padding:8px 12px; border-radius:5px;">📧 Draft Broker Email</a>'
                        st.markdown(lnk, unsafe_allow_html=True)
                    else:
                        st.warning("⚠️ No Broker Email Loaded")

                    if st.button("Mark Broker Sent"): 
                        update_email_status(b_choice, "Broker Email Sent Date")
                        st.cache_data.clear()
                        st.rerun()
                
                st.markdown("**Internal Insurance Dept**")
                
                ins_path = f"Y:\\HenryJ\\NEW BUSINESS & DEVELOPMENTS\\{b_choice}\\insurance"
                internal_ins_body = f"Hi Insurance Team,\n\n"
                internal_ins_body += f"Please note that {b_choice} is now being managed by Pretor.\n\n"
                internal_ins_body += f"You can find the latest insurance policy and claims history saved at the following location:\n{ins_path}\n\n"
                internal_ins_body += "Could you please review these documents and provide us with an insurance quotation?\n\n"
                internal_ins_body += "Regards,\nPretor Take-On Team"

                render_handover_section("Internal Insurance", "Internal Ins Email Sent Date", "Insurance", custom_body=internal_ins_body)

                # 5. Wages
                wages_body = f"Dear Wages Team,\n\nPlease note that the relevant information received from the previous agents regarding salaries and wages can be found at:\n"
                wages_body += f"Y:\\HenryJ\\NEW BUSINESS & DEVELOPMENTS\\{b_choice}\\salaries&wages\n\n"
                wages_body += "Below is a summary of the project details and staff loaded on the system:\n\n"
                wages_body += "--- PROJECT STATUTORY NUMBERS ---\n"
                wages_body += f"UIF: {get_val('UIF Number')}\nPAYE: {get_val('PAYE Number')}\nCOIDA: {get_val('COIDA Number')}\n\n"
                wages_body += "--- STAFF DETAILS ---\n"
                
                all_staff_email = get_data("Employees")
                if not all_staff_email.empty:
                    c_staff = all_staff_email[all_staff_email['Complex Name'] == b_choice]
                    if not c_staff.empty:
                        for _, emp in c_staff.iterrows():
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

                # 6. Debt Collection
                st.markdown("#### Debt Collection & Legal")
                
                # Internal Handover
                dc_sent_date = get_val("Debt Collection Sent Date")
                
                arrears_data = get_data("Arrears")
                if not arrears_data.empty:
                    rename_map_arr = {'complex_name': 'Complex Name', 'unit_number': 'Unit Number', 'outstanding_amount': 'Outstanding Amount', 'attorney_name': 'Attorney Name', 'attorney_email': 'Attorney Email', 'attorney_phone': 'Attorney Phone'}
                    arrears_data.rename(columns=rename_map_arr, inplace=True)

                dc_body = f"Dear Debt Collection Team,\n\nPlease find attached the handover documents for {b_choice}.\n\n--- ARREARS LIST ---\n"
                if not arrears_data.empty and 'Complex Name' in arrears_data.columns:
                    curr_arrears = arrears_data[arrears_data['Complex Name'] == b_choice].copy()
                    if not curr_arrears.empty:
                        for _, row in curr_arrears.iterrows():
                            dc_body += f"Unit: {row.get('Unit Number', '')} | Amt: R{row.get('Outstanding Amount', 0)}\n"
                            dc_body += f"   Attorney: {row.get('Attorney Name', 'None')} ({row.get('Attorney Email', '')} - {row.get('Attorney Phone', '')})\n"
                            dc_body += "   ----------------------------\n"
                    else:
                        dc_body += "(No arrears loaded)\n"
                else:
                    dc_body += "(No arrears loaded)\n"
                
                dc_body += "\nRegards,\nPretor Take-On Team"

                st.markdown("**Internal Handover**")
                
                if dc_sent_date and dc_sent_date != "None":
                    st.success(f"✅ Sent on: {dc_sent_date}")
                    if st.button("Unlock (New Units Added)", key="rst_dc_internal"):
                        update_email_status(b_choice, "Debt Collection Sent Date", "")
                        st.cache_data.clear()
                        st.rerun()
                else:
                    target_email = s_dict.get("Debt Collection", "")
                    col_a, col_b = st.columns([1, 1])
                    with col_a:
                        if target_email:
                            subject = urllib.parse.quote(f"Handover: {b_choice} - Debt Collection")
                            body = urllib.parse.quote(dc_body)
                            link = f'<a href="mailto:{target_email}?subject={subject}&body={body}" target="_blank" style="text-decoration:none; color:white; background-color:#FF4B4B; padding:8px 12px; border-radius:5px;">📧 Draft Email</a>'
                            st.markdown(link, unsafe_allow_html=True)
                        else:
                            st.warning("⚠️ Set Debt Collection Email in Global Settings")
                    with col_b:
                        if st.button("Mark Debt Collection Sent", key="btn_dc_internal"):
                            res = update_email_status(b_choice, "Debt Collection Sent Date")
                            if res == "SUCCESS":
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(f"Update failed: {res}. Check if 'Debt Collection Sent Date' column exists in Supabase.")

                st.divider()

                # External Attorney Notifications
                st.markdown("**External Attorney Notifications**")
                st.caption("Notify attorneys that Pretor is taking over.")
                
                att_sent_date = get_val("Attorney Email Sent Date")
                
                if att_sent_date and att_sent_date != "None":
                    st.success(f"✅ Attorneys Notified on {att_sent_date}")
                    if st.button("Unlock (New Units Added)", key="rst_att_ext"):
                        update_email_status(b_choice, "Attorney Email Sent Date", "")
                        st.cache_data.clear()
                        st.rerun()
                else:
                    if not arrears_data.empty and 'Complex Name' in arrears_data.columns:
                        curr_arrears = arrears_data[arrears_data['Complex Name'] == b_choice].copy()
                        
                        if not curr_arrears.empty:
                            attorneys = curr_arrears.dropna(subset=['Attorney Email'])
                            unique_emails = attorneys['Attorney Email'].unique()
                            
                            legal_dept_email = s_dict.get("Debt Collection", "")
                            pm_name = get_val("Assigned Manager")
                            pm_email = get_val("Manager Email")

                            for att_email in unique_emails:
                                if not att_email: continue
                                
                                att_rows = curr_arrears[curr_arrears['Attorney Email'] == att_email]
                                att_name = att_rows.iloc[0].get('Attorney Name', 'Attorney')
                                
                                att_body = f"Dear {att_name},\n\n"
                                att_body += f"Please be advised that Pretor Group has been appointed as the managing agents for {b_choice}.\n\n"
                                att_body += "We note that you are currently handling collections for the following units:\n"
                                for _, r in att_rows.iterrows():
                                    att_body += f"- Unit {r['Unit Number']} (Outstanding: R{r.get('Outstanding Amount',0)})\n"
                                
                                att_body += "\nPlease direct all future communication regarding these matters to our Legal Department and the appointed Portfolio Manager:\n\n"
                                att_body += f"**Legal Department:** {legal_dept_email}\n"
                                att_body += f"**Portfolio Manager:** {pm_name} ({pm_email})\n\n"
                                att_body += "Regards,\nPretor Take-On Team"
                                
                                att_sub = urllib.parse.quote(f"Handover: {b_choice} - Pretor Group Appointment")
                                att_bod = urllib.parse.quote(att_body)
                                
                                cc_list = []
                                if legal_dept_email: cc_list.append(legal_dept_email)
                                if pm_email: cc_list.append(pm_email)
                                cc_str = ",".join(cc_list)
                                
                                mailto_href = f"mailto:{att_email}?subject={att_sub}&body={att_bod}"
                                if cc_str:
                                    mailto_href += f"&cc={cc_str}"
                                    
                                st.markdown(f'<a href="{mailto_href}" target="_blank" style="text-decoration:none; color:white; background-color:#4CAF50; padding:6px 12px; border-radius:5px; margin-right:10px;">📧 Draft Email to {att_name}</a>', unsafe_allow_html=True)
                                st.write("") 
                            
                            st.divider()
                            if st.button("Mark Attorneys Notified"):
                                res = update_email_status(b_choice, "Attorney Email Sent Date")
                                if res == "SUCCESS":
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error(f"Update failed: {res}. Check if 'Attorney Email Sent Date' column exists in Supabase.")
                        else:
                            st.info("No attorneys loaded in Arrears Details.")
                    else:
                        st.info("No arrears data found.")

                st.divider()

                # 8. Fee Confirmation
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
                            st.cache_data.clear()
                            st.rerun()

                st.divider()

                # 9. Finalize
                st.markdown("### 🏁 Final Actions")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Finalize Project"):
                        finalize_project_db(b_choice)
                        st.cache_data.clear()
                        st.balloons()

if __name__ == "__main__":
    main()
