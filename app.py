import streamlit as st
import pandas as pd
from database import (
    get_data, add_master_item, add_service_provider, add_employee, add_arrears_item, 
    add_council_account, add_trustee, delete_record_by_match, save_global_settings, 
    update_building_details_batch, create_new_building, update_project_agent_details, 
    save_checklist_batch, finalize_project_db, save_broker_details, update_email_status, 
    update_service_provider_date, update_wages_status, update_employee_batch, 
    update_council_batch, update_arrears_batch, login_user, log_access,
    upload_file_to_supabase, update_document_url, initialize_checklist
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

# ==========================================
# PDF GENERATORS
# ==========================================
class BasePDF(FPDF):
    def clean_text(self, text):
        if text is None: return ""
        text = str(text)
        text = text.replace('“', '"').replace('”', '"').replace('’', "'").replace('–', '-')
        return text.encode('latin-1', 'replace').decode('latin-1')
    def header(self):
        if os.path.exists("pretor_logo.png"): self.image("pretor_logo.png", 10, 8, 33)
        self.set_font('Arial', 'B', 14); self.cell(80); self.ln(20)
    def footer(self):
        self.set_y(-15); self.set_font('Arial', 'I', 8); self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

# --- 1. AGENT REQUEST PDF ---
class AgentRequestPDF(BasePDF):
    def section_header(self, title):
        self.set_font('Arial', 'B', 11); self.set_fill_color(230, 230, 230); self.cell(0, 8, self.clean_text(title), 0, 1, 'L', 1); self.ln(2)
    def add_item(self, text):
        self.set_font('Arial', '', 10); self.cell(10); self.multi_cell(0, 5, "- " + self.clean_text(text)); self.ln(1)

def generate_appointment_pdf(complex_name, checklist_df, agent_name, take_on_date, immediate_items_list):
    pdf = AgentRequestPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 14); pdf.cell(0, 10, 'Handover Request: Managing Agent Appointment', 0, 1, 'C'); pdf.ln(5)
    pdf.set_font('Arial', '', 10)
    intro = f"Dear {agent_name},\n\nWe confirm that Pretor Group has been appointed as the managing agents for {complex_name}, effective {take_on_date}.\n\nTo ensure a smooth transition, we require the following documentation. We have separated this request into items required immediately and items required at month-end closing."
    pdf.multi_cell(0, 5, pdf.clean_text(intro)); pdf.ln(5)
    
    # Split Dataframe
    df_immediate = checklist_df[checklist_df['Task Name'].isin(immediate_items_list)]
    df_month_end = checklist_df[~checklist_df['Task Name'].isin(immediate_items_list)]
    
    pdf.section_header("SECTION A: REQUIRED IMMEDIATELY")
    pdf.set_font('Arial', 'I', 9); pdf.multi_cell(0, 5, "Please provide the following documents at your earliest convenience."); pdf.ln(2)
    if not df_immediate.empty:
        for heading, group in df_immediate.groupby('Task Heading'):
            pdf.set_font('Arial', 'B', 9); pdf.cell(0, 6, pdf.clean_text(heading), 0, 1)
            for _, row in group.iterrows(): pdf.add_item(row['Task Name'])
            pdf.ln(2)
    else: pdf.add_item("No immediate items listed.")
    pdf.ln(5)

    pdf.section_header("SECTION B: REQUIRED BY MONTH END")
    pdf.set_font('Arial', 'I', 9); pdf.multi_cell(0, 5, "Please provide the following records once the month has been closed (by the 10th)."); pdf.ln(2)
    if not df_month_end.empty:
        for heading, group in df_month_end.groupby('Task Heading'):
            pdf.set_font('Arial', 'B', 9); pdf.cell(0, 6, pdf.clean_text(heading), 0, 1)
            for _, row in group.iterrows(): pdf.add_item(row['Task Name'])
            pdf.ln(2)
    else: pdf.add_item("No month-end items listed.")
    
    pdf.ln(5); pdf.set_font('Arial', 'B', 10); pdf.cell(0, 10, "We look forward to working with you during this handover.", 0, 1)
    temp_dir = tempfile.gettempdir(); filename = os.path.join(temp_dir, f"Agent_Request_{complex_name}.pdf"); pdf.output(filename); return filename

