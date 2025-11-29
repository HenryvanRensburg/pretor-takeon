import streamlit as st
import pandas as pd
from database import (
    get_data, add_master_item, add_service_provider, add_employee, add_arrears_item, 
    add_council_account, add_trustee, delete_record_by_match, save_global_settings, 
    update_building_details_batch, create_new_building, update_project_agent_details, 
    save_checklist_batch, finalize_project_db, save_broker_details, update_email_status, 
    update_service_provider_date, update_wages_status, update_employee_batch, 
    update_council_batch, update_arrears_batch, login_user, log_access,
    upload_file_to_supabase, update_checklist_document  # Ensure these are imported
)
from pdf_generator import generate_appointment_pdf, generate_report_pdf, generate_weekly_report_pdf
import urllib.parse
from datetime import datetime
import os
import tempfile
import re
from fpdf import FPDF
from streamlit_option_menu import option_menu

# --- PAGE CONFIG ---
st.set_page_config(page_title="Pretor Take-On", layout="wide")

# --- VALIDATION HELPERS ---
def validate_email(email):
    if not email: return True 
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    if not phone: return True
    clean_phone = re.sub(r'[\s\-\(\)]', '', str(phone))
    return re.match(r'^0\d{9}$', clean_phone) is not None

def validate_sa_id(id_num):
    if not id_num: return True
    clean_id = str(id_num).strip()
    return re.match(r'^\d{13}$', clean_id) is not None

# --- PDF GENERATOR CLASS ---
class HandoverReport(FPDF):
    def clean_text(self, text):
        if text is None: return ""
        text = str(text)
        text = text.replace('“', '"').replace('”', '"').replace('’', "'").replace('–', '-')
        return text.encode('latin-1', 'replace').decode('latin-1')

    def header(self):
        if os.path.exists("pretor_logo.png"):
            self.image("pretor_logo.png", 10, 8, 33)
        self.set_font('Arial', 'B', 14)
        self.cell(80)
        self.cell(30, 10, 'Comprehensive Handover Report', 0, 0, 'C')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def section_title(self, label):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 8, self.clean_text(label), 0, 1, 'L', 1)
        self.ln(2)

    def entry_row(self, label, value):
        self.set_font('Arial', 'B', 10)
        self.cell(50, 6, self.clean_text(label), 0)
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 6, self.clean_text(str(value)))

