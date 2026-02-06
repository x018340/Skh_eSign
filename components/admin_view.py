import streamlit as st
import pandas as pd
from datetime import datetime
from core.connection import get_sheet_object
from core.state import refresh_all_data
from services.pdf_service import generate_qr_card
from config import DEPLOYMENT_URL, FONT_CH
from utils import safe_int, safe_str, map_dict_to_row, base64_to_image
from fpdf import FPDF
import time
import random
import os

def show_admin():
    st.sidebar.title("Navigation")
    menu = st.sidebar.radio("Go to:", ["🗓️ Arrange Meeting", "🛡️ Meeting Control", "👥 Employee Master"])
    
    st.sidebar.divider()
    if st.sidebar.button("🔄 Refresh Data (Sync)"):
        refresh_all_data()
        st.session_state.meeting_limit = 10 
        st.sidebar.success("Updated!")
        time.sleep(1)
        st.rerun()

    if menu == "🗓️ Arrange Meeting":
        st.title("Arrange New Meeting")
        df_master = st.session_state.df_master
        if df_master is None or df_master.empty or "FullName" not in df_master.columns:
            st.warning("⚠️ Database connection unstable. Please click Refresh.")
            if st.button("🔄 Retry Connection"):
                refresh_all_data()
                st.rerun()
            st.stop()

        if "created_meeting_data" in st.session_state and st.session_state.created_meeting_data:
            lm = st.session_state.created_meeting_data
            st.success(f"🎉 Meeting Created: **{lm['name']}** (ID: {lm['id']})")
            
            card_bytes = generate_qr_card(lm['url'], lm['name'], lm['loc'], lm['time'])
            clean_date = str(lm['date']).replace("-", "").replace("/", "")
            clean_name = str(lm['name']).replace(" ", "_")
            qr_filename = f"{clean_date}_{clean_name}_{lm['id']}.png"
            
            c1, c2 = st.columns(2)
            with c1: st.image(card_bytes, caption="Preview", width=250)
            with c2:
                st.download_button("📥 Download QR Card", card_bytes, qr_filename, "image/png", type="primary")
                st.write("")
                if st.button("⬅️ Create Another Meeting"):
                    st.session_state.form_name = ""
                    st.session_state.form_loc = ""
                    st.session_state.form_selected = []
                    st.session_state.created_meeting_data = None
                    st.rerun()
        else:
            if "form_name" not in st.session_state: st.session_state.form_name = ""
            if "form_loc" not in st.session_state: st.session_state.form_loc = ""
            if "form_selected" not in st.session_state: st.session_state.form_selected = []

            col1, col2 = st.columns(2)
            name = col1.text_input("Meeting Name", key="form_name")
            loc = col2.text_input("Location", key="form_loc")
            date = col1.date_input("Meeting Date")
            c_t1, c_t2 = st.columns(2)
            t_start = c_t1.time_input("Start", value=datetime.strptime("12:00", "%H:%M").time())
            t_end = c_t2.time_input("End", value=datetime.strptime("13:00", "%H:%M").time())

            st.subheader("Select Attendees")
            depts = sorted(df_master["Department"].astype(str).unique().tolist()) if "Department" in df_master.columns else []
            sel_dept = st.multiselect("Filter by Department", depts)
            
            filtered_emp = df_master.copy()
            if sel_dept:
                filtered_emp = filtered_emp[filtered_emp["Department"].astype(str).isin(sel_dept)]
            
            if "RankID" in filtered_emp.columns:
                filtered_emp["RankID_Int"] = filtered_emp["RankID"].apply(lambda x: safe_int(x, 999))
                filtered_emp = filtered_emp.sort_values("RankID_Int")
            
            filtered_names = filtered_emp["FullName"].astype(str).tolist()
            current_selection = st.session_state.form_selected
            combined_options = []
            seen = set()
            for n in filtered_names + current_selection:
                if n not in seen:
                    combined_options.append(n)
                    seen.add(n)
            
            selected_names = st.multiselect("Attendees", combined_options, key="form_selected")

            is_valid = bool(name and loc and selected_names)
            if st.button("Create Meeting & Generate QR", type="primary", disabled=not is_valid):
                df_info_live = st.session_state.df_info
                max_id = 0
                if not df_info_live.empty and "MeetingID" in df_info_live.columns:
                    clean_ids = pd.to_numeric(df_info_live["MeetingID"], errors='coerce').fillna(0)
                    max_id = int(clean_ids.max())
                new_id = max_id + 1
                
                date_str = date.strftime('%Y/%m/%d')
                time_range = f"{date_str} {t_start.strftime('%H:%M')}~{t_end.strftime('%H:%M')}"
                
                ws_info = get_sheet_object("Meeting_Info")
                ws_info.append_row(map_dict_to_row(df_info_live.columns.tolist(), {
                    "MeetingID": new_id, "MeetingName": name, 
                    "MeetingDate": str(date), "Location": loc, 
                    "TimeRange": time_range, "MeetingStatus": "Open" 
                }))
                
                ws_att = get_sheet_object("Meeting_Attendees")
                att_cols = st.session_state.df_att.columns.tolist()
                rows = []
                for n in selected_names:
                    emp = df_master[df_master["FullName"].astype(str) == n].iloc[0]
                    rows.append(map_dict_to_row(att_cols, {
                        "AttendeeName": n, "JobTitle": emp.get("JobTitle",""),
                        "MeetingID": new_id, "RankID": safe_int(emp.get("RankID"), 999), 
                        "Status": "Pending", "SignatureBase64": ""
                    }))
                if rows: ws_att.append_rows(rows)
                
                refresh_all_data()
                st.session_state.created_meeting_data = {
                    'id': new_id, 'name': name, 'loc': loc, 'time': time_range, 'date': str(date),
                    'url': f"https://{DEPLOYMENT_URL}/?mid={new_id}"
                }
                st.rerun()

    elif menu == "🛡️ Meeting Control":
        st.title("Meeting Control")
        df_info, df_att = st.session_state.df_info, st.session_state.df_att
        c1, c2 = st.columns(2)
        s_id, s_date = c1.text_input("ID Filter"), c2.date_input("Date Filter", value=None)
        
        results = df_info.copy()
        results["d_obj"] = pd.to_datetime(results["MeetingDate"].astype(str).str.strip(), errors='coerce').dt.date
        if "MeetingID" in results.columns:
            results["m"] = pd.to_numeric(results["MeetingID"], errors='coerce')
        results = results.sort_values(by=["d_obj", "m"], ascending=[False, False])
        if s_id: results = results[results["MeetingID"].astype(str) == s_id]
        if s_date: results = results[results["d_obj"] == s_date]
        results = results.drop_duplicates(subset=['MeetingID'])
        
        display_results = results.head(st.session_state.meeting_limit) if not (s_id or s_date) else results

        for _, m in display_results.iterrows():
            m_id, m_name, status = str(m.get('MeetingID')), m.get('MeetingName'), m.get('MeetingStatus', 'Open')
            m_date = str(m.get('d_obj')).replace("-", "/")
            att_subset = df_att[df_att["MeetingID"].astype(str) == m_id]
            total, signed = len(att_subset), len(att_subset[att_subset["Status"] == "Signed"])
            
            with st.expander(f"{'🟢' if status=='Open' else '🔴'} {m_date} | {m_name} | {signed}/{total} Signed"):
                r1, r2, r3 = st.columns([1, 1, 2])
                with r1:
                    if st.button(f"{'🔒 Close' if status=='Open' else '🔓 Open'}", key=f"btn_lock_{m_id}"):
                        new_status = "Close" if status == "Open" else "Open"
                        ws_info = get_sheet_object("Meeting_Info")
                        all_vals = ws_info.get_all_values()
                        headers = all_vals[0]
                        id_idx, status_idx = headers.index("MeetingID"), headers.index("MeetingStatus") + 1
                        row_idx = -1
                        for i, r in enumerate(all_vals):
                            if i==0: continue
                            if safe_str(r[id_idx]) == m_id:
                                row_idx = i + 1
                                break
                        if row_idx > 0:
                            ws_info.update_cell(row_idx, status_idx, new_status)
                            refresh_all_data(); st.rerun()
                with r2:
                    m_url = f"https://{DEPLOYMENT_URL}/?mid={m_id}"
                    qr_bytes = generate_qr_card(m_url, str(m_name), str(m.get('Location')), str(m.get('TimeRange')))
                    clean_date_fn = str(m.get('MeetingDate')).replace("-", "").replace("/", "")
                    clean_name_fn = str(m_name).replace(" ", "_")
                    qr_fname = f"{clean_date_fn}_{clean_name_fn}_{m_id}.png"
                    st.download_button("📥 Download QR", qr_bytes, qr_fname, "image/png", key=f"qr_dl_{m_id}")
                with r3:
                    pdf_key = f"pdf_{m_id}"
                    if pdf_key in st.session_state.pdf_cache:
                        clean_date_fn = str(m.get('MeetingDate')).replace("-", "").replace("/", "")
                        clean_name_fn = str(m_name).replace(" ", "_")
                        fname = f"{clean_date_fn}_{clean_name_fn}_{m_id}.pdf"
                        st.download_button("📥 Download PDF", st.session_state.pdf_cache[pdf_key], fname, "application/pdf", key=f"dl_{m_id}")
                    else:
                        if st.button("📄 Generate PDF", key=f"gen_{m_id}"):
                            with st.spinner("Generating..."):
                                fresh_m = st.session_state.df_info[st.session_state.df_info["MeetingID"].astype(str) == m_id].iloc[0]
                                fresh_att_subset = st.session_state.df_att[st.session_state.df_att["MeetingID"].astype(str) == m_id]
                                if "RankID" in fresh_att_subset.columns:
                                    fresh_att_subset["RankID_Int"] = fresh_att_subset["RankID"].apply(lambda x: safe_int(x, 999))
                                    fresh_att_subset = fresh_att_subset.sort_values("RankID_Int")
                                
                                pdf = FPDF()
                                pdf.add_page()
                                pdf.add_font('CustomFont', '', FONT_CH, uni=True)
                                pdf.set_font('CustomFont', '', 24)
                                pdf.multi_cell(w=0, h=12, txt=f"{fresh_m.get('MeetingName')}簽到", align="C")
                                pdf.set_font_size(14)
                                
                                t_range = str(fresh_m.get('TimeRange', ''))
                                display_time = f"時間：{t_range}" if "/" in t_range else f"時間：{str(fresh_m.get('MeetingDate')).replace('-', '/')} {t_range}"
                                pdf.cell(0, 10, display_time, ln=True, align="C")
                                pdf.cell(0, 10, f"地點：{fresh_m.get('Location')}", ln=True, align="C")
                                pdf.ln(5)
                                pdf.set_fill_color(230, 230, 230)
                                pdf.set_font_size(16)
                                pdf.cell(80, 12, "出席人員", 1, 0, 'C', True)
                                pdf.cell(110, 12, "簽名", 1, 1, 'C', True)
                                for i, row in fresh_att_subset.reset_index().iterrows():
                                    pdf.cell(80, 25, str(row.get('AttendeeName')), 1, 0, 'C')
                                    x, y = pdf.get_x(), pdf.get_y()
                                    pdf.cell(110, 25, "", 1, 1)
                                    sig = row.get('SignatureBase64')
                                    if sig and len(str(sig)) > 20:
                                        img = base64_to_image(sig)
                                        if img:
                                            tmp_name = f"tmp_{m_id}_{i}.png"
                                            img.save(tmp_name)
                                            pdf.image(tmp_name, x+35, y+4, h=17)
                                            os.remove(tmp_name)
                                st.session_state.pdf_cache[pdf_key] = bytes(pdf.output())
                                st.rerun()
        if not (s_id or s_date):
            if st.button("⬇️ Load 10 More Records", type="secondary", use_container_width=True):
                st.session_state.meeting_limit += 10
                st.rerun()

    elif menu == "👥 Employee Master":
        st.title("Employee Master")
        df_master = st.session_state.df_master
        if df_master is not None:
            with st.expander("➕ Add New Employee"):
                with st.form("add_emp"):
                    c1, c2 = st.columns(2)
                    new_rank = c1.number_input("Rank ID", min_value=1, step=1, value=99)
                    new_name = c2.text_input("Full Name")
                    new_job = c1.text_input("Job Title")
                    new_dept = c2.text_input("Department")
                    if st.form_submit_button("Add to Master"):
                        ws_master = get_sheet_object("Employee_Master")
                        ws_master.append_row(map_dict_to_row(df_master.columns.tolist(), {"RankID": int(new_rank), "FullName": new_name, "JobTitle": new_job, "Department": new_dept}))
                        refresh_all_data(); st.rerun()
            edited_df = st.data_editor(df_master, num_rows="dynamic", use_container_width=True, height=600)
            if st.button("💾 Save Changes to Cloud", type="primary"):
                ws_master = get_sheet_object("Employee_Master")
                ws_master.clear()
                ws_master.update([edited_df.columns.tolist()] + edited_df.values.tolist())
                refresh_all_data(); st.success("✅ Saved!"); time.sleep(1); st.rerun()
