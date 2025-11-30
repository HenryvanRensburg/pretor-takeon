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
    pdf.set_font('Arial', 'B', 10); pdf.cell(0, 6, "General", 0, 1)
    for k in ["Building Code", "Type", "No of Units", "SS Number", "Erf Number", "CSOS Number"]:
        v = p_row.get(k, ''); pdf.entry_row(k+":", v) if v and v != 'None' else None
    pdf.ln(2); pdf.set_font('Arial', 'B', 10); pdf.cell(0, 6, "Financial", 0, 1)
    for k in ["Year End", "Mgmt Fees", "VAT Number", "Tax Number", "Auditor"]:
        v = p_row.get(k, ''); pdf.entry_row(k+":", v) if v and v != 'None' else None
    pdf.ln(2); pdf.set_font('Arial', 'B', 10); pdf.cell(0, 6, "Team", 0, 1)
    for k, v_col in {"Manager": "Assigned Manager", "PM Email": "Manager Email", "Client": "Client Email"}.items():
        v = p_row.get(v_col, ''); pdf.entry_row(k+":", v) if v and v != 'None' else None
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
    st.sidebar.info(f"User: {st.session_state['user_email']}")
    if st.sidebar.button("Log Out"): st.session_state.clear(); st.rerun()
    if os.path.exists("pretor_logo.png"): st.sidebar.image("pretor_logo.png", use_container_width=True)
    st.title("🏢 Pretor Take-On Manager")
    
    menu = ["Dashboard", "Master Schedule", "New Building", "Manage Buildings", "Global Settings"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Dashboard":
        st.subheader("Active Projects")
        df = get_data("Projects"); checklist = get_data("Checklist")
        if not df.empty:
            u_email = st.session_state.get('user_email', '').lower()
            df['Manager Email'] = df['Manager Email'].astype(str).str.lower()
            my_projs = df[df['Manager Email'] == u_email]
            
            col1, col2 = st.columns(2)
            col1.metric("Total Projects", len(df)); col2.metric("My Projects", len(my_projs))
            st.divider()
            st.markdown("### 📋 My Pending Tasks")
            if not my_projs.empty:
                for _, p in my_projs.iterrows():
                    nm = p['Complex Name']
                    tasks = checklist[(checklist['Complex Name'] == nm) & (checklist['Received'].astype(str).str.lower() != 'true') & (checklist['Delete'] != True)] if not checklist.empty else pd.DataFrame()
                    if len(tasks) > 0:
                        with st.expander(f"🔥 {nm} ({len(tasks)} Pending)"):
                            for _, t in tasks.iterrows(): st.write(f"- {t['Task Name']}")
            else: st.info("No projects assigned to you.")
        else: st.info("No projects.")

    elif choice == "Master Schedule":
        st.subheader("Master Checklist"); df = get_data("Master"); st.dataframe(df)
        with st.form("add_master"):
            c1,c2,c3,c4 = st.columns(4)
            n = c1.text_input("Task"); cat = c2.selectbox("Cat", ["Both","BC","HOA"]); resp = c3.selectbox("Resp", ["Previous Agent","Pretor Group","Both"]); head = c4.selectbox("Head", ["Take-On","Financial","Legal","Statutory Compliance","Insurance","City Council","Building Compliance","Employee","General"])
            if st.form_submit_button("Add"): add_master_item(n, cat, resp, head); st.cache_data.clear(); st.success("Added"); st.rerun()

    elif choice == "Global Settings":
        st.subheader("Settings"); st.info("Manage department emails here.")
        s_dict = dict(zip(get_data("Settings")["Department"], get_data("Settings")["Email"])) if not get_data("Settings").empty else {}
        with st.form("set"):
            w = st.text_input("Wages", s_dict.get("Wages","")); s = st.text_input("SARS", s_dict.get("SARS","")); m = st.text_input("Municipal", s_dict.get("Municipal",""))
            if st.form_submit_button("Save"): save_global_settings({"Wages": w, "SARS": s, "Municipal": m}); st.cache_data.clear(); st.success("Saved"); st.rerun()

    elif choice == "New Building":
        st.subheader("New Building")
        with st.form("new"):
            n = st.text_input("Name"); t = st.selectbox("Type", ["Body Corporate", "HOA"])
            if st.form_submit_button("Create"):
                if n: 
                    res = create_new_building({"Complex Name": n, "Type": t, "Date Doc Requested": str(datetime.today())})
                    st.cache_data.clear()
                    if res == "SUCCESS": st.success("Created!"); st.rerun()
                    else: st.error("Exists.")

    elif choice == "Manage Buildings":
        projs = get_data("Projects")
        if projs.empty: st.warning("No projects."); st.stop()
        
        b_choice = st.selectbox("Select Complex", projs['Complex Name'])
        p_row = projs[projs['Complex Name'] == b_choice].iloc[0]
        def get_val(c): return str(p_row.get(c, ''))

        st.divider()
        sub_nav = option_menu(None, ["Overview", "Progress Tracker", "Staff Details", "Arrears Details", "Council Details", "Department Handovers", "Client Updates"], 
            icons=["house", "list-task", "people", "cash-coin", "building", "envelope", "person-check"], 
            orientation="horizontal", default_index=0)
        st.divider()

        if sub_nav == "Overview":
            st.subheader(f"Project Overview: {b_choice}")
            with st.form("ov_form"):
                c1, c2 = st.columns(2)
                mgr = c1.text_input("Manager", get_val("Assigned Manager")); mail = c2.text_input("Email", get_val("Manager Email"))
                # (Add other fields here as needed)
                if st.form_submit_button("Save"):
                    update_building_details_batch(b_choice, {"Assigned Manager": mgr, "Manager Email": mail}); st.cache_data.clear(); st.success("Saved"); st.rerun()

            st.markdown("### Previous Agent Request")
            c1, c2 = st.columns(2)
            an = c1.text_input("Agent Name", value=get_val("Agent Name"), key=f"an_{b_choice}")
            ae = c2.text_input("Agent Email", value=get_val("Agent Email"), key=f"ae_{b_choice}")

            # --- HANDOVER STRATEGY ---
            st.markdown("#### 📋 Handover Strategy: Immediate Items")
            full_chk = get_data("Checklist")
            
            # --- FIXED LOGIC FOR EMPTY CHECKLIST ---
            # 1. Attempt to find checklist items for this specific building
            if not full_chk.empty:
                agent_task_df = full_chk[
                    (full_chk['Complex Name'] == b_choice) & 
                    (full_chk['Responsibility'].isin(['Previous Agent', 'Both']))
                ]
            else:
                agent_task_df = pd.DataFrame()

            # 2. If found, show selection. If NOT found, show LOAD button.
            if not agent_task_df.empty:
                month_end_cats = ['Financial', 'Employee', 'City Council']
                default_immediate = agent_task_df[~agent_task_df['Task Heading'].isin(month_end_cats)]['Task Name'].tolist()
                all_options = agent_task_df['Task Name'].tolist()
                
                selected_immediate = st.multiselect(
                    "Items Required Immediately:",
                    options=all_options,
                    default=[x for x in default_immediate if x in all_options],
                    key=f"imm_{b_choice}"
                )
                
                if st.button("Generate Split Request PDF"):
                    update_project_agent_details(b_choice, an, ae)
                    pdf = generate_appointment_pdf(b_choice, agent_task_df, an, get_val("Take On Date"), selected_immediate)
                    with open(pdf, "rb") as f: st.download_button("Download Split PDF", f, file_name=pdf)
                    
                    imm_text = "\n".join([f"- {x}" for x in selected_immediate])
                    email_body = f"Dear {an},\n\nWe confirm our appointment for {b_choice}.\n\nPlease provide these immediately:\n{imm_text}\n\nRemainder by 10th.\n\nRegards, Pretor"
                    link = f'<a href="mailto:{ae}?subject=Handover&body={urllib.parse.quote(email_body)}" target="_blank">📧 Draft Email</a>'
                    st.markdown(link, unsafe_allow_html=True)
            else:
                # 3. SHOW LOAD BUTTON IF EMPTY
                st.warning("⚠️ No checklist items found for this building.")
                st.info("Click below to load the standard checklist from the Master Schedule.")
                if st.button("📥 Load Standard Checklist", key="init_chk"):
                    res = initialize_checklist(b_choice)
                    if res == "SUCCESS":
                        st.success("Checklist Loaded! Reloading...")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"Failed to load: {res}. (Check if Master Schedule has items)")

        elif sub_nav == "Progress Tracker":
            # ... [This section remains identical to previous full versions] ...
            st.info("Progress Tracker (See previous full code)") 
            # NOTE: For production, ensure the full code from the previous step is pasted here.
            # I am only truncating to fit the response limit, but the critical fix was in the Overview tab above.

        # ... [Rest of tabs: Staff, Arrears, Council, Handovers, Client Updates] ...
        # Ensure you keep the code I provided in the "Full Updated app.py" response 
        # two steps ago, as that had the complete logic for these tabs.

if __name__ == "__main__":
    if 'user' not in st.session_state: login_screen()
    else: main_app()
