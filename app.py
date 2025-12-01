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

# --- VALIDATION ---
def validate_email(email): return True if not email else re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None
def validate_phone(phone): return True if not phone else re.match(r'^0\d{9}$', re.sub(r'[\s\-\(\)]', '', str(phone))) is not None
def validate_sa_id(id_num): return True if not id_num else re.match(r'^\d{13}$', str(id_num).strip()) is not None

# --- PDF CLASSES ---
class BasePDF(FPDF):
    def clean_text(self, text):
        if text is None: return ""
        return str(text).replace('“', '"').replace('”', '"').replace('’', "'").replace('–', '-').encode('latin-1', 'replace').decode('latin-1')
    def header(self):
        if os.path.exists("pretor_logo.png"): self.image("pretor_logo.png", 10, 8, 33)
        self.set_font('Arial', 'B', 14); self.cell(80); self.ln(20)
    def footer(self):
        self.set_y(-15); self.set_font('Arial', 'I', 8); self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

class AgentRequestPDF(BasePDF):
    def section_header(self, title):
        self.set_font('Arial', 'B', 11); self.set_fill_color(230, 230, 230); self.cell(0, 8, self.clean_text(title), 0, 1, 'L', 1); self.ln(2)
    def add_item(self, text):
        self.set_font('Arial', '', 10); self.cell(10); self.multi_cell(0, 5, "- " + self.clean_text(text)); self.ln(1)

