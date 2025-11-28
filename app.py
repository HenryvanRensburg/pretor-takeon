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
import tempfile
from fpdf import FPDF

# --- PAGE CONFIG ---
st.set_page_config(page_title="Pretor Take-On", layout="wide")

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

    def sub_section_title(self, label):
        self.set_font('Arial', 'B', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, self.clean_text(label), 0, 1, 'L')
        self.set_text_color(0, 0, 0)

    def entry_row(self, label, value):
        self.set_font('Arial', 'B', 9)
        self.cell(55, 5, self.clean_text(label), 0)
        self.set_font('Arial', '', 9)
        self.multi_cell(0, 5, self.clean_text(str(value)))

def create_comprehensive_pdf(complex_name, p_row, checklist_df, emp_df, arrears_df, council_df):
    pdf = HandoverReport()
    pdf.add_page()
    
    # --- 1. OVERVIEW (ALL FIELDS) ---
    pdf.section_title(f"1. Overview: {complex_name}")
    pdf.ln(2)

    # A. General
    pdf.sub_section_title("General & Address")
    general_data = {
        "Building Code": "Building Code", "Type": "Type", "No of Units": "No of Units",
        "SS Number": "SS Number", "Erf Number": "Erf Number", "CSOS Number": "CSOS Number",
        "Physical Address": "Physical Address"
    }
    for label, db_col in general_data.items():
        val = p_row.get(db_col, '')
        if val and val != 'None': pdf.entry_row(label + ":", val)
    pdf.ln(2)

    # B. Financial
    pdf.sub_section_title("Financial & Compliance")
    fin_data = {
        "Year End": "Year End", "Mgmt Fees": "Mgmt Fees", "Expense Code": "Expense Code",
        "VAT Number": "VAT Number", "Tax Number": "Tax Number", "Take On Date": "Take On Date",
        "Auditor": "Auditor", "Last Audit": "Last Audit"
    }
    for label, db_col in fin_data.items():
        val = p_row.get(db_col, '')
        if val and val != 'None': pdf.entry_row(label + ":", val)
    pdf.ln(2)

    # C. Team
    pdf.sub_section_title("The Team")
    team_data = {
        "Portfolio Manager": "Assigned Manager", "PM Email": "Manager Email",
        "Portfolio Assistant": "Portfolio Assistant", "PA Email": "Portfolio Assistant Email",
        "Bookkeeper": "Bookkeeper", "Bookkeeper Email": "Bookkeeper Email",
        "Take-On Manager": "TakeOn Name", "Client Email": "Client Email"
    }
    for label, db_col in team_data.items():
        val = p_row.get(db_col, '')
        if val and val != 'None': pdf.entry_row(label + ":", val)
    
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
                notes = f" (Note: {pdf.clean_text(str(row['Notes']))})" if row['Notes'] else ""
                pdf.cell(5)
                pdf.multi_cell(0, 5, f"- {t_name}{notes} [Received: {d_rec}]")
        else:
            pdf.set_font("Arial", "I", 9); pdf.cell(0, 6, "No items marked as received from agent yet.", 0, 1)
    else: pdf.cell(0, 6, "No checklist data.", 0, 1)
    pdf.ln(4)

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
                pdf.cell(5)
                pdf.multi_cell(0, 5, f"- {t_name} (Completed)")
        else:
            pdf.set_font("Arial", "I", 9); pdf.cell(0, 6, "No internal actions completed yet.", 0, 1)
    else: pdf.cell(0, 6, "No checklist data.", 0, 1)
    pdf.ln(4)

    # 4. STAFF
    pdf.section_title("4. Staff & Wages Loaded")
    if not emp_df.empty and 'Complex Name' in emp_df.columns:
        c_emp = emp_df[emp_df['Complex Name'] == complex_name]
        if not c_emp.empty:
            pdf.set_font("Arial", "B", 8)
            pdf.cell(60, 6, "Name", 1)
            pdf.cell(50, 6, "Position", 1)
            pdf.cell(30, 6, "Salary", 1)
            pdf.cell(20, 6, "Docs?", 1)
            pdf.ln()
            pdf.set_font("Arial", "", 8)
            for _, row in c_emp.iterrows():
                name = pdf.clean_text(f"{row.get('Name','')} {row.get('Surname','')}")
                pos = pdf.clean_text(str(row.get('Position','')))
                sal = f"R {row.get('Salary',0)}"
                has_docs = "Yes" if str(row.get('Contract Received', 'False')).lower() == 'true' else "No"
                pdf.cell(60, 6, name, 1)
                pdf.cell(50, 6, pos, 1)
                pdf.cell(30, 6, sal, 1)
                pdf.cell(20, 6, has_docs, 1)
                pdf.ln()
        else: pdf.cell(0, 6, "No staff loaded.", 0, 1)
    else: pdf.cell(0, 6, "No staff data.", 0, 1)
    pdf.ln(4)

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
        else: pdf.cell(0, 6, "No arrears loaded.", 0, 1)
    else: pdf.cell(0, 6, "No arrears data.", 0, 1)
    pdf.ln(4)

    # 6. COUNCIL
    pdf.section_title("6. Council Accounts")
    if not council_df.empty and 'Complex Name' in council_df.columns:
        c_coun = council_df[council_df['Complex Name'] == complex_name]
        if not c_coun.empty:
            pdf.set_font("Arial", "B", 8)
            pdf.cell(60, 6, "Account Number", 1)
            pdf.cell(60, 6, "Service", 1)
            pdf.cell(40, 6, "Balance", 1)
            pdf.ln()
            pdf.set_font("Arial", "", 8)
            for _, row in c_coun.iterrows():
                acc = pdf.clean_text(str(row.get('Account Number','')))
                svc = pdf.clean_text(str(row.get('Service','')))
                bal = f"R {row.get('Balance',0)}"
                pdf.cell(60, 6, acc, 1)
                pdf.cell(60, 6, svc, 1)
                pdf.cell(40, 6, bal, 1)
                pdf.ln()
        else: pdf.cell(0, 6, "No council accounts loaded.", 0, 1)
    else: pdf.cell(0, 6, "No council data.", 0, 1)
    pdf.ln(4)

    # 7. DATES
    pdf.section_title("7. Internal Department Handover Dates")
    pdf.set_font("Arial", "", 9)
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

