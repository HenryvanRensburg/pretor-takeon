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
    intro = f"Dear {agent_name},\n\nWe confirm that Pretor Group has been appointed as the managing agents for {complex_name}, effective {take_on_date}.\n\nTo ensure a smooth transition, we require the following documentation."
    pdf.multi_cell(0, 5, pdf.clean_text(intro)); pdf.ln(5)
    
    # AUTO SPLIT FROM DB
    df_immediate = checklist_df[checklist_df['Timing'] == 'Immediate']
    df_month_end = checklist_df[checklist_df['Timing'] == 'Month-End']
    
    pdf.section_header("SECTION A: REQUIRED IMMEDIATELY")
    pdf.set_font('Arial', 'I', 9); pdf.multi_cell(0, 5, "Please provide the following documents at your earliest convenience."); pdf.ln(2)
    if not df_immediate.empty:
        for heading, group in df_immediate.groupby('Task Heading'):
            pdf.set_font('Arial', 'B', 9); pdf.cell(0, 6, pdf.clean_text(heading), 0, 1)
            for _, row in group.iterrows(): pdf.add_item(row['Task Name'])
            pdf.ln(2)
    else: pdf.add_item("No immediate items.")
    pdf.ln(5)
    pdf.section_header("SECTION B: REQUIRED BY MONTH END")
    pdf.set_font('Arial', 'I', 9); pdf.multi_cell(0, 5, "Please provide the following records once the month has been closed (by the 10th)."); pdf.ln(2)
    if not df_month_end.empty:
        for heading, group in df_month_end.groupby('Task Heading'):
            pdf.set_font('Arial', 'B', 9); pdf.cell(0, 6, pdf.clean_text(heading), 0, 1)
            for _, row in group.iterrows(): pdf.add_item(row['Task Name'])
            pdf.ln(2)
    else: pdf.add_item("No month-end items.")
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
    st.sidebar.title("👤 User Info")
    st.sidebar.info(f"Logged in as:\n{st.session_state['user_email']}")
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
            col1, col2 = st.columns(2); col1.metric("Total Projects", len(df)); col2.metric("My Projects", len(my_projs))
            st.divider(); st.markdown("### 📋 My Pending Tasks")
            if not my_projs.empty:
                for _, p in my_projs.iterrows():
                    nm = p['Complex Name']
                    tasks = checklist[(checklist['Complex Name'] == nm) & (checklist['Received'].astype(str).str.lower() != 'true') & (checklist['Delete'] != True)] if not checklist.empty else pd.DataFrame()
                    if len(tasks) > 0:
                        with st.expander(f"🔥 {nm} ({len(tasks)} Pending)"):
                            for _, t in tasks.iterrows(): st.write(f"- {t['Task Name']}")
            else: st.info("No projects assigned.")
        else: st.info("No projects.")

    elif choice == "Master Schedule":
        st.subheader("Master Checklist"); df = get_data("Master"); st.dataframe(df)
        with st.form("add_master"):
            c1,c2,c3,c4,c5 = st.columns(5)
            n = c1.text_input("Task"); cat = c2.selectbox("Cat", ["Both","BC","HOA"]); resp = c3.selectbox("Resp", ["Previous Agent","Pretor Group","Both"]); head = c4.selectbox("Head", ["Take-On","Financial","Legal","Statutory Compliance","Insurance","City Council","Building Compliance","Employee","General"]); time = c5.selectbox("Timing", ["Immediate", "Month-End"]) 
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
                        # AUTO-INIT
                        t_code = "BC" if t == "Body Corporate" else "HOA"
                        initialize_checklist(n, t_code)
                        st.cache_data.clear(); st.success(f"Project '{n}' created & checklist loaded!"); st.rerun()
                    else: st.error("Exists.")

    elif choice == "Manage Buildings":
        projs = get_data("Projects")
        if projs.empty: st.warning("No projects."); st.stop()
        b_choice = st.selectbox("Select Complex", projs['Complex Name'])
        p_row = projs[projs['Complex Name'] == b_choice].iloc[0]
        def get_val(c): return str(p_row.get(c, ''))
        
        # --- SELF HEALING CHECK ---
        checklist_data = get_data("Checklist")
        b_checklist = checklist_data[checklist_data['Complex Name'] == b_choice] if not checklist_data.empty else pd.DataFrame()
        
        # IF CHECKLIST IS EMPTY, AUTO-REPAIR
        if b_checklist.empty:
            with st.status("⚠️ Checklist Missing! Auto-repairing...", expanded=True) as status:
                type_full = get_val("Type") # e.g. "Body Corporate"
                st.write(f"Detecting type: {type_full}...")
                res = initialize_checklist(b_choice, type_full)
                if res == "SUCCESS":
                    st.success("Checklist Repaired Successfully!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Repair Failed: {res}. Please check Master Schedule.")
                    status.update(label="Repair Failed", state="error")
        # ---------------------------

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
            c1, c2 = st.columns(2)
            an = c1.text_input("Agent Name", value=get_val("Agent Name"), key=f"an_{b_choice}")
            ae = c2.text_input("Agent Email", value=get_val("Agent Email"), key=f"ae_{b_choice}")

            # --- AGENT EMAIL SECTION ---
            # Robust Filter
            agent_task_df = b_checklist[b_checklist['Responsibility'].astype(str).str.contains('Agent|Both', case=False, na=False)]
            
            if not agent_task_df.empty:
                imm_df = agent_task_df[agent_task_df['Timing'] == 'Immediate']
                if st.button("Generate Request PDF & Email"):
                    if ae and not validate_email(ae): st.error("Invalid Email")
                    else:
                        update_project_agent_details(b_choice, an, ae)
                        pdf = generate_appointment_pdf(b_choice, agent_task_df, an, get_val("Take On Date"))
                        with open(pdf, "rb") as f: st.download_button("Download PDF", f, file_name=pdf)
                        
                        imm_text = "\n".join([f"- {x}" for x in imm_df['Task Name'].tolist()])
                        email_body = f"Dear {an},\n\nWe confirm our appointment for {b_choice}.\n\nPlease provide the following URGENTLY:\n{imm_text}\n\nThe remaining items are required by the 10th.\n\nRegards, Pretor"
                        link = f'<a href="mailto:{ae}?subject=Handover&body={urllib.parse.quote(email_body)}" target="_blank">📧 Draft Email</a>'
                        st.markdown(link, unsafe_allow_html=True)
            else:
                st.info("No Agent-specific items found in checklist.")

        elif sub_nav == "Progress Tracker":
            st.markdown("### Checklist")
            
            # Logic to split items
            # Note: We know b_checklist is not empty because of Self-Healing above
            c_items = b_checklist.copy()
            c_items['Received'] = c_items['Received'].apply(lambda x: True if str(x).lower() == 'true' else False)
            if 'Delete' in c_items.columns: c_items['Delete'] = c_items['Delete'].apply(lambda x: True if str(x).lower() == 'true' else False)

            df_pending = c_items[(c_items['Received'] == False) & (c_items['Delete'] != True)]
            df_completed = c_items[(c_items['Received'] == True) | (c_items['Delete'] == True)]
            
            def fill_date(row):
                if row['Received'] and (pd.isna(row['Date Received']) or str(row['Date Received']).strip() == ''): return str(datetime.now().date())
                return row['Date Received']

            t1, t2 = st.tabs(["① Previous Agent Pending", "② Internal Pending"])
            sections = ["Take-On", "Financial", "Legal", "Statutory Compliance", "Insurance", "City Council", "Building Compliance", "Employee", "General"]
            
            with t1:
                # AGENT PENDING
                mask_agent = df_pending['Responsibility'].astype(str).str.contains('Agent|Both', case=False, na=False)
                ag_pend = df_pending[mask_agent].copy()
                
                if not ag_pend.empty:
                    ag_pend['Sort'] = ag_pend['Task Heading'].apply(lambda x: sections.index(x) if x in sections else 99)
                    ag_pend = ag_pend.sort_values(by=['Sort', 'Task Name'])
                    
                    # UPLOAD
                    st.markdown("##### 📎 Attach Document")
                    sel_item = st.selectbox("Select Item", ["None"] + ag_pend['Task Name'].tolist(), key=f"up_sel_{b_choice}")
                    if sel_item != "None":
                        uf = st.file_uploader("Upload", key=f"uf_{b_choice}")
                        if uf and st.button("Upload File", key=f"ub_{b_choice}"):
                            row_id = ag_pend[ag_pend['Task Name'] == sel_item].iloc[0]['id']
                            url = upload_file_to_supabase(uf, f"{b_choice}/Checklist/{sel_item}_{uf.name}")
                            if url: update_document_url("Checklist", row_id, url); st.success("Uploaded!")

                    # EDITOR
                    edited_ag = st.data_editor(ag_pend[['id', 'Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes', 'Delete']], hide_index=True, height=400, key=f"ag_ed_{b_choice}", column_config={"id": None})
                    if st.button("Save Agent Items", key=f"sv_ag_{b_choice}"):
                        edited_ag['Date Received'] = edited_ag.apply(fill_date, axis=1)
                        save_checklist_batch(b_choice, edited_ag, st.session_state.get('user_email')); st.cache_data.clear(); st.success("Saved!"); st.rerun()
                else:
                    st.success("✅ No pending items for Previous Agent.")

            with t2:
                # INTERNAL PENDING
                mask_int = df_pending['Responsibility'].astype(str).str.contains('Pretor|Both', case=False, na=False)
                int_pend = df_pending[mask_int].copy()
                if not int_pend.empty:
                    int_pend['Sort'] = int_pend['Task Heading'].apply(lambda x: sections.index(x) if x in sections else 99)
                    int_pend = int_pend.sort_values(by=['Sort', 'Task Name'])
                    ed_int = st.data_editor(int_pend[['id', 'Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes', 'Delete']], hide_index=True, height=400, key=f"int_ed_{b_choice}", column_config={"id": None})
                    if st.button("Save Internal Items", key=f"sv_int_{b_choice}"):
                        ed_int['Date Received'] = ed_int.apply(fill_date, axis=1)
                        save_checklist_batch(b_choice, ed_int, st.session_state.get('user_email')); st.cache_data.clear(); st.success("Saved!"); st.rerun()
                else:
                    st.success("✅ No pending internal items.")

            st.divider()
            st.markdown("#### ✅ History (Completed)")
            if not df_completed.empty:
                st.dataframe(df_completed[['Task Heading', 'Task Name', 'Responsibility', 'Date Received', 'Completed By']], hide_index=True)

        # --- OTHER TABS ---
        elif sub_nav == "Staff Details":
            # (Use code from previous successful version - shortened here for context)
            st.subheader("Staff Management"); all_s = get_data("Employees")
            # ... (Full logic for staff, ID validation, upload etc.)
            st.info("Full Staff Logic here (from previous file)")

        elif sub_nav == "Arrears Details":
            st.subheader("Arrears"); ad = get_data("Arrears")
            # ... (Full logic for Arrears upload etc.)
            st.info("Full Arrears Logic here")

        elif sub_nav == "Council Details":
            st.subheader("Council"); cd = get_data("Council")
            # ... (Full logic for Council upload etc.)
            st.info("Full Council Logic here")

        elif sub_nav == "Department Handovers":
            st.subheader("Department Handovers")
            # ... (Full logic for emails)
            st.info("Full Dept Handovers Logic here")
            
        elif sub_nav == "Client Updates":
            st.subheader("Client Updates")
            # ... (Full logic for client)
            st.info("Full Client Updates Logic here")

        st.divider()
        if st.button("Finalize Project"): finalize_project_db(b_choice); st.cache_data.clear(); st.balloons()

if __name__ == "__main__":
    if 'user' not in st.session_state: login_screen()
    else: main_app()