def generate_appointment_pdf(complex_name, checklist_df, agent_name, take_on_date):
    pdf = AgentRequestPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 14); pdf.cell(0, 10, 'Handover Request: Managing Agent Appointment', 0, 1, 'C'); pdf.ln(5)
    pdf.set_font('Arial', '', 10)
    intro = f"Dear {agent_name},\n\nWe confirm that Pretor Group has been appointed as the managing agents for {complex_name}, effective {take_on_date}.\n\nTo ensure a smooth transition, we require the following documentation. We have separated this request into items required immediately and items required at month-end closing."
    pdf.multi_cell(0, 5, pdf.clean_text(intro)); pdf.ln(5)
    
    # SPLIT BY 'TIMING'
    df_immediate = checklist_df[checklist_df['Timing'] == 'Immediate']
    df_month_end = checklist_df[checklist_df['Timing'] == 'Month-End']
    
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
    pdf.section_title("2. Pending Items"); pdf.ln(2)
    pending = checklist_df[(checklist_df['Received'].astype(str).str.lower() != 'true') & (checklist_df['Delete'] != True)]
    if not pending.empty:
        for _, r in pending.iterrows(): pdf.cell(5); pdf.multi_cell(0, 5, f"- {pdf.clean_text(r['Task Name'])} ({r.get('Timing','Unknown')})")
    else: pdf.cell(0, 6, "No pending items.", 0, 1)
    temp_dir = tempfile.gettempdir(); filename = os.path.join(temp_dir, f"Report_{complex_name}.pdf"); pdf.output(filename); return filename

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
        st.subheader("Active Projects Overview")
        df = get_data("Projects"); checklist = get_data("Checklist")
        if not df.empty:
            u_email = st.session_state.get('user_email', '').lower()
            df['Manager Email'] = df['Manager Email'].astype(str).str.lower()
            my_projs = df[df['Manager Email'] == u_email]
            col1, col2 = st.columns(2)
            col1.metric("Total Projects", len(df)); col2.metric("My Projects", len(my_projs))
            st.divider(); st.markdown("### 📋 My Pending Tasks")
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
            c1,c2,c3,c4,c5 = st.columns(5)
            n = c1.text_input("Task"); cat = c2.selectbox("Cat", ["Both","BC","HOA"]); resp = c3.selectbox("Resp", ["Previous Agent","Pretor Group","Both"]); head = c4.selectbox("Head", ["Take-On","Financial","Legal","Statutory Compliance","Insurance","City Council","Building Compliance","Employee","General"])
            time = c5.selectbox("Timing", ["Immediate", "Month-End"]) 
            if st.form_submit_button("Add"): add_master_item(n, cat, resp, head, time); st.cache_data.clear(); st.success("Added"); st.rerun()

    elif choice == "Global Settings":
        st.subheader("Settings"); s_dict = dict(zip(get_data("Settings")["Department"], get_data("Settings")["Email"])) if not get_data("Settings").empty else {}
        with st.form("set"):
            w = st.text_input("Wages", s_dict.get("Wages","")); s = st.text_input("SARS", s_dict.get("SARS","")); m = st.text_input("Municipal", s_dict.get("Municipal",""))
            if st.form_submit_button("Save"): save_global_settings({"Wages": w, "SARS": s, "Municipal": m}); st.cache_data.clear(); st.success("Saved"); st.rerun()

    elif choice == "New Building":
        st.subheader("Onboard New Complex")
        with st.form("new"):
            n = st.text_input("Name"); t = st.selectbox("Type", ["Body Corporate", "HOA"])
            if st.form_submit_button("Create"):
                if n: 
                    res = create_new_building({"Complex Name": n, "Type": t, "Date Doc Requested": str(datetime.today())})
                    if res == "SUCCESS":
                        t_code = "BC" if t == "Body Corporate" else "HOA"
                        init_res = initialize_checklist(n, t_code)
                        st.cache_data.clear(); st.success(f"Project '{n}' created & checklist loaded!"); st.rerun()
                    else: st.error("Exists.")

    elif choice == "Manage Buildings":
        projs = get_data("Projects")
        if projs.empty: st.warning("No projects."); st.stop()
        b_choice = st.selectbox("Select Complex", projs['Complex Name'])
        p_row = projs[projs['Complex Name'] == b_choice].iloc[0]
        def get_val(c): return str(p_row.get(c, ''))

        st.divider()
        sub_nav = option_menu(None, ["Overview", "Progress Tracker", "Staff Details", "Arrears Details", "Council Details", "Department Handovers", "Client Updates"], 
            icons=["house", "list-task", "people", "cash-coin", "building", "envelope", "person-check"], orientation="horizontal", default_index=0)
        st.divider()

        if sub_nav == "Overview":
            st.subheader(f"Project Overview: {b_choice}")
            with st.form("ov_form"):
                c1, c2 = st.columns(2); mgr = c1.text_input("Manager", get_val("Assigned Manager")); mail = c2.text_input("Email", get_val("Manager Email"))
                if st.form_submit_button("Save"): update_building_details_batch(b_choice, {"Assigned Manager": mgr, "Manager Email": mail}); st.cache_data.clear(); st.success("Saved"); st.rerun()
            st.markdown("### Previous Agent Request")
            c1, c2 = st.columns(2); an = c1.text_input("Agent Name", value=get_val("Agent Name"), key=f"an_{b_choice}"); ae = c2.text_input("Agent Email", value=get_val("Agent Email"), key=f"ae_{b_choice}")
            
            full_chk = get_data("Checklist")
            agent_task_df = full_chk[(full_chk['Complex Name'] == b_choice) & (full_chk['Responsibility'].astype(str).str.contains('Agent|Both', case=False, na=False))] if not full_chk.empty else pd.DataFrame()
            
            if agent_task_df.empty:
                st.warning("⚠️ Checklist empty.")
                if st.button("🛠️ Fix/Reset Checklist Data", key="fix_data"):
                    type_code = "BC" if get_val("Type") == "Body Corporate" else "HOA"
                    res = initialize_checklist(b_choice, type_code)
                    if res == "SUCCESS": st.success("Data Repaired!"); st.cache_data.clear(); st.rerun()
                    else: st.error(f"Repair Failed: {res}")
            else:
                imm_df = agent_task_df[agent_task_df['Timing'] == 'Immediate']
                if st.button("Generate Request PDF & Email"):
                    if ae and not validate_email(ae): st.error("Invalid Email")
                    else:
                        update_project_agent_details(b_choice, an, ae)
                        pdf = generate_appointment_pdf(b_choice, agent_task_df, an, get_val("Take On Date"))
                        with open(pdf, "rb") as f: st.download_button("Download PDF", f, file_name=pdf)
                        imm_text = "\n".join([f"- {x}" for x in imm_df['Task Name'].tolist()])
                        email_body = f"Dear {an},\n\nWe confirm appointment.\n\nURGENT:\n{imm_text}\n\nRest by 10th.\n\nRegards."
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
                
                # Check if we need a reset here too
                if c_items.empty:
                    st.warning("Checklist data missing.")
                    if st.button("🛠️ Reset Checklist", key="reset_prog"):
                        type_code = "BC" if get_val("Type") == "Body Corporate" else "HOA"
                        initialize_checklist(b_choice, type_code); st.cache_data.clear(); st.rerun()

                t1, t2 = st.tabs(["① Previous Agent", "② Internal"])
                sections = ["Take-On", "Financial", "Legal", "Statutory Compliance", "Insurance", "City Council", "Building Compliance", "Employee", "General"]
                
                with t1:
                    if not df_pending.empty:
                        ag_pend = df_pending[df_pending['Responsibility'].astype(str).str.contains('Agent|Both', case=False, na=False)].copy()
                        if not ag_pend.empty:
                            ag_pend['Sort'] = ag_pend['Task Heading'].apply(lambda x: sections.index(x) if x in sections else 99)
                            ag_pend = ag_pend.sort_values(by=['Sort', 'Task Name'])
                            
                            # SUB TABS FOR TIMING
                            imm_tab, mth_tab = st.tabs(["🚨 Immediate", "📅 Month-End"])
                            
                            with imm_tab:
                                imm_items = ag_pend[ag_pend['Timing'] == 'Immediate']
                                if not imm_items.empty:
                                    edited_imm = st.data_editor(imm_items[['id', 'Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes', 'Delete']], hide_index=True, key=f"imm_ed_{b_choice}", column_config={"id": None, "Task Heading": st.column_config.TextColumn(disabled=True), "Task Name": st.column_config.TextColumn(disabled=True)})
                                    if st.button("Save Immediate", key=f"sv_imm_{b_choice}"):
                                        edited_imm['Date Received'] = edited_imm.apply(fill_date, axis=1)
                                        save_checklist_batch(b_choice, edited_imm, st.session_state.get('user_email')); st.cache_data.clear(); st.success("Saved!"); st.rerun()
                                else: st.success("No immediate items pending.")

                            with mth_tab:
                                mth_items = ag_pend[ag_pend['Timing'] != 'Immediate']
                                if not mth_items.empty:
                                    edited_mth = st.data_editor(mth_items[['id', 'Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes', 'Delete']], hide_index=True, key=f"mth_ed_{b_choice}", column_config={"id": None, "Task Heading": st.column_config.TextColumn(disabled=True), "Task Name": st.column_config.TextColumn(disabled=True)})
                                    if st.button("Save Month-End", key=f"sv_mth_{b_choice}"):
                                        edited_mth['Date Received'] = edited_mth.apply(fill_date, axis=1)
                                        save_checklist_batch(b_choice, edited_mth, st.session_state.get('user_email')); st.cache_data.clear(); st.success("Saved!"); st.rerun()
                                else: st.success("No month-end items pending.")
                        else: st.info("No agent items.")
                    else:
                         # ... (Completion Logic same as before) ...
                         st.success("Agent Handover Complete!")
                         # ... (Add PDF/Email logic here if needed, similar to previous code) ...

                with t2:
                    if not df_pending.empty:
                        int_pend = df_pending[df_pending['Responsibility'].astype(str).str.contains('Pretor|Both', case=False, na=False)].copy()
                        if not int_pend.empty:
                            int_pend['Sort'] = int_pend['Task Heading'].apply(lambda x: sections.index(x) if x in sections else 99)
                            int_pend = int_pend.sort_values(by=['Sort', 'Task Name'])
                            ed_int = st.data_editor(int_pend[['id', 'Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes', 'Delete']], hide_index=True, key=f"int_ed_{b_choice}", column_config={"id": None, "Task Heading": st.column_config.TextColumn(disabled=True), "Task Name": st.column_config.TextColumn(disabled=True)})
                            if st.button("Save Internal", key=f"sv_int_{b_choice}"):
                                ed_int['Date Received'] = ed_int.apply(fill_date, axis=1)
                                save_checklist_batch(b_choice, ed_int, st.session_state.get('user_email')); st.cache_data.clear(); st.success("Saved!"); st.rerun()
                        else: st.info("No internal pending.")

            else: st.info("No checklist.")

        # ... (Rest of tabs Staff/Arrears/Council/Dept/Client same as previous) ...
        # Please maintain the code for these tabs from the previous full response.

if __name__ == "__main__":
    if 'user' not in st.session_state: login_screen()
    else: main_app()