def create_comprehensive_pdf(complex_name, p_row, checklist_df, emp_df, arrears_df, council_df):
    pdf = HandoverReport()
    pdf.add_page()
    
    # 1. OVERVIEW
    pdf.section_title(f"1. Overview: {complex_name}")
    pdf.ln(2)
    overview_fields = {
        "Building Code": "Building Code", "Type": "Type", "Units": "No of Units",
        "Year End": "Year End", "Address": "Physical Address",
        "Portfolio Manager": "Assigned Manager", "PM Email": "Manager Email",
        "Bookkeeper": "Bookkeeper", "Tax Number": "Tax Number", "VAT Number": "VAT Number"
    }
    for label, db_col in overview_fields.items():
        val = p_row.get(db_col, 'N/A')
        pdf.entry_row(label + ":", val)
    pdf.ln(5)

    # 2. PREVIOUS AGENT
    pdf.section_title("2. Items Received from Previous Agent")
    if not checklist_df.empty:
        agent_items = checklist_df[
            (checklist_df['Responsibility'].isin(['Previous Agent', 'Both'])) & 
            (checklist_df['Received'].astype(str).str.lower() == 'true')
        ]
        if not agent_items.empty:
            pdf.set_font("Arial", "", 9)
            for _, row in agent_items.iterrows():
                t_name = pdf.clean_text(row['Task Name'])
                d_rec = pdf.clean_text(str(row.get('Date Received', '')))
                
                # Show link in PDF if exists
                doc_url = row.get('Document URL')
                doc_txt = " (See attached doc)" if doc_url else ""
                
                notes = f" (Note: {pdf.clean_text(str(row['Notes']))})" if row['Notes'] else ""
                pdf.cell(10)
                pdf.multi_cell(0, 5, f"- {t_name}{notes}{doc_txt} [Received: {d_rec}]")
        else:
            pdf.set_font("Arial", "I", 9)
            pdf.cell(0, 6, "No items marked as received from agent yet.", 0, 1)
    else:
        pdf.cell(0, 6, "No checklist data.", 0, 1)
    pdf.ln(5)

    # 3. INTERNAL
    pdf.section_title("3. Internal Pretor Actions Completed")
    if not checklist_df.empty:
        pretor_items = checklist_df[
            (checklist_df['Responsibility'].isin(['Pretor Group', 'Both'])) & 
            (checklist_df['Received'].astype(str).str.lower() == 'true')
        ]
        if not pretor_items.empty:
            pdf.set_font("Arial", "", 9)
            for _, row in pretor_items.iterrows():
                t_name = pdf.clean_text(row['Task Name'])
                pdf.cell(10)
                pdf.multi_cell(0, 5, f"- {t_name} (Completed)")
        else:
            pdf.set_font("Arial", "I", 9)
            pdf.cell(0, 6, "No internal actions completed yet.", 0, 1)
    else:
        pdf.cell(0, 6, "No checklist data.", 0, 1)
    pdf.ln(5)

    # 4. STAFF
    pdf.section_title("4. Staff & Wages Loaded")
    if not emp_df.empty and 'Complex Name' in emp_df.columns:
        c_emp = emp_df[emp_df['Complex Name'] == complex_name]
        if not c_emp.empty:
            pdf.set_font("Arial", "B", 8)
            pdf.cell(50, 6, "Name", 1)
            pdf.cell(50, 6, "Position", 1)
            pdf.cell(30, 6, "Salary", 1)
            pdf.cell(30, 6, "Docs?", 1)
            pdf.ln()
            pdf.set_font("Arial", "", 8)
            for _, row in c_emp.iterrows():
                name = pdf.clean_text(f"{row.get('Name','')} {row.get('Surname','')}")
                pos = pdf.clean_text(str(row.get('Position','')))
                sal = f"R {row.get('Salary',0)}"
                has_docs = "Yes" if str(row.get('Contract Received', 'False')).lower() == 'true' else "No"
                pdf.cell(50, 6, name, 1)
                pdf.cell(50, 6, pos, 1)
                pdf.cell(30, 6, sal, 1)
                pdf.cell(30, 6, has_docs, 1)
                pdf.ln()
        else:
            pdf.cell(0, 6, "No staff loaded.", 0, 1)
    else:
        pdf.cell(0, 6, "No staff data.", 0, 1)
    pdf.ln(5)

    # 5. ARREARS
    pdf.section_title("5. Arrears Handover")
    if not arrears_df.empty and 'Complex Name' in arrears_df.columns:
        c_arr = arrears_df[arrears_df['Complex Name'] == complex_name]
        if not c_arr.empty:
            pdf.set_font("Arial", "B", 8)
            pdf.cell(30, 6, "Unit", 1)
            pdf.cell(40, 6, "Outstanding", 1)
            pdf.cell(90, 6, "Attorney", 1)
            pdf.ln()
            pdf.set_font("Arial", "", 8)
            for _, row in c_arr.iterrows():
                unit = pdf.clean_text(str(row.get('Unit Number','')))
                amt = f"R {row.get('Outstanding Amount',0)}"
                att = pdf.clean_text(str(row.get('Attorney Name','')))
                pdf.cell(30, 6, unit, 1)
                pdf.cell(40, 6, amt, 1)
                pdf.cell(90, 6, att, 1)
                pdf.ln()
        else:
            pdf.cell(0, 6, "No arrears loaded.", 0, 1)
    else:
        pdf.cell(0, 6, "No arrears data.", 0, 1)
    pdf.ln(5)

    # 6. COUNCIL
    pdf.section_title("6. Council Accounts")
    if not council_df.empty and 'Complex Name' in council_df.columns:
        c_coun = council_df[council_df['Complex Name'] == complex_name]
        if not c_coun.empty:
            pdf.set_font("Arial", "B", 8)
            pdf.cell(60, 6, "Account Number", 1)
            pdf.cell(50, 6, "Service", 1)
            pdf.cell(40, 6, "Balance", 1)
            pdf.ln()
            pdf.set_font("Arial", "", 8)
            for _, row in c_coun.iterrows():
                acc = pdf.clean_text(str(row.get('Account Number','')))
                svc = pdf.clean_text(str(row.get('Service','')))
                bal = f"R {row.get('Balance',0)}"
                pdf.cell(60, 6, acc, 1)
                pdf.cell(50, 6, svc, 1)
                pdf.cell(40, 6, bal, 1)
                pdf.ln()
        else:
            pdf.cell(0, 6, "No council accounts loaded.", 0, 1)
    else:
        pdf.cell(0, 6, "No council data.", 0, 1)
    pdf.ln(5)

    # 7. DATES
    pdf.section_title("7. Internal Department Handover Dates")
    pdf.set_font("Arial", "", 10)
    handovers = {
        "Wages Dept": p_row.get("Wages Sent Date"),
        "Council Dept": p_row.get("Council Email Sent Date"),
        "Legal/Debt Dept": p_row.get("Debt Collection Sent Date"),
        "Insurance (Internal)": p_row.get("Internal Ins Email Sent Date"),
        "SARS": p_row.get("SARS Sent Date"),
        "Attorneys Notified": p_row.get("Attorney Email Sent Date")
    }
    for dept, date in handovers.items():
        status = f"{date}" if (date and date != "None") else "Pending"
        pdf.cell(60, 6, f"{dept}:", 0)
        pdf.cell(0, 6, status, 0, 1)

    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, f"Handover_Report_{complex_name}.pdf")
    pdf.output(file_path)
    return file_path

# --- LOGIN SCREEN ---
def login_screen():
    st.markdown("## 🔐 Pretor Take-On: Staff Login")
    with st.form("login_form"):
        email = st.text_input("Email Address")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Log In")
        
        if submit:
            user, error = login_user(email, password)
            if user:
                st.session_state['user'] = user
                st.session_state['user_email'] = user.email
                log_access(user.email)
                st.success("Login successful!")
                st.rerun()
            else:
                st.error(f"Login Failed: {error}")
                st.caption("Check 'Authentication > Users' in Supabase Dashboard.")