# --- 2. CLIENT REPORT PDF ---
class ClientReport(BasePDF):
    def section_title(self, label):
        self.set_font('Arial', 'B', 12); self.set_fill_color(200, 220, 255); self.cell(0, 8, self.clean_text(label), 0, 1, 'L', 1); self.ln(2)
    def entry_row(self, label, value):
        self.set_font('Arial', 'B', 9); self.cell(55, 5, self.clean_text(label), 0); self.set_font('Arial', '', 9); self.multi_cell(0, 5, self.clean_text(str(value)))

def create_comprehensive_pdf(complex_name, p_row, checklist_df, emp_df, arrears_df, council_df):
    pdf = ClientReport(); pdf.add_page()
    pdf.cell(80); pdf.cell(30, 10, 'Comprehensive Handover Report', 0, 0, 'C'); pdf.ln(20)
    
    pdf.section_title(f"1. Overview: {complex_name}"); pdf.ln(2)
    fields = {"Building Code":"Building Code","Type":"Type","Units":"No of Units","Year End":"Year End","Address":"Physical Address","Manager":"Assigned Manager","Email":"Manager Email"}
    for k,v in fields.items(): pdf.entry_row(k, p_row.get(v,''))
    pdf.ln(5)
    
    pdf.section_title("2. Items Received from Previous Agent"); pdf.ln(2)
    if not checklist_df.empty:
        agent_items = checklist_df[(checklist_df['Responsibility'].isin(['Previous Agent', 'Both'])) & (checklist_df['Received'].astype(str).str.lower() == 'true')]
        if not agent_items.empty:
            pdf.set_font("Arial", "", 9)
            for _, row in agent_items.iterrows():
                pdf.cell(5); pdf.multi_cell(0, 5, f"- {pdf.clean_text(row['Task Name'])} (Rec: {row.get('Date Received','')})")
        else: pdf.cell(0, 6, "None received yet.", 0, 1)
    else: pdf.cell(0, 6, "No data.", 0, 1)
    pdf.ln(4)

    pdf.section_title("3. Internal Actions Completed"); pdf.ln(2)
    if not checklist_df.empty:
        pretor_items = checklist_df[(checklist_df['Responsibility'].isin(['Pretor Group', 'Both'])) & (checklist_df['Received'].astype(str).str.lower() == 'true')]
        if not pretor_items.empty:
            pdf.set_font("Arial", "", 9)
            for _, row in pretor_items.iterrows():
                pdf.cell(5); pdf.multi_cell(0, 5, f"- {pdf.clean_text(row['Task Name'])}")
        else: pdf.cell(0, 6, "None completed yet.", 0, 1)
    else: pdf.cell(0, 6, "No data.", 0, 1)
    pdf.ln(4)

    pdf.section_title("4. Staff Loaded"); pdf.ln(2)
    if not emp_df.empty:
        c_emp = emp_df[emp_df['Complex Name'] == complex_name]
        if not c_emp.empty:
            pdf.set_font("Arial", "B", 8); pdf.cell(60, 6, "Name", 1); pdf.cell(50, 6, "Position", 1); pdf.cell(30, 6, "Salary", 1); pdf.ln()
            pdf.set_font("Arial", "", 8)
            for _, row in c_emp.iterrows():
                pdf.cell(60, 6, pdf.clean_text(f"{row.get('Name','')} {row.get('Surname','')}"), 1)
                pdf.cell(50, 6, pdf.clean_text(str(row.get('Position',''))), 1)
                pdf.cell(30, 6, f"R{row.get('Salary',0)}", 1); pdf.ln()
        else: pdf.cell(0, 6, "No staff.", 0, 1)
    else: pdf.cell(0, 6, "No data.", 0, 1)
    pdf.ln(4)

    pdf.section_title("5. Department Handovers"); pdf.ln(2)
    pdf.set_font("Arial", "", 9)
    handovers = { "Wages": "Wages Sent Date", "Council": "Council Email Sent Date", "Debt": "Debt Collection Sent Date", "SARS": "SARS Sent Date" }
    for k, v in handovers.items():
        d = p_row.get(v)
        st_txt = f"Done ({d})" if d and d != "None" else "Pending"
        pdf.cell(40, 6, k+":", 0); pdf.cell(0, 6, st_txt, 0, 1)
    
    temp_dir = tempfile.gettempdir()
    filename = os.path.join(temp_dir, f"Handover_Report_{complex_name}.pdf")
    pdf.output(filename); return filename