# --- APP START ---
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
                ["Overview", "Progress Tracker", "Staff Details", "Arrears Details", "Council Details", "Department Handovers", "Client Updates"], 
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
                    
                    c_items['Received'] = c_items['Received'].apply(lambda x: True if str(x).lower() == 'true' else False)
                    if 'Delete' in c_items.columns:
                        c_items['Delete'] = c_items['Delete'].apply(lambda x: True if str(x).lower() == 'true' else False)

                    df_pending = c_items[(c_items['Received'] == False) & (c_items['Delete'] != True)]
                    df_completed = c_items[(c_items['Received'] == True) | (c_items['Delete'] == True)]

                    def fill_date_if_received(row):
                        if row['Received'] and (pd.isna(row['Date Received']) or str(row['Date Received']).strip() == ''):
                            return str(datetime.now().date())
                        return row['Date Received']

                    st.markdown("#### 📝 Pending Actions")
                    t1, t2 = st.tabs(["① Previous Agent Pending", "② Internal Pending"])
                    sections = ["Take-On", "Financial", "Legal", "Statutory Compliance", "Insurance", "City Council", "Building Compliance", "Employee", "General"]

                    with t1:
                        if not df_pending.empty:
                            agent_pending = df_pending[df_pending['Responsibility'].isin(['Previous Agent', 'Both'])].copy()
                            if not agent_pending.empty:
                                agent_pending['Sort'] = agent_pending['Task Heading'].apply(lambda x: sections.index(x) if x in sections else 99)
                                agent_pending = agent_pending.sort_values(by=['Sort', 'Task Name'])
                                
                                edited_agent = st.data_editor(
                                    agent_pending[['id', 'Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes', 'Delete']],
                                    hide_index=True,
                                    height=400,
                                    key="agent_editor",
                                    column_config={
                                        "id": None,
                                        "Task Heading": st.column_config.TextColumn(disabled=True),
                                        "Task Name": st.column_config.TextColumn(disabled=True)
                                    }
                                )
                                if st.button("Save Agent Items"):
                                    edited_agent['Date Received'] = edited_agent.apply(fill_date_if_received, axis=1)
                                    save_checklist_batch(b_choice, edited_agent)
                                    st.cache_data.clear()
                                    st.success("Saved!")
                                    st.rerun()
                                
                                st.divider()
                                st.markdown("#### 📧 Follow Up with Previous Agent")
                                agent_email = get_val("Agent Email")
                                agent_name = get_val("Agent Name")
                                
                                if agent_email and agent_email != "None":
                                    email_list = ""
                                    for _, r in agent_pending.iterrows():
                                        email_list += f"- {r['Task Name']}\n"
                                    agent_sub = urllib.parse.quote(f"Outstanding Handover Items: {b_choice}")
                                    agent_body = f"Dear {agent_name},\n\nWe refer to the handover process for {b_choice}.\n\nThe following items remain outstanding:\n{email_list}\nWe must stress the need for a complete handover to be done.\nPlease ensure that these documents are handed over as soon as possible, but not later than the 10th of the month in which Pretor Group was appointed.\n\nRegards,\nPretor Take-On Team"
                                    agent_link = f'<a href="mailto:{agent_email}?subject={agent_sub}&body={urllib.parse.quote(agent_body)}" target="_blank" style="text-decoration:none; color:white; background-color:#FF4B4B; padding:8px 12px; border-radius:5px;">📧 Draft Follow-Up Email</a>'
                                    st.markdown(agent_link, unsafe_allow_html=True)
                            else:
                                st.info("No pending items for Previous Agent.")
                        else:
                            agent_completed_items = c_items[
                                (c_items['Responsibility'].isin(['Previous Agent', 'Both'])) & 
                                (c_items['Received'] == True)
                            ]
                            
                            if not agent_completed_items.empty:
                                try: last_date = pd.to_datetime(agent_completed_items['Date Received'], errors='coerce').max().strftime('%Y-%m-%d')
                                except: last_date = "Unknown"
                                if last_date == "NaT": last_date = "Unknown"

                                st.success(f"✅ All items received from Previous Agent! Last document received on: **{last_date}**")
                                
                                st.divider()
                                st.markdown("#### 🚀 Take-On Complete: Notify Client")
                                
                                comp_sent_date = get_val("Client Completion Email Sent Date")
                                report_gen_date = get_val("Client Report Generated Date")
                                client_email_addr = get_val("Client Email")
                                
                                # STEP 1: REPORT
                                st.markdown("**Step 1: Generate Handover Report**")
                                
                                if report_gen_date and report_gen_date != "None":
                                    st.success(f"✅ Report Generated on: {report_gen_date}")
                                    emp_df, arr_df, cou_df = get_data("Employees"), get_data("Arrears"), get_data("Council")
                                    pdf_file = create_comprehensive_pdf(b_choice, p_row, c_items, emp_df, arr_df, cou_df)
                                    with open(pdf_file, "rb") as f:
                                        st.download_button("⬇️ Download Copy of Report", f, file_name=pdf_file, mime="application/pdf")
                                    
                                    if st.button("Unlock (Regenerate Report)", key="unlock_rep_gen"):
                                        update_email_status(b_choice, "Client Report Generated Date", "")
                                        st.cache_data.clear()
                                        st.rerun()
                                else:
                                    if st.button("📄 Generate & Lock Report", key="btn_gen_lock_rep"):
                                        emp_df, arr_df, cou_df = get_data("Employees"), get_data("Arrears"), get_data("Council")
                                        create_comprehensive_pdf(b_choice, p_row, c_items, emp_df, arr_df, cou_df)
                                        update_email_status(b_choice, "Client Report Generated Date")
                                        st.cache_data.clear()
                                        st.rerun()

                                # STEP 2: EMAIL
                                st.markdown("**Step 2: Send Email**")
                                if comp_sent_date and comp_sent_date != "None":
                                    st.success(f"✅ Completion Email Sent on: {comp_sent_date}")
                                    if st.button("Unlock (Resend)", key="rst_client_comp"):
                                        update_email_status(b_choice, "Client Completion Email Sent Date", "")
                                        st.cache_data.clear()
                                        st.rerun()
                                else:
                                    if client_email_addr and client_email_addr != "None":
                                        comp_body = f"Dear Client,\n\nWe are pleased to confirm that the take-on process for {b_choice} has been successfully completed.\n\nAll relevant information has been received and filed accordingly.\n\nWe appreciate the trust you have placed in Pretor Group. We undertake to ensure that the complex is managed with the utmost integrity going forward.\n\nRegards,\nPretor Take-On Team"
                                        comp_sub = urllib.parse.quote(f"Take-On Completed: {b_choice}")
                                        comp_link = f'<a href="mailto:{client_email_addr}?subject={comp_sub}&body={urllib.parse.quote(comp_body)}" target="_blank" style="text-decoration:none; color:white; background-color:#09ab3b; padding:10px 20px; border-radius:5px; font-weight:bold; display:inline-block;">📧 Draft Email</a>'
                                        st.markdown(comp_link, unsafe_allow_html=True)
                                        
                                        st.write("")
                                        if st.button("Mark as Sent", key="btn_client_comp_sent"):
                                            update_email_status(b_choice, "Client Completion Email Sent Date")
                                            st.cache_data.clear()
                                            st.rerun()
                                    else:
                                        st.warning("⚠️ Client Email missing in Overview tab.")
                            else:
                                st.info("No items assigned to Previous Agent.")

                    with t2:
                        if not df_pending.empty:
                            internal_pending = df_pending[df_pending['Responsibility'].isin(['Pretor Group', 'Both'])].copy()
                            if not internal_pending.empty:
                                internal_pending['Sort'] = internal_pending['Task Heading'].apply(lambda x: sections.index(x) if x in sections else 99)
                                internal_pending = internal_pending.sort_values(by=['Sort', 'Task Name'])
                                edited_internal = st.data_editor(internal_pending[['id', 'Task Heading', 'Task Name', 'Received', 'Date Received', 'Notes', 'Delete']], hide_index=True, height=400, key="internal_editor", column_config={"id": None, "Task Heading": st.column_config.TextColumn(disabled=True), "Task Name": st.column_config.TextColumn(disabled=True)})
                                if st.button("Save Internal Items"):
                                    edited_internal['Date Received'] = edited_internal.apply(fill_date_if_received, axis=1)
                                    save_checklist_batch(b_choice, edited_internal)
                                    st.cache_data.clear()
                                    st.success("Saved!")
                                    st.rerun()
                            else:
                                st.info("No pending internal items.")
                        else:
                            st.info("No pending items.")

                    st.divider()
                    st.markdown("#### ✅ Completed / History (Locked)")
                    if not df_completed.empty:
                        agent_hist = df_completed[df_completed['Responsibility'].isin(['Previous Agent', 'Both'])]
                        internal_hist = df_completed[df_completed['Responsibility'].isin(['Pretor Group', 'Both'])]
                        h1, h2 = st.tabs(["Agent History", "Internal History"])
                        with h1:
                            if not agent_hist.empty:
                                st.dataframe(agent_hist[['Task Heading', 'Task Name', 'Date Received', 'Notes']], hide_index=True, use_container_width=True)
                            else:
                                st.info("No completed items for Previous Agent.")
                        with h2:
                            if not internal_hist.empty:
                                st.dataframe(internal_hist[['Task Heading', 'Task Name', 'Date Received', 'Notes']], hide_index=True, use_container_width=True)
                            else:
                                st.info("No completed Internal items.")
                    else:
                        st.info("No items completed yet.")
                else:
                    st.info("No checklist loaded for this complex.")

            # --- SUB SECTION 3: STAFF DETAILS ---
            elif sub_nav == "Staff Details":
                st.subheader(f"Staff Management: {b_choice}")
                # Same as before
                uif_val = get_val("UIF Number") if "UIF Number" in p_row.index else ""
                paye_val = get_val("PAYE Number") if "PAYE Number" in p_row.index else ""
                coida_val = get_val("COIDA Number") if "COIDA Number" in p_row.index else ""

                def is_filled(val): return val and str(val).lower() not in ["none", "nan", ""]
                locked = is_filled(uif_val) or is_filled(paye_val) or is_filled(coida_val)

                st.markdown("#### 🏢 Project Statutory Numbers")
                if locked:
                    c1, c2, c3 = st.columns(3)
                    c1.text_input("UIF Number", value=uif_val, disabled=True, key="uif_lock")
                    c2.text_input("PAYE Number", value=paye_val, disabled=True, key="paye_lock")
                    c3.text_input("COIDA / Workmens Comp", value=coida_val, disabled=True, key="coida_lock")
                else:
                    st.info("ℹ️ Enter carefully. Once saved, these will be locked.")
                    with st.form("stat_nums"):
                        c1, c2, c3 = st.columns(3)
                        uif_n = c1.text_input("UIF Number", value=uif_val); paye_n = c2.text_input("PAYE Number", value=paye_val); coida_n = c3.text_input("COIDA / Workmens Comp", value=coida_val)
                        if st.form_submit_button("💾 Save & Lock"):
                            update_building_details_batch(b_choice, {"UIF Number": uif_n, "PAYE Number": paye_n, "COIDA Number": coida_n})
                            st.cache_data.clear(); st.success("Saved and locked."); st.rerun()

                st.divider(); st.markdown("#### 👥 Employee List (Editable)")
                all_staff = get_data("Employees")
                if not all_staff.empty:
                    if 'Complex Name' in all_staff.columns:
                        current_staff = all_staff[all_staff['Complex Name'] == b_choice].copy()
                    else: current_staff = pd.DataFrame()
                else: current_staff = pd.DataFrame()

                if not current_staff.empty:
                    for col in ['Payslip Received', 'Contract Received', 'Tax Ref Received']:
                        if col in current_staff.columns:
                            current_staff[col] = current_staff[col].apply(lambda x: True if str(x).lower() == 'true' else False)
                    display_cols = ['id', 'Name', 'Surname', 'ID Number', 'Position', 'Salary', 'Payslip Received', 'Contract Received', 'Tax Ref Received']
                    final_cols = [c for c in display_cols if c in current_staff.columns]
                    edited_df = st.data_editor(current_staff[final_cols], hide_index=True, use_container_width=True, column_config={"id": None, "Salary": st.column_config.NumberColumn(format="R %.2f")}, key="staff_editor")
                    if st.button("💾 Save Changes to Staff List"):
                        update_employee_batch(edited_df); st.cache_data.clear(); st.success("Updated!"); st.rerun()
                else: st.info("No staff loaded.")

                st.divider(); st.markdown("#### ➕ Add New Employee")
                with st.form("add_emp", clear_on_submit=True):
                    c1, c2, c3 = st.columns(3)
                    e_name = c1.text_input("Name", key="new_name"); e_sur = c2.text_input("Surname", key="new_sur"); e_id = c3.text_input("ID Number", key="new_id")
                    c4, c5 = st.columns(2)
                    e_pos = c4.text_input("Position", key="new_pos"); e_sal = c5.number_input("Gross Salary", min_value=0.0, key="new_sal")
                    st.markdown("**Documents Received:**")
                    col_a, col_b, col_c = st.columns(3)
                    chk_pay = col_a.checkbox("Latest Payslip", key="new_chk_pay"); chk_con = col_b.checkbox("Employment Contract", key="new_chk_con"); chk_tax = col_c.checkbox("Indiv Tax Number", key="new_chk_tax")
                    if st.form_submit_button("Add Employee"):
                        add_employee(b_choice, e_name, e_sur, e_id, e_pos, float(e_sal), chk_pay, chk_con, chk_tax)
                        st.cache_data.clear(); st.success("Employee Added"); st.rerun()

            # --- SUB SECTION 4: ARREARS DETAILS ---
            elif sub_nav == "Arrears Details":
                st.subheader(f"Arrears Management: {b_choice}")
                arrears_data = get_data("Arrears")
                if not arrears_data.empty:
                    rename_map_arr = {'complex_name': 'Complex Name', 'unit_number': 'Unit Number', 'outstanding_amount': 'Outstanding Amount', 'attorney_name': 'Attorney Name', 'attorney_email': 'Attorney Email', 'attorney_phone': 'Attorney Phone'}
                    arrears_data.rename(columns=rename_map_arr, inplace=True)
                if not arrears_data.empty and 'Complex Name' in arrears_data.columns:
                    curr_arrears = arrears_data[arrears_data['Complex Name'] == b_choice].copy()
                    if not curr_arrears.empty:
                        st.markdown("#### 📝 Arrears List (Editable)")
                        arr_cols = ['id', 'Unit Number', 'Outstanding Amount', 'Attorney Name', 'Attorney Email', 'Attorney Phone']
                        arr_cols = [c for c in arr_cols if c in curr_arrears.columns]
                        edited_arrears = st.data_editor(curr_arrears[arr_cols], hide_index=True, use_container_width=True, column_config={"id": None, "Outstanding Amount": st.column_config.NumberColumn(format="R %.2f")}, key="arrears_editor")
                        if st.button("💾 Save Changes to Arrears"):
                            update_arrears_batch(edited_arrears); st.cache_data.clear(); st.success("Updated!"); st.rerun()
                    else: st.info("No arrears loaded.")
                else: st.info("No arrears data.")
                st.divider()
                with st.expander("➕ Add New Arrears Record", expanded=True):
                    with st.form("add_arr_form", clear_on_submit=True):
                        c1, c2 = st.columns(2); a_unit = c1.text_input("Unit Number", key="new_a_u"); a_amt = c2.number_input("Outstanding Amount", min_value=0.0, key="new_a_a")
                        c3, c4, c5 = st.columns(3); a_att = c3.text_input("Attorney Name", key="new_a_n"); a_mail = c4.text_input("Attorney Email", key="new_a_e"); a_ph = c5.text_input("Attorney Phone", key="new_a_p")
                        if st.form_submit_button("Add Record"):
                            add_arrears_item(b_choice, a_unit, a_amt, a_att, a_mail, a_ph); st.cache_data.clear(); st.success("Added"); st.rerun()

            # --- SUB SECTION 5: COUNCIL DETAILS ---
            elif sub_nav == "Council Details":
                st.subheader(f"Council Management: {b_choice}")
                council_data = get_data("Council")
                if council_data.empty: council_data = get_data("council")
                if not council_data.empty:
                    council_data.columns = [c.strip() for c in council_data.columns]
                    rename_map = {'complex_name': 'Complex Name', 'account_number': 'Account Number', 'service': 'Service', 'balance': 'Balance'}
                    council_data.rename(columns=rename_map, inplace=True)
                if not council_data.empty and 'Complex Name' in council_data.columns:
                    curr_council = council_data[council_data['Complex Name'] == b_choice].copy()
                    if not curr_council.empty:
                        st.markdown("#### 📝 Council Accounts (Editable)")
                        c_cols = ['id', 'Account Number', 'Service', 'Balance']
                        c_cols = [c for c in c_cols if c in curr_council.columns]
                        edited_council = st.data_editor(curr_council[c_cols], hide_index=True, use_container_width=True, column_config={"id": None, "Balance": st.column_config.NumberColumn(format="R %.2f")}, key="council_editor")
                        if st.button("💾 Save Changes to Accounts"):
                            update_council_batch(edited_council); st.cache_data.clear(); st.success("Updated!"); st.rerun()
                    else: st.info("No accounts loaded.")
                else: st.info("No council data.")
                st.divider()
                with st.expander("➕ Add New Council Account", expanded=True):
                    with st.form("add_c_form", clear_on_submit=True):
                        c1, c2, c3 = st.columns(3); an = c1.text_input("Acc Number", key="new_c_an"); sv = c2.text_input("Service", key="new_c_sv"); bl = c3.number_input("Balance", key="new_c_bl")
                        if st.form_submit_button("Add Account"):
                            add_council_account(b_choice, an, sv, bl); st.cache_data.clear(); st.success("Added"); st.rerun()

            # --- SUB SECTION 6: DEPARTMENT HANDOVERS ---
            elif sub_nav == "Department Handovers":
                st.markdown("### Department Handovers")
                settings = get_data("Settings")
                s_dict = dict(zip(settings["Department"], settings["Email"])) if not settings.empty else {}

                # SARS
                st.markdown("#### SARS")
                sars_email = s_dict.get("SARS", "")
                sars_sent_date = get_val("SARS Sent Date")
                if sars_sent_date and sars_sent_date != "None":
                    st.success(f"✅ Sent on: {sars_sent_date}")
                    if st.button("Reset SARS", key="rst_sars"):
                        update_email_status(b_choice, "SARS Sent Date", "")
                        st.cache_data.clear()
                        st.rerun()
                else:
                    tax_num = get_val("Tax Number")
                    has_tax_num = tax_num and str(tax_num).lower() not in ['none', 'nan', '']
                    if has_tax_num:
                        st.success(f"📌 Tax Number: {tax_num}")
                    else:
                        st.warning("⚠️ No Tax Number.")
                    
                    if st.button("Mark SARS Sent", key="btn_sars"):
                        update_email_status(b_choice, "SARS Sent Date")
                        st.cache_data.clear()
                        st.rerun()
                
                st.divider()
                
                # COUNCIL (Handover)
                st.markdown("#### Council")
                muni_email = s_dict.get("Municipal", "")
                c_sent_date = get_val("Council Email Sent Date")
                
                council_path = f"Y:\\HenryJ\\NEW BUSINESS & DEVELOPMENTS\\{b_choice}\\council"
                c_body_str = f"Dear Council Team,\n\nCouncil accounts are at: {council_path}\n\nPlease load onto Pretor Portal.\n\nRegards,\nPretor"
                
                if c_sent_date and c_sent_date != "None":
                    st.success(f"✅ Sent on: {c_sent_date}")
                    if st.button("Reset Council", key="rst_coun"):
                        update_email_status(b_choice, "Council Email Sent Date", "")
                        st.cache_data.clear()
                        st.rerun()
                else:
                    col_c1, col_c2 = st.columns([1,1])
                    with col_c1:
                        lnk = f'<a href="mailto:{muni_email}?subject=Handover: {b_choice}&body={urllib.parse.quote(c_body_str)}" target="_blank" style="text-decoration:none; color:white; background-color:#FF4B4B; padding:8px 12px; border-radius:5px;">📧 Draft Email</a>'
                        st.markdown(lnk, unsafe_allow_html=True)
                    with col_c2:
                        if st.button("Mark Council Sent", key="btn_coun"):
                            update_email_status(b_choice, "Council Email Sent Date")
                            st.cache_data.clear()
                            st.rerun()

                st.divider()

                # Generic Handler
                def render_simple_handover(dept_name, db_col, email_key):
                    st.markdown(f"#### {dept_name}")
                    sent = get_val(db_col)
                    target = s_dict.get(email_key, "")
                    if sent and sent != "None":
                        st.success(f"✅ Sent on: {sent}")
                        if st.button(f"Reset {dept_name}", key=f"rst_{dept_name}"):
                            update_email_status(b_choice, db_col, "")
                            st.cache_data.clear()
                            st.rerun()
                    else:
                        st.info(f"Pending | Target: {target}")
                        col1, col2 = st.columns([1,1])
                        with col1:
                            subject = urllib.parse.quote(f"Handover: {b_choice} - {dept_name}")
                            body = urllib.parse.quote(f"Dear {dept_name} Team,\n\nPlease find attached handover docs.\n\nRegards.")
                            lnk = f'<a href="mailto:{target}?subject={subject}&body={body}" target="_blank" style="text-decoration:none; color:white; background-color:#FF4B4B; padding:8px 12px; border-radius:5px;">📧 Draft Email</a>'
                            st.markdown(lnk, unsafe_allow_html=True)
                        with col2:
                            if st.button(f"Mark {dept_name} Sent", key=f"btn_{dept_name}"):
                                update_email_status(b_choice, db_col)
                                st.cache_data.clear()
                                st.rerun()
                    st.divider()

                render_simple_handover("Internal Insurance", "Internal Ins Email Sent Date", "Insurance")
                render_simple_handover("Wages", "Wages Sent Date", "Wages")
                render_simple_handover("Debt Collection", "Debt Collection Sent Date", "Debt Collection")

                # Fee Confirmation
                st.markdown("#### Fee Confirmation")
                f_date = get_val("Fee Confirmation Email Sent Date")
                if f_date and f_date != "None":
                    st.success(f"✅ Sent: {f_date}")
                else:
                    if st.button("Mark Fee Email Sent"): 
                        update_email_status(b_choice, "Fee Confirmation Email Sent Date")
                        st.cache_data.clear()
                        st.rerun()

            # --- SUB SECTION 7: CLIENT UPDATES ---
            elif sub_nav == "Client Updates":
                st.subheader(f"Client Status Update: {b_choice}")
                st.markdown("Generate a progress report email for the client.")
                
                # 1. Internal Progress
                internal_status = "--- INTERNAL HANDOVERS ---\n"
                handovers = {
                    "Wages": get_val("Wages Sent Date"),
                    "Council": get_val("Council Email Sent Date"),
                    "Legal/Debt": get_val("Debt Collection Sent Date"),
                    "Insurance (Internal)": get_val("Internal Ins Email Sent Date"),
                    "SARS": get_val("SARS Sent Date")
                }
                
                for dept, date in handovers.items():
                    status = f"✅ Done ({date})" if (date and date != "None") else "⚠️ Pending"
                    internal_status += f"- {dept}: {status}\n"

                # 2. Checklist Status
                checklist = get_data("Checklist")
                received_list = "--- DOCUMENTS RECEIVED ---\n"
                pending_list = "--- OUTSTANDING ITEMS ---\n"
                
                c_items = pd.DataFrame()
                if not checklist.empty:
                    c_items = checklist[checklist['Complex Name'] == b_choice]
                    if not c_items.empty:
                        # Received
                        rec_items = c_items[c_items['Received'].astype(str).str.lower() == 'true']
                        if not rec_items.empty:
                            for _, r in rec_items.iterrows(): received_list += f"✔ {r['Task Name']}\n"
                        else: received_list += "(None yet)\n"
                        
                        # Outstanding
                        out_items = c_items[(c_items['Received'].astype(str).str.lower() != 'true') & (c_items['Delete'] != True)]
                        if not out_items.empty:
                            for _, r in out_items.iterrows(): pending_list += f"⭕ {r['Task Name']}\n"
                        else: pending_list += "(None - All Clear!)\n"
                    else:
                        received_list += "(No items)\n"
                        pending_list += "(No items)\n"

                # 3. PDF GENERATION
                emp_df = get_data("Employees")
                arrears_df = get_data("Arrears")
                council_df = get_data("Council")

                st.markdown("#### 1. Download Report PDF")
                st.caption("Attach this PDF to the email below.")
                if st.button("📄 Generate Handover Report PDF"):
                    pdf_file = create_comprehensive_pdf(b_choice, p_row, c_items, emp_df, arrears_df, council_df)
                    with open(pdf_file, "rb") as f:
                        st.download_button("⬇️ Click to Download PDF", f, file_name=pdf_file, mime="application/pdf")
                    st.success("PDF Generated successfully!")

                st.divider()

                # 4. EMAIL GENERATION
                st.markdown("#### 2. Send Update Email")
                client_email = get_val("Client Email")
                client_body = f"Dear Client,\n\nPlease find below a status update regarding the onboarding of {b_choice}.\n\n"
                client_body += "**Please see the attached PDF for a detailed breakdown of all items.**\n\n"
                client_body += internal_status + "\n"
                client_body += pending_list + "\n"
                client_body += "We are actively following up on the outstanding items.\n\nRegards,\nPretor Take-On Team"
                
                st.text_area("Preview Email Content", value=client_body, height=300)
                
                if client_email and client_email != "None":
                    sub = urllib.parse.quote(f"Status Update: {b_choice}")
                    bod = urllib.parse.quote(client_body)
                    lnk = f'<a href="mailto:{client_email}?subject={sub}&body={bod}" target="_blank" style="text-decoration:none; color:white; background-color:#FF4B4B; padding:10px 20px; border-radius:5px; font-weight:bold;">🚀 Send Update to Client</a>'
                    st.markdown(lnk, unsafe_allow_html=True)
                else:
                    st.warning("⚠️ Client Email is missing. Please add it in the 'Overview' tab.")

if __name__ == "__main__":
    main()