# --- MAIN APP ---
def main_app():
    st.sidebar.title("👤 User Info")
    st.sidebar.info(f"Logged in as:\n{st.session_state['user_email']}")
    if st.sidebar.button("Log Out"):
        st.session_state.clear()
        st.rerun()

    if os.path.exists("pretor_logo.png"):
        st.sidebar.image("pretor_logo.png", use_container_width=True)
    st.title("🏢 Pretor Group: Take-On Manager")

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
                if checklist.empty: total, received = 0, 0
                else:
                    c_items = checklist[checklist['Complex Name'] == c_name]
                    valid = c_items[c_items['Delete'] != True] 
                    pretor = valid[valid['Responsibility'].isin(['Pretor Group', 'Both'])]
                    total = len(pretor)
                    received = len(pretor[pretor['Received'].apply(lambda x: str(x).lower() == 'true')])
                progress_val = (received / total) if total > 0 else 0
                status = "✅ Completed" if progress_val == 1.0 else "⚠️ Near Completion" if progress_val > 0.8 else "🔄 In Progress" if progress_val > 0.1 else "🆕 Just Started"
                summary_list.append({"Complex Name": c_name, "Manager": row.get('Assigned Manager', ''), "Take On Date": row.get('Take On Date', ''), "Progress": progress_val, "Status": status, "Items Pending": total - received})
            summ_df = pd.DataFrame(summary_list)
            st.dataframe(summ_df, column_config={"Progress": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=1)}, hide_index=True)
            if st.button("Download Weekly Report PDF"):
                pdf = generate_weekly_report_pdf(summary_list)
                with open(pdf, "rb") as f: st.download_button("⬇️ Download PDF", f, file_name=pdf)
        else: st.info("No projects found.")

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
                st.cache_data.clear(); st.success("Added!"); st.rerun()
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
                # --- VALIDATION ---
                errors = []
                if wages and not validate_email(wages): errors.append("Invalid Wages Email")
                if sars and not validate_email(sars): errors.append("Invalid SARS Email")
                if muni and not validate_email(muni): errors.append("Invalid Municipal Email")
                if debt and not validate_email(debt): errors.append("Invalid Debt Email")
                if ins and not validate_email(ins): errors.append("Invalid Insurance Email")
                if acc and not validate_email(acc): errors.append("Invalid Accounts Email")
                
                if errors:
                    for e in errors: st.error(e)
                else:
                    save_global_settings({"Wages": wages, "SARS": sars, "Municipal": muni, "Debt Collection": debt, "Insurance": ins, "Accounts": acc})
                    st.cache_data.clear(); st.success("Saved!"); st.rerun()

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
                    data = {"Complex Name": name, "Type": b_type, "Take On Date": str(tod), "No of Units": units, "TakeOn Name": tom, "Assigned Manager": pm, "Year End": ye, "Mgmt Fees": fees, "Building Code": bcode, "Date Doc Requested": str(datetime.today())}
                    res = create_new_building(data)
                    st.cache_data.clear()
                    if res == "SUCCESS": st.success("Created!"); st.rerun()
                    elif res == "EXISTS": st.error("Exists already.")
                else: st.error("Name required.")

    # --- MANAGE BUILDINGS ---
    elif choice == "Manage Buildings":
        projs = get_data("Projects")
        if projs.empty: st.warning("No projects.")
        else:
            b_choice = st.selectbox("Select Complex", projs['Complex Name'])
            p_row = projs[projs['Complex Name'] == b_choice].iloc[0]
            def get_val(col): return str(p_row.get(col, ''))

            st.divider()
            sub_nav = option_menu(
                menu_title=None,
                options=["Overview", "Progress Tracker", "Staff Details", "Arrears Details", "Council Details", "Department Handovers", "Client Updates"],
                icons=["house", "list-task", "people", "cash-coin", "building", "envelope", "person-check"],
                menu_icon="cast",
                default_index=0,
                orientation="horizontal",
                styles={
                    "container": {"padding": "0!important"},
                    "icon": {"color": "orange", "font-size": "16px"}, 
                    "nav-link": {"font-size": "14px", "text-align": "center", "margin": "0px"},
                    "nav-link-selected": {"background-color": "#FF4B4B"},
                }
            )
            st.divider()

            if sub_nav == "Overview":
                st.subheader(f"Project Overview: {b_choice}")
                
                # --- MINI DASHBOARD ---
                checklist = get_data("Checklist")
                arrears = get_data("Arrears")
                staff = get_data("Employees")
                council = get_data("Council")
                
                c_checklist = checklist[checklist['Complex Name'] == b_choice] if not checklist.empty else pd.DataFrame()
                total_tasks = len(c_checklist)
                done_tasks = len(c_checklist[c_checklist['Received'].astype(str).str.lower() == 'true']) if not c_checklist.empty else 0
                prog_val = done_tasks / total_tasks if total_tasks > 0 else 0
                
                # FIX: Force numeric conversion for arrears summary
                c_arrears = pd.DataFrame()
                debt_val = 0.0
                if not arrears.empty and 'Complex Name' in arrears.columns:
                    c_arrears = arrears[arrears['Complex Name'] == b_choice]
                    if not c_arrears.empty and 'Outstanding Amount' in c_arrears.columns:
                        numeric_amounts = pd.to_numeric(c_arrears['Outstanding Amount'], errors='coerce').fillna(0)
                        debt_val = numeric_amounts.sum()
                
                c_staff = staff[staff['Complex Name'] == b_choice] if not staff.empty and 'Complex Name' in staff.columns else pd.DataFrame()
                staff_count = len(c_staff)
                
                c_coun = council[council['Complex Name'] == b_choice] if not council.empty and 'Complex Name' in council.columns else pd.DataFrame()
                coun_count = len(c_coun)

                col_d1, col_d2, col_d3, col_d4 = st.columns(4)
                col_d1.metric("Checklist Progress", f"{int(prog_val*100)}%")
                col_d1.progress(prog_val)
                col_d2.metric("Total Arrears", f"R {debt_val:,.2f}")
                col_d3.metric("Staff Loaded", staff_count)
                col_d4.metric("Council Accounts", coun_count)
                
                tax_check = get_val("Tax Number")
                if not tax_check or tax_check == 'None': st.warning("⚠️ Alert: Tax Number is missing!")
                st.divider()

                with st.form("project_overview_form"):
                    st.caption("Fields with existing data are locked 🔒.")
                    def smart_input(label, col_name, col_obj=st):
                        curr_val = str(p_row.get(col_name, ''))
                        has_data = bool(curr_val and curr_val.lower() not in ["none", "nan", ""])
                        return col_obj.text_input(label, value=curr_val if has_data else "", disabled=has_data, key=f"ov_{col_name}", placeholder="Enter detail...")
                    st.markdown("#### 📍 General & Address")
                    c1, c2, c3 = st.columns(3)
                    with c1: u_code = smart_input("Building Code", "Building Code", c1); u_type = smart_input("Type (BC/HOA)", "Type", c1)
                    with c2: u_units = smart_input("No of Units", "No of Units", c2); u_ss = smart_input("SS Number", "SS Number", c2)
                    with c3: u_erf = smart_input("Erf Number", "Erf Number", c3); u_csos = smart_input("CSOS Number", "CSOS Number", c3)
                    st.markdown(""); u_addr = smart_input("Physical Address", "Physical Address", st)
                    st.markdown("#### 💰 Financial & Compliance")
                    c4, c5, c6 = st.columns(3)
                    with c4: u_ye = smart_input("Year End", "Year End", c4); u_fees = smart_input("Mgmt Fees", "Mgmt Fees", c4); u_exp = smart_input("Expense Code", "Expense Code", c4)
                    with c5: u_vat = smart_input("VAT Number", "VAT Number", c5); u_tax = smart_input("Tax Number", "Tax Number", c5); u_tod = smart_input("Take On Date", "Take On Date", c5)
                    with c6: u_aud = smart_input("Auditor", "Auditor", c6); u_last_aud = smart_input("Last Audit", "Last Audit", c6)
                    st.markdown("#### 👥 The Team")
                    c7, c8, c9 = st.columns(3)
                    with c7: u_pm = smart_input("Portfolio Manager", "Assigned Manager", c7); u_pm_e = smart_input("PM Email", "Manager Email", c7); u_client_e = smart_input("Client Email", "Client Email", c7)
                    with c8: u_pa = smart_input("Portfolio Assistant", "Portfolio Assistant", c8); u_pa_e = smart_input("PA Email", "Portfolio Assistant Email", c8); u_tom = smart_input("Take-On Manager", "TakeOn Name", c8)
                    with c9: u_bk = smart_input("Bookkeeper", "Bookkeeper", c9); u_bk_e = smart_input("Bookkeeper Email", "Bookkeeper Email", c9)
                    st.markdown("---")
                    if st.form_submit_button("💾 Save Missing Details"):
                        # --- VALIDATION ---
                        errors = []
                        if u_pm_e and not validate_email(u_pm_e): errors.append("Invalid PM Email")
                        if u_client_e and not validate_email(u_client_e): errors.append("Invalid Client Email")
                        if u_pa_e and not validate_email(u_pa_e): errors.append("Invalid PA Email")
                        if u_bk_e and not validate_email(u_bk_e): errors.append("Invalid Bookkeeper Email")

                        if errors:
                            for e in errors: st.error(e)
                        else:
                            updates = {"Building Code": u_code, "Type": u_type, "No of Units": u_units, "SS Number": u_ss, "Erf Number": u_erf, "CSOS Number": u_csos, "Physical Address": u_addr, "Year End": u_ye, "Mgmt Fees": u_fees, "Expense Code": u_exp, "VAT Number": u_vat, "Tax Number": u_tax, "Take On Date": u_tod, "Auditor": u_aud, "Last Audit": u_last_aud, "Assigned Manager": u_pm, "Manager Email": u_pm_e, "Client Email": u_client_e, "Portfolio Assistant": u_pa, "Portfolio Assistant Email": u_pa_e, "TakeOn Name": u_tom, "Bookkeeper": u_bk, "Bookkeeper Email": u_bk_e}
                            update_building_details_batch(b_choice, updates); st.cache_data.clear(); st.success("Updated."); st.rerun()
                
                st.markdown("### Previous Agent Request")
                c1, c2 = st.columns(2)
                an = c1.text_input("Agent Name", value=get_val("Agent Name"))
                ae = c2.text_input("Agent Email", value=get_val("Agent Email"))
                if st.button("Generate Request PDF"):
                    # VALIDATE AGENT EMAIL
                    if ae and not validate_email(ae):
                        st.error("Invalid Agent Email Address")
                    else:
                        update_project_agent_details(b_choice, an, ae); st.cache_data.clear()
                        items = get_data("Checklist")
                        req = items[(items['Complex Name'] == b_choice) & (items['Responsibility'] != 'Pretor Group')]
                        pdf = generate_appointment_pdf(b_choice, req, an, get_val("Take On Date"), get_val("Year End"), get_val("Building Code"))
                        with open(pdf, "rb") as f: st.download_button("Download PDF", f, file_name=pdf)

            elif sub_nav == "Progress Tracker":
                st.markdown("### Checklist")
                items = get_data("Checklist")
                if not items.empty:
                    c_items = items[items['Complex Name'] == b_choice].copy()
                    c_items['Received'] = c_items['Received'].apply(lambda x: True if str(x).lower() == 'true' else False)
                    if 'Delete' in c_items.columns: c_items['Delete'] = c_items['Delete'].apply(lambda x: True if str(x).lower() == 'true' else False)
                    df_pending = c_items[(c_items['Received'] == False) & (c_items['Delete'] != True)]
                    df_completed = c_items[(c_items['Received'] == True) | (c_items['Delete'] == True)]
                    def fill_date(row):
                        if row['Received'] and (pd.isna(row['Date Received']) or str(row['Date Received']).strip() == ''): return str(datetime.now().date())
                        return row['Date Received']
                    
                    st.markdown("#### 📝 Pending Actions")
                    t1, t2 = st.tabs(["① Previous Agent Pending", "② Internal Pending"])
                    sections = ["Take-On", "Financial", "Legal", "Statutory Compliance", "Insurance", "City Council", "Building Compliance", "Employee", "General"]
                    with t1:
                        if not df_pending.empty:
                            ag_pend = df_pending[df_pending['Responsibility'].isin(['Previous Agent', 'Both'])].copy()
                            if not ag_pend.empty:
                                ag_pend['Sort'] = ag_pend['Task Heading'].apply(lambda x: sections.index(x) if x in sections else 99)
                                ag_pend = ag_pend.sort_values(by=['Sort', 'Task Name'])
                                
                                # --- DOCUMENT UPLOAD COLUMN (OPTIONAL) ---
                                st.markdown("##### Select Item to Upload Document (Optional)")
                                item_names = ag_pend['Task Name'].tolist()
                                selected_item = st.selectbox("Choose Checklist Item", ["None"] + item_names)
                                
                                if selected_item != "None":
                                    uploaded_file = st.file_uploader(f"Upload Document for: {selected_item}")
                                    if uploaded_file:
                                        if st.button("Upload & Mark as Received"):
                                            # 1. Find Item ID
                                            item_id = ag_pend[ag_pend['Task Name'] == selected_item].iloc[0]['id']
                                            
                                            # 2. Upload to Supabase
                                            file_path = f"{b_choice}/{selected_item}_{uploaded_file.name}"
                                            doc_url = upload_file_to_supabase(uploaded_file, file_path)
                                            
                                            if doc_url:
                                                # 3. Update DB with URL + Mark Received
                                                update_checklist_document(item_id, doc_url)
                                                # We also need to mark it received in the main logic, but for now user can tick it.
                                                # Better: Auto-tick the dataframe row? Hard in editor.
                                                # Best: Use a direct DB update for 'Received' too
                                                # ... (Simplification: User ticks box after upload or we force update)
                                                st.success(f"Uploaded! Please tick '{selected_item}' below and Save.")
                                
                                st.divider()
                                
                                edited_ag = st.data_editor(ag_pend[['id', 'Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes', 'Delete']], hide_index=True, height=400, key="ag_ed", column_config={"id": None, "Task Heading": st.column_config.TextColumn(disabled=True), "Task Name": st.column_config.TextColumn(disabled=True)})
                                if st.button("Save Agent Items"):
                                    edited_ag['Date Received'] = edited_ag.apply(fill_date, axis=1)
                                    save_checklist_batch(b_choice, edited_ag, st.session_state.get('user_email', 'Unknown')); st.cache_data.clear(); st.success("Saved!"); st.rerun()
                                st.divider()
                                agent_email = get_val("Agent Email")
                                if agent_email and agent_email != "None":
                                    e_list = "".join([f"- {r['Task Name']}\n" for _, r in ag_pend.iterrows()])
                                    sub = urllib.parse.quote(f"Outstanding Handover Items: {b_choice}")
                                    bod = f"Dear Agent,\n\nOutstanding items:\n{e_list}\nPlease handover ASAP by the 10th.\n\nRegards, Pretor"
                                    st.markdown(f'<a href="mailto:{agent_email}?subject={sub}&body={urllib.parse.quote(bod)}" target="_blank" style="background-color:#FF4B4B;color:white;padding:8px;border-radius:5px;text-decoration:none;">📧 Follow Up Email</a>', unsafe_allow_html=True)
                            else: st.info("No pending items.")
                        else:
                             ag_comp = c_items[(c_items['Responsibility'].isin(['Previous Agent', 'Both'])) & (c_items['Received'] == True)]
                             if not ag_comp.empty:
                                 try: last_d = pd.to_datetime(ag_comp['Date Received'], errors='coerce').max().strftime('%Y-%m-%d')
                                 except: last_d = "Unknown"
                                 st.success(f"✅ All items received! Last: **{last_d}**")
                                 
                                 st.divider()
                                 st.markdown("#### 🚀 Take-On Complete: Notify Client")
                                 comp_date = get_val("Client Completion Email Sent Date")
                                 rep_date = get_val("Client Report Generated Date")
                                 
                                 st.markdown("**Step 1: Generate Handover Report**")
                                 if rep_date and rep_date != "None":
                                     st.success(f"✅ Generated: {rep_date}")
                                     emp_df, arr_df, cou_df = get_data("Employees"), get_data("Arrears"), get_data("Council")
                                     pdf_f = create_comprehensive_pdf(b_choice, p_row, c_items, emp_df, arr_df, cou_df)
                                     with open(pdf_f, "rb") as f: st.download_button("⬇️ Download Copy", f, file_name=pdf_f, mime="application/pdf")
                                     if st.button("Unlock (Regenerate Report)", key="unlock_rep"): update_email_status(b_choice, "Client Report Generated Date", ""); st.cache_data.clear(); st.rerun()
                                 else:
                                     if st.button("📄 Generate & Lock Report", key="gen_pdf_comp"):
                                         emp_df, arr_df, cou_df = get_data("Employees"), get_data("Arrears"), get_data("Council")
                                         create_comprehensive_pdf(b_choice, p_row, c_items, emp_df, arr_df, cou_df)
                                         update_email_status(b_choice, "Client Report Generated Date")
                                         st.cache_data.clear(); st.rerun()

                                 st.markdown("**Step 2: Email Client**")
                                 if comp_date and comp_date != "None":
                                     st.success(f"✅ Sent: {comp_date}")
                                     if st.button("Unlock Email", key="unlock_comp"): update_email_status(b_choice, "Client Completion Email Sent Date", ""); st.cache_data.clear(); st.rerun()
                                 else:
                                     c_mail = get_val("Client Email")
                                     if c_mail and c_mail != "None":
                                         bod = "Dear Client,\n\nTake-on complete.\n\nRegards, Pretor"
                                         sub = urllib.parse.quote(f"Completed: {b_choice}")
                                         lnk = f'<a href="mailto:{c_mail}?subject={sub}&body={urllib.parse.quote(bod)}" target="_blank" style="background-color:#09ab3b;color:white;padding:10px;border-radius:5px;text-decoration:none;">🚀 Draft Email</a>'
                                         st.markdown(lnk, unsafe_allow_html=True)
                                         st.write("")
                                         if st.button("Mark as Sent", key="mark_comp"): update_email_status(b_choice, "Client Completion Email Sent Date"); st.cache_data.clear(); st.rerun()
                                     else: st.warning("No Client Email.")
                             else: st.info("No agent items.")
                    with t2:
                         if not df_pending.empty:
                            int_pend = df_pending[df_pending['Responsibility'].isin(['Pretor Group', 'Both'])].copy()
                            if not int_pend.empty:
                                int_pend['Sort'] = int_pend['Task Heading'].apply(lambda x: sections.index(x) if x in sections else 99)
                                int_pend = int_pend.sort_values(by=['Sort', 'Task Name'])
                                ed_int = st.data_editor(int_pend[['id', 'Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes', 'Delete']], hide_index=True, height=400, key="int_ed", column_config={"id": None, "Task Heading": st.column_config.TextColumn(disabled=True), "Task Name": st.column_config.TextColumn(disabled=True)})
                                if st.button("Save Internal Items"):
                                    ed_int['Date Received'] = ed_int.apply(fill_date, axis=1)
                                    save_checklist_batch(b_choice, ed_int, st.session_state.get('user_email', 'Unknown')); st.cache_data.clear(); st.success("Saved!"); st.rerun()
                            else: st.info("No pending internal.")
                         else: st.info("No pending.")
                    st.divider()
                    st.markdown("#### ✅ History")
                    if not df_completed.empty:
                        ah = df_completed[df_completed['Responsibility'].isin(['Previous Agent', 'Both'])]
                        ih = df_completed[df_completed['Responsibility'].isin(['Pretor Group', 'Both'])]
                        h1, h2 = st.tabs(["Agent History", "Internal History"])
                        with h1: st.dataframe(ah[['Task Heading', 'Task Name', 'Date Received', 'Notes', 'Completed By']], hide_index=True, use_container_width=True)
                        with h2: st.dataframe(ih[['Task Heading', 'Task Name', 'Date Received', 'Notes', 'Completed By']], hide_index=True, use_container_width=True)
                else: st.info("No checklist.")

            elif sub_nav == "Staff Details":
                st.subheader(f"Staff Management: {b_choice}")
                uif_val = get_val("UIF Number"); paye_val = get_val("PAYE Number"); coida_val = get_val("COIDA Number")
                locked = (uif_val and uif_val != 'None') or (paye_val and paye_val != 'None')
                st.markdown("#### 🏢 Project Statutory Numbers")
                if locked:
                    c1, c2, c3 = st.columns(3); c1.text_input("UIF", uif_val, disabled=True); c2.text_input("PAYE", paye_val, disabled=True); c3.text_input("COIDA", coida_val, disabled=True)
                else:
                    with st.form("stat"):
                        c1,c2,c3=st.columns(3); u=c1.text_input("UIF"); p=c2.text_input("PAYE"); c=c3.text_input("COIDA")
                        if st.form_submit_button("💾 Save & Lock"):
                            update_building_details_batch(b_choice, {"UIF Number": u, "PAYE Number": p, "COIDA Number": c}); st.cache_data.clear(); st.success("Saved"); st.rerun()
                st.divider(); st.markdown("#### 👥 Employee List")
                all_s = get_data("Employees")
                if not all_s.empty and 'Complex Name' in all_s.columns:
                    curr_s = all_s[all_s['Complex Name'] == b_choice].copy()
                    if not curr_s.empty:
                        cols = ['id', 'Name', 'Surname', 'Position', 'Salary']
                        ed_s = st.data_editor(curr_s[[c for c in cols if c in curr_s.columns]], hide_index=True, key="stf_ed", column_config={"id": None, "Salary": st.column_config.NumberColumn(format="R %.2f")})
                        if st.button("Save Staff"): update_employee_batch(ed_s); st.cache_data.clear(); st.success("Updated!"); st.rerun()
                    else: st.info("No staff.")
                st.divider(); st.markdown("#### ➕ Add New Employee")
                with st.form("add_s", clear_on_submit=True):
                    c1,c2 = st.columns(2); n=c1.text_input("Name"); s=c2.text_input("Surname")
                    e_id = st.text_input("ID Number", key="new_eid") # Use separate logic for ID field placement
                    if st.form_submit_button("Add"):
                         if validate_sa_id(e_id):
                             add_employee(b_choice, n, s, e_id, "", 0.0, False, False, False); st.cache_data.clear(); st.success("Added"); st.rerun()
                         else: st.error("Invalid ID Number")

            elif sub_nav == "Arrears Details":
                st.subheader("Arrears Management")
                ad = get_data("Arrears")
                if not ad.empty:
                    rename_map_arr = {'complex_name': 'Complex Name', 'unit_number': 'Unit Number', 'outstanding_amount': 'Outstanding Amount', 'attorney_name': 'Attorney Name', 'attorney_email': 'Attorney Email', 'attorney_phone': 'Attorney Phone'}
                    ad.rename(columns=rename_map_arr, inplace=True)
                if not ad.empty and 'Complex Name' in ad.columns:
                    curr_a = ad[ad['Complex Name'] == b_choice].copy()
                    if not curr_a.empty:
                         ed_a = st.data_editor(curr_a[['id', 'Unit Number', 'Outstanding Amount']], hide_index=True, key="arr_ed", column_config={"id": None, "Outstanding Amount": st.column_config.NumberColumn(format="R %.2f")})
                         if st.button("Save Arrears"): update_arrears_batch(ed_a); st.cache_data.clear(); st.success("Updated"); st.rerun()
                    else: st.info("No arrears.")
                with st.form("add_a", clear_on_submit=True):
                    u=st.text_input("Unit"); a=st.number_input("Amount"); m=st.text_input("Attorney Email"); p=st.text_input("Attorney Phone")
                    if st.form_submit_button("Add"):
                         # VALIDATE
                         errs = []
                         if m and not validate_email(m): errs.append("Invalid Email")
                         if p and not validate_phone(p): errs.append("Invalid Phone (10 digits)")
                         if errs: 
                             for e in errs: st.error(e)
                         else:
                             add_arrears_item(b_choice, u, a, "", m, p); st.cache_data.clear(); st.success("Added"); st.rerun()

            elif sub_nav == "Council Details":
                st.subheader("Council Management")
                cd = get_data("Council")
                if cd.empty: cd = get_data("council")
                if not cd.empty:
                    cd.columns = [c.strip() for c in cd.columns]
                    rename_map = {'complex_name': 'Complex Name', 'account_number': 'Account Number', 'service': 'Service', 'balance': 'Balance'}
                    cd.rename(columns=rename_map, inplace=True)
                if not cd.empty and 'Complex Name' in cd.columns:
                    curr_c = cd[cd['Complex Name'] == b_choice].copy()
                    if not curr_c.empty:
                        ed_c = st.data_editor(curr_c[['id', 'Account Number', 'Service']], hide_index=True, key="cou_ed", column_config={"id": None, "Balance": st.column_config.NumberColumn(format="R %.2f")})
                        if st.button("Save Council"): update_council_batch(ed_c); st.cache_data.clear(); st.success("Updated"); st.rerun()
                    else: st.info("No accounts.")
                with st.form("add_c", clear_on_submit=True):
                    a=st.text_input("Acc"); s=st.text_input("Svc")
                    if st.form_submit_button("Add"): add_council_account(b_choice, a, s, 0.0); st.cache_data.clear(); st.success("Added"); st.rerun()

            elif sub_nav == "Department Handovers":
                st.markdown("### Department Handovers")
                settings = get_data("Settings"); s_dict = dict(zip(settings["Department"], settings["Email"])) if not settings.empty else {}

                st.markdown("#### SARS")
                sars_sent = get_val("SARS Sent Date")
                if sars_sent and sars_sent != "None":
                    st.success(f"✅ Sent: {sars_sent}")
                    if st.button("Reset SARS"): update_email_status(b_choice, "SARS Sent Date", ""); st.cache_data.clear(); st.rerun()
                else:
                    if st.button("Mark SARS Sent"): update_email_status(b_choice, "SARS Sent Date"); st.cache_data.clear(); st.rerun()
                
                st.divider(); st.markdown("#### Council")
                c_sent = get_val("Council Email Sent Date")
                if c_sent and c_sent != "None":
                    st.success(f"✅ Sent: {c_sent}")
                    if st.button("Reset Council"): update_email_status(b_choice, "Council Email Sent Date", ""); st.cache_data.clear(); st.rerun()
                else:
                    if st.button("Mark Council Sent"): update_email_status(b_choice, "Council Email Sent Date"); st.cache_data.clear(); st.rerun()

                st.divider()
                def render_handover(name, col, email_key, custom_body=None):
                    st.markdown(f"#### {name}")
                    sent = get_val(col)
                    target = s_dict.get(email_key, "")
                    if sent and sent != "None":
                        st.success(f"✅ Sent: {sent}")
                        if st.button(f"Reset {name}", key=f"rst_{name}"): update_email_status(b_choice, col, ""); st.cache_data.clear(); st.rerun()
                    else:
                        c1, c2 = st.columns([1,1])
                        with c1:
                            if target:
                                body = custom_body if custom_body else f"Dear {name} Team,\n\nDocs attached.\n\nRegards."
                                lnk = f'<a href="mailto:{target}?subject=Handover: {b_choice}&body={urllib.parse.quote(body)}" target="_blank" style="background-color:#FF4B4B;color:white;padding:8px;border-radius:5px;text-decoration:none;">📧 Draft Email</a>'
                                st.markdown(lnk, unsafe_allow_html=True)
                        with c2:
                            if st.button(f"Mark {name} Sent", key=f"btn_{name}"): update_email_status(b_choice, col); st.cache_data.clear(); st.rerun()
                    st.divider()

                st.markdown("#### Insurance")
                with st.expander("Edit Broker"):
                     with st.form("eb"): 
                        bn=st.text_input("Name", get_val("Insurance Broker Name")); be=st.text_input("Email", get_val("Insurance Broker Email"))
                        if st.form_submit_button("Save"): 
                            if be and not validate_email(be): st.error("Invalid Email")
                            else: save_broker_details(b_choice, bn, be); st.cache_data.clear(); st.rerun()

                st.markdown("**External Broker**")
                b_sent = get_val("Broker Email Sent Date")
                if b_sent and b_sent != "None":
                    st.success(f"✅ Sent: {b_sent}")
                    if st.button("Reset Broker"): update_email_status(b_choice, "Broker Email Sent Date", ""); st.cache_data.clear(); st.rerun()
                else:
                    if st.button("Mark Broker Sent"): update_email_status(b_choice, "Broker Email Sent Date"); st.cache_data.clear(); st.rerun()

                st.markdown("**Internal Insurance**")
                render_handover("Internal Insurance", "Internal Ins Email Sent Date", "Insurance", f"Hi Insurance,\n\nDocs at: Y:\\HenryJ\\NEW BUSINESS & DEVELOPMENTS\\{b_choice}\\insurance\n\nRegards.")
                
                render_handover("Wages", "Wages Sent Date", "Wages", f"Dear Wages,\n\nDocs at: Y:\\HenryJ\\NEW BUSINESS & DEVELOPMENTS\\{b_choice}\\salaries&wages\n\nRegards.")
                
                render_handover("Debt Collection", "Debt Collection Sent Date", "Debt Collection")

                st.markdown("#### Fee Confirmation")
                fsent = get_val("Fee Confirmation Email Sent Date")
                if fsent and fsent != "None":
                     st.success(f"✅ Sent: {fsent}")
                     if st.button("Reset Fees"): update_email_status(b_choice, "Fee Confirmation Email Sent Date", ""); st.cache_data.clear(); st.rerun()
                else:
                     if st.button("Mark Fee Email Sent"): update_email_status(b_choice, "Fee Confirmation Email Sent Date"); st.cache_data.clear(); st.rerun()

            elif sub_nav == "Client Updates":
                st.subheader("Client Status Update")
                client_email = get_val("Client Email")
                if client_email and client_email != "None":
                    lnk = f'<a href="mailto:{client_email}?subject=Update&body=Update" target="_blank">Draft Update Email</a>'
                    st.markdown(lnk, unsafe_allow_html=True)
                else: st.warning("Add client email in Overview.")

            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Finalize Project"): finalize_project_db(b_choice); st.cache_data.clear(); st.balloons()

if __name__ == "__main__":
    if 'user' not in st.session_state: login_screen()
    else: main_app()