# --- LOGIN ---
def login_screen():
    st.markdown("## 🔐 Staff Login")
    with st.form("login"):
        e = st.text_input("Email"); p = st.text_input("Password", type="password")
        if st.form_submit_button("Log In"):
            u, err = login_user(e, p)
            if u: st.session_state['user'] = u; st.session_state['user_email'] = u.email; log_access(u.email); st.rerun()
            else: st.error(err)

# --- MAIN ---
def main_app():
    st.sidebar.title("👤 User Info")
    st.sidebar.info(f"Logged in as:\n{st.session_state['user_email']}")
    if st.sidebar.button("Log Out"): st.session_state.clear(); st.rerun()

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
            
            # MINI DASHBOARD (GLOBAL)
            st.divider()
            st.markdown("### 📋 My Task Summary")
            user_email = st.session_state.get('user_email', '').lower()
            df['Manager Email'] = df['Manager Email'].astype(str).str.lower()
            my_projects = df[df['Manager Email'] == user_email]
            
            if not my_projects.empty:
                for _, proj in my_projects.iterrows():
                    p_name = proj['Complex Name']
                    p_tasks = checklist[(checklist['Complex Name'] == p_name) & (checklist['Received'].astype(str).str.lower() != 'true') & (checklist['Delete'] != True)] if not checklist.empty else pd.DataFrame()
                    count = len(p_tasks)
                    if count > 0:
                        with st.expander(f"🔥 {p_name} ({count} Pending)"):
                            for _, task in p_tasks.iterrows(): st.write(f"- {task['Task Name']}")
            else:
                st.info("No projects assigned to you currently.")
                
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
                add_master_item(tn, cat, resp, head, "Immediate") # Default Immediate
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
                errors = []
                if wages and not validate_email(wages): errors.append("Invalid Wages Email")
                if sars and not validate_email(sars): errors.append("Invalid SARS Email")
                
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
                    if res == "SUCCESS":
                        # Auto-Init
                        t_code = "BC" if b_type == "Body Corporate" else "HOA"
                        initialize_checklist(name, t_code)
                        st.cache_data.clear(); st.success("Created!"); st.rerun()
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
                
                checklist = get_data("Checklist")
                arrears = get_data("Arrears")
                staff = get_data("Employees")
                council = get_data("Council")
                
                c_checklist = checklist[checklist['Complex Name'] == b_choice] if not checklist.empty else pd.DataFrame()
                total_tasks = len(c_checklist)
                done_tasks = len(c_checklist[c_checklist['Received'].astype(str).str.lower() == 'true']) if not c_checklist.empty else 0
                prog_val = done_tasks / total_tasks if total_tasks > 0 else 0
                
                # FIX: Force numeric conversion
                c_arrears = pd.DataFrame(); debt_val = 0.0
                if not arrears.empty and 'Complex Name' in arrears.columns:
                    c_arrears = arrears[arrears['Complex Name'] == b_choice]
                    if not c_arrears.empty and 'Outstanding Amount' in c_arrears.columns:
                        debt_val = pd.to_numeric(c_arrears['Outstanding Amount'], errors='coerce').fillna(0).sum()
                
                c_staff = staff[staff['Complex Name'] == b_choice] if not staff.empty and 'Complex Name' in staff.columns else pd.DataFrame()
                staff_count = len(c_staff)
                c_coun = council[council['Complex Name'] == b_choice] if not council.empty and 'Complex Name' in council.columns else pd.DataFrame()
                coun_count = len(c_coun)

                col_d1, col_d2, col_d3, col_d4 = st.columns(4)
                col_d1.metric("Checklist Progress", f"{int(prog_val*100)}%"); col_d1.progress(prog_val)
                col_d2.metric("Total Arrears", f"R {debt_val:,.2f}")
                col_d3.metric("Staff Loaded", staff_count)
                col_d4.metric("Council Accounts", coun_count)
                
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
                        updates = {"Building Code": u_code, "Type": u_type, "No of Units": u_units, "SS Number": u_ss, "Erf Number": u_erf, "CSOS Number": u_csos, "Physical Address": u_addr, "Year End": u_ye, "Mgmt Fees": u_fees, "Expense Code": u_exp, "VAT Number": u_vat, "Tax Number": u_tax, "Take On Date": u_tod, "Auditor": u_aud, "Last Audit": u_last_aud, "Assigned Manager": u_pm, "Manager Email": u_pm_e, "Client Email": u_client_e, "Portfolio Assistant": u_pa, "Portfolio Assistant Email": u_pa_e, "TakeOn Name": u_tom, "Bookkeeper": u_bk, "Bookkeeper Email": u_bk_e}
                        update_building_details_batch(b_choice, updates); st.cache_data.clear(); st.success("Updated."); st.rerun()
                
                st.markdown("### Previous Agent Request")
                c1, c2 = st.columns(2)
                an = c1.text_input("Agent Name", value=get_val("Agent Name"), key=f"an_{b_choice}")
                ae = c2.text_input("Agent Email", value=get_val("Agent Email"), key=f"ae_{b_choice}")

                st.markdown("#### 📋 Handover Strategy: Immediate Items")
                full_chk = get_data("Checklist")
                agent_task_df = pd.DataFrame()
                if not full_chk.empty:
                    # ROBUST FILTER: Case insensitive match for 'Agent' or 'Both'
                    mask_complex = full_chk['Complex Name'] == b_choice
                    mask_resp = full_chk['Responsibility'].astype(str).str.contains('Agent|Both', case=False, na=False)
                    agent_task_df = full_chk[mask_complex & mask_resp]
                
                if agent_task_df.empty:
                    st.warning("⚠️ No checklist items found for this building.")
                    if st.button("📥 Load Standard Checklist from Master", key="init_chk"):
                        type_code = "BC" if get_val("Type") == "Body Corporate" else "HOA"
                        res = initialize_checklist(b_choice, type_code)
                        if res == "SUCCESS": st.success("Loaded! Reloading..."); st.cache_data.clear(); st.rerun()
                        else: st.error(f"Failed: {res}")
                else:
                    # SELECT IMMEDIATE ITEMS MANUALLY OR AUTO
                    # This allows changing "Timing" on the fly for the PDF
                    month_end_cats = ['Financial', 'Employee', 'City Council']
                    default_immediate = agent_task_df[~agent_task_df['Task Heading'].isin(month_end_cats)]['Task Name'].tolist()
                    all_options = agent_task_df['Task Name'].tolist()
                    
                    selected_immediate = st.multiselect("Items Required Immediately:", options=all_options, default=[x for x in default_immediate if x in all_options], key=f"imm_{b_choice}")
                    
                    if st.button("Generate Request PDF & Email"):
                        if ae and not validate_email(ae): st.error("Invalid Agent Email")
                        else:
                            update_project_agent_details(b_choice, an, ae)
                            pdf = generate_appointment_pdf(b_choice, agent_task_df, an, get_val("Take On Date"), selected_immediate)
                            with open(pdf, "rb") as f: st.download_button("Download PDF", f, file_name=pdf)
                            
                            imm_text = "\n".join([f"- {x}" for x in selected_immediate])
                            email_body = f"Dear {an},\n\nWe confirm our appointment for {b_choice}.\n\nPlease provide the following URGENTLY:\n{imm_text}\n\nThe remaining items are required by the 10th.\n\nRegards, Pretor"
                            link = f'<a href="mailto:{ae}?subject=Handover&body={urllib.parse.quote(email_body)}" target="_blank">📧 Draft Email</a>'
                            st.markdown(link, unsafe_allow_html=True)

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
                            # ROBUST FILTER
                            mask_agent = df_pending['Responsibility'].astype(str).str.contains('Agent|Both', case=False, na=False)
                            ag_pend = df_pending[mask_agent].copy()
                            if not ag_pend.empty:
                                ag_pend['Sort'] = ag_pend['Task Heading'].apply(lambda x: sections.index(x) if x in sections else 99)
                                ag_pend = ag_pend.sort_values(by=['Sort', 'Task Name'])
                                
                                st.markdown("##### 📎 Attach Document (Optional)")
                                item_names = ag_pend['Task Name'].tolist()
                                selected_item = st.selectbox("Select checklist item to attach file", ["None"] + item_names, key=f"sel_up_{b_choice}")
                                if selected_item != "None":
                                    uploaded_file = st.file_uploader(f"Upload Document for: {selected_item}", key=f"ul_chk_{b_choice}")
                                    if uploaded_file:
                                        if st.button("Upload File", key=f"btn_up_{b_choice}"):
                                            row_id = ag_pend[ag_pend['Task Name'] == selected_item].iloc[0]['id']
                                            path = f"{b_choice}/Checklist/{selected_item}_{uploaded_file.name}"
                                            doc_url = upload_file_to_supabase(uploaded_file, path)
                                            if doc_url:
                                                update_document_url("Checklist", row_id, doc_url)
                                                st.success(f"Uploaded! Please tick '{selected_item}' below and Save.")

                                edited_ag = st.data_editor(ag_pend[['id', 'Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes', 'Delete']], hide_index=True, height=400, key=f"ag_ed_{b_choice}", column_config={"id": None, "Task Heading": st.column_config.TextColumn(disabled=True), "Task Name": st.column_config.TextColumn(disabled=True)})
                                if st.button("Save Agent Items", key=f"sv_ag_{b_choice}"):
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
                             # AGENT COMPLETE
                             mask_agent_comp = c_items['Responsibility'].astype(str).str.contains('Agent|Both', case=False, na=False)
                             ag_comp = c_items[mask_agent_comp & (c_items['Received'] == True)]
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
                                     with open(pdf_f, "rb") as f: st.download_button("⬇️ Download Copy", f, file_name=pdf_f, mime="application/pdf", key=f"dl_rep_{b_choice}")
                                     if st.button("Unlock (Regenerate Report)", key=f"unlock_rep_{b_choice}"): update_email_status(b_choice, "Client Report Generated Date", ""); st.cache_data.clear(); st.rerun()
                                 else:
                                     if st.button("📄 Generate & Lock Report", key=f"gen_pdf_comp_{b_choice}"):
                                         emp_df, arr_df, cou_df = get_data("Employees"), get_data("Arrears"), get_data("Council")
                                         create_comprehensive_pdf(b_choice, p_row, c_items, emp_df, arr_df, cou_df)
                                         update_email_status(b_choice, "Client Report Generated Date"); st.cache_data.clear(); st.rerun()
                                 st.markdown("**Step 2: Email Client**")
                                 if comp_date and comp_date != "None":
                                     st.success(f"✅ Sent: {comp_date}")
                                     if st.button("Unlock Email", key=f"unlock_comp_{b_choice}"): update_email_status(b_choice, "Client Completion Email Sent Date", ""); st.cache_data.clear(); st.rerun()
                                 else:
                                     c_mail = get_val("Client Email")
                                     if c_mail and c_mail != "None":
                                         bod = "Dear Client,\n\nTake-on complete.\n\nRegards, Pretor"
                                         sub = urllib.parse.quote(f"Completed: {b_choice}")
                                         lnk = f'<a href="mailto:{c_mail}?subject={sub}&body={urllib.parse.quote(bod)}" target="_blank" style="background-color:#09ab3b;color:white;padding:10px;border-radius:5px;text-decoration:none;">🚀 Draft Email</a>'
                                         st.markdown(lnk, unsafe_allow_html=True)
                                         st.write("")
                                         if st.button("Mark as Sent", key=f"mark_comp_{b_choice}"): update_email_status(b_choice, "Client Completion Email Sent Date"); st.cache_data.clear(); st.rerun()
                                     else: st.warning("No Client Email.")
                             else: st.info("No agent items.")

                    with t2:
                        if not df_pending.empty:
                            # ROBUST FILTER INTERNAL
                            mask_internal = df_pending['Responsibility'].astype(str).str.contains('Pretor|Both', case=False, na=False)
                            int_pend = df_pending[mask_internal].copy()
                            if not int_pend.empty:
                                int_pend['Sort'] = int_pend['Task Heading'].apply(lambda x: sections.index(x) if x in sections else 99)
                                int_pend = int_pend.sort_values(by=['Sort', 'Task Name'])
                                ed_int = st.data_editor(int_pend[['id', 'Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes', 'Delete']], hide_index=True, height=400, key=f"int_ed_{b_choice}", column_config={"id": None, "Task Heading": st.column_config.TextColumn(disabled=True), "Task Name": st.column_config.TextColumn(disabled=True)})
                                if st.button("Save Internal Items", key=f"sv_int_{b_choice}"):
                                    ed_int['Date Received'] = ed_int.apply(fill_date, axis=1)
                                    save_checklist_batch(b_choice, ed_int, st.session_state.get('user_email', 'Unknown')); st.cache_data.clear(); st.success("Saved!"); st.rerun()
                            else: st.info("No pending internal.")
                        else: st.info("No pending.")
                st.divider()
                st.markdown("#### ✅ History")
                if not df_completed.empty:
                    mask_ah = df_completed['Responsibility'].astype(str).str.contains('Agent|Both', case=False, na=False)
                    mask_ih = df_completed['Responsibility'].astype(str).str.contains('Pretor|Both', case=False, na=False)
                    ah = df_completed[mask_ah]
                    ih = df_completed[mask_ih]
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
                c1, c2, c3 = st.columns(3); c1.text_input("UIF", uif_val, disabled=True, key=f"l_u_{b_choice}"); c2.text_input("PAYE", paye_val, disabled=True, key=f"l_p_{b_choice}"); c3.text_input("COIDA", coida_val, disabled=True, key=f"l_c_{b_choice}")
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
                    ed_s = st.data_editor(curr_s[[c for c in cols if c in curr_s.columns]], hide_index=True, key=f"stf_ed_{b_choice}", column_config={"id": None, "Salary": st.column_config.NumberColumn(format="R %.2f")})
                    if st.button("Save Staff", key=f"sv_s_{b_choice}"): update_employee_batch(ed_s); st.cache_data.clear(); st.success("Updated!"); st.rerun()
                else: st.info("No staff.")
                
                st.markdown("##### 📎 Upload Contract/ID")
                s_list = curr_s['Name'].tolist() if not curr_s.empty else []
                sel_s = st.selectbox("Select Employee", ["None"] + s_list, key=f"sel_s_{b_choice}")
                if sel_s != "None":
                    up_s = st.file_uploader("Upload Document", key=f"up_stf_{b_choice}")
                    if up_s and st.button("Upload to Staff", key=f"btn_up_stf_{b_choice}"):
                        row_id = curr_s[curr_s['Name'] == sel_s].iloc[0]['id']
                        path = f"{b_choice}/Staff/{sel_s}_{up_s.name}"
                        doc_url = upload_file_to_supabase(up_s, path)
                        if doc_url:
                            update_document_url("Employees", row_id, doc_url)
                            st.success("Uploaded!")
            
            st.divider(); st.markdown("#### ➕ Add New Employee")
            with st.form("add_s", clear_on_submit=True):
                c1,c2 = st.columns(2); n=c1.text_input("Name"); s=c2.text_input("Surname")
                e_id = st.text_input("ID Number", key="new_eid")
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
                        ed_a = st.data_editor(curr_a[['id', 'Unit Number', 'Outstanding Amount']], hide_index=True, key=f"arr_ed_{b_choice}", column_config={"id": None, "Outstanding Amount": st.column_config.NumberColumn(format="R %.2f")})
                        if st.button("Save Arrears", key=f"sv_arr_{b_choice}"): update_arrears_batch(ed_a); st.cache_data.clear(); st.success("Updated"); st.rerun()
                        
                        st.markdown("##### 📎 Upload Legal Handover")
                        u_list = curr_a['Unit Number'].astype(str).tolist()
                        sel_u = st.selectbox("Select Unit", ["None"] + u_list, key=f"sel_arr_{b_choice}")
                        if sel_u != "None":
                            up_a = st.file_uploader("Upload File", key=f"up_arr_{b_choice}")
                            if up_a and st.button("Upload to Arrears", key=f"btn_up_arr_{b_choice}"):
                                row_id = curr_a[curr_a['Unit Number'].astype(str) == sel_u].iloc[0]['id']
                                path = f"{b_choice}/Arrears/{sel_u}_{up_a.name}"
                                doc_url = upload_file_to_supabase(up_a, path)
                                if doc_url: update_document_url("Arrears", row_id, doc_url); st.success("Uploaded!")

                else: st.info("No arrears.")
            with st.form("add_a", clear_on_submit=True):
                u=st.text_input("Unit"); a=st.number_input("Amount"); m=st.text_input("Attorney Email"); p=st.text_input("Attorney Phone")
                if st.form_submit_button("Add"):
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
                    ed_c = st.data_editor(curr_c[['id', 'Account Number', 'Service']], hide_index=True, key=f"cou_ed_{b_choice}", column_config={"id": None, "Balance": st.column_config.NumberColumn(format="R %.2f")})
                    if st.button("Save Council", key=f"sv_cou_{b_choice}"): update_council_batch(ed_c); st.cache_data.clear(); st.success("Updated"); st.rerun()
                    
                    st.markdown("##### 📎 Upload Account Statement")
                    ac_list = curr_c['Account Number'].astype(str).tolist()
                    sel_ac = st.selectbox("Select Account", ["None"] + ac_list, key=f"sel_cou_{b_choice}")
                    if sel_ac != "None":
                        up_c = st.file_uploader("Upload File", key=f"up_cou_{b_choice}")
                        if up_c and st.button("Upload to Council", key=f"btn_up_cou_{b_choice}"):
                            row_id = curr_c[curr_c['Account Number'].astype(str) == sel_ac].iloc[0]['id']
                            path = f"{b_choice}/Council/{sel_ac}_{up_c.name}"
                            doc_url = upload_file_to_supabase(up_c, path)
                            if doc_url: update_document_url("Council", row_id, doc_url); st.success("Uploaded!")
                else: st.info("No accounts.")
            with st.form("add_c", clear_on_submit=True):
                a=st.text_input("Acc"); s=st.text_input("Svc")
                if st.form_submit_button("Add"): add_council_account(b_choice, a, s, 0.0); st.cache_data.clear(); st.success("Added"); st.rerun()

        elif sub_nav == "Department Handovers":
            st.markdown("### Department Handovers")
            settings = get_data("Settings"); s_dict = dict(zip(settings["Department"], settings["Email"])) if not settings.empty else {}

            council_df = get_data("Council")
            if council_df.empty: council_df = get_data("council")

            st.markdown("#### SARS")
            sars_sent = get_val("SARS Sent Date")
            if sars_sent and sars_sent != "None":
                st.success(f"✅ Sent: {sars_sent}")
                if st.button("Reset SARS", key=f"rst_sars_{b_choice}"): update_email_status(b_choice, "SARS Sent Date", ""); st.cache_data.clear(); st.rerun()
            else:
                if st.button("Mark SARS Sent", key=f"btn_sars_{b_choice}"): update_email_status(b_choice, "SARS Sent Date"); st.cache_data.clear(); st.rerun()
            
            st.divider(); st.markdown("#### Council")
            c_sent = get_val("Council Email Sent Date")
            
            c_docs = " (Files Attached)" if not council_df.empty else ""
            c_body = f"Dear Council Team,\n\nPlease find attached account details{c_docs}.\n\nPath: Y:\\HenryJ\\NEW BUSINESS & DEVELOPMENTS\\{b_choice}\\council\n\nPlease load onto Pretor Portal.\n\nRegards."
            
            if c_sent and c_sent != "None":
                st.success(f"✅ Sent: {c_sent}")
                if st.button("Reset Council", key=f"rst_cou_{b_choice}"): update_email_status(b_choice, "Council Email Sent Date", ""); st.cache_data.clear(); st.rerun()
            else:
                c1, c2 = st.columns([1,1])
                with c1:
                    muni_em = s_dict.get("Municipal", "")
                    if muni_em:
                        lnk = f'<a href="mailto:{muni_em}?subject=Handover: {b_choice}&body={urllib.parse.quote(c_body)}" target="_blank" style="background-color:#FF4B4B;color:white;padding:8px;border-radius:5px;text-decoration:none;">📧 Draft Email</a>'
                        st.markdown(lnk, unsafe_allow_html=True)
                with c2:
                    if st.button("Mark Council Sent", key=f"btn_cou_{b_choice}"): update_email_status(b_choice, "Council Email Sent Date"); st.cache_data.clear(); st.rerun()

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
