import streamlit as st
import pandas as pd
from datetime import datetime
from services.data_service import api_read_with_retry, get_sheet_object
from core.state import refresh_all_data
from services.pdf_service import generate_qr_card
from config import DEPLOYMENT_URL, FONT_CH
from utils import safe_int, safe_str, map_dict_to_row, base64_to_image
from fpdf import FPDF
import time
import random
import os
import gspread

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

    ensure_data = st.session_state.df_master
    if menu == "🗓️ Arrange Meeting":
        st.title("Arrange New Meeting")
        
        # 🔥 CRASH PREVENTION
        df_master = st.session_state.df_master
        if df_master is None or df_master.empty or "FullName" not in df_master.columns:
            st.warning("⚠️ Database connection unstable. Please click Refresh.")
            if st.button("🔄 Retry Connection"):
                refresh_all_data()
                st.rerun()
            st.stop()

        def clear_create_form():
            st.session_state.form_name = ""
            st.session_state.form_loc = ""
            st.session_state.form_selected = []

        if "created_meeting_data" not in st.session_state:
            st.session_state.created_meeting_data = None

        if st.session_state.created_meeting_data:
            lm = st.session_state.created_meeting_data
            st.success(f"🎉 Meeting Created: **{lm['name']}** (ID: {lm['id']})")
            
            card_bytes = generate_qr_card(lm['url'], lm['name'], lm['loc'], lm['time'])
            # IDENTICAL NAMING LOGIC
            clean_date = str(lm['date']).replace("-", "").replace("/", "")
            clean_name = str(lm['name']).replace(" ", "_")
            qr_filename = f"{clean_date}_{clean_name}_{lm['id']}.png"
            
            c1, c2 = st.columns(2)
            with c1: st.image(card_bytes, caption="Preview", width=250)
            with c2:
                st.download_button("📥 Download QR Card", card_bytes, qr_filename, "image/png", type="primary")
                st.write("")
                if st.button("⬅️ Create Another Meeting"):
                    clear_create_form()
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
            
            depts = []
            if "Department" in df_master.columns:
                depts = sorted(df_master["Department"].astype(str).unique().tolist())
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

            st.divider()
            
            is_valid = bool(name and loc and selected_names)
            
            if "processing_create" not in st.session_state: 
                st.session_state.processing_create = False

            if st.session_state.processing_create:
                 st.button("⏳ Creating Meeting...", disabled=True)
                 
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
                 df_att_live = st.session_state.df_att
                 att_cols = df_att_live.columns.tolist()
                 
                 rows = []
                 for n in selected_names:
                     emp = df_master[df_master["FullName"].astype(str) == n].iloc[0]
                     rid = safe_int(emp.get("RankID"), 999)
                     rows.append(map_dict_to_row(att_cols, {
                         "AttendeeName": n, "JobTitle": emp.get("JobTitle",""),
                         "MeetingID": new_id, "RankID": rid, "Status": "Pending", "SignatureBase64": ""
                     }))
                 if rows: ws_att.append_rows(rows)
                 
                 refresh_all_data()
                 st.session_state.created_meeting_data = {
                     'id': new_id, 'name': name, 'loc': loc, 'time': time_range, 'date': str(date),
                     'url': f"https://{DEPLOYMENT_URL}/?mid={new_id}"
                 }
                 st.session_state.processing_create = False
                 st.rerun()

            else:
                 if st.button("Create Meeting & Generate QR", type="primary", disabled=not is_valid):
                     st.session_state.processing_create = True
                     st.rerun()

    # --- 2. MEETING CONTROL (Merged) ---
    elif menu == "🛡️ Meeting Control":
        st.title("Meeting Control")
        df_info = st.session_state.df_info
        df_att = st.session_state.df_att
        
        c1, c2 = st.columns(2)
        s_id = c1.text_input("ID Filter")
        s_date = c2.date_input("Date Filter", value=None)
        
        results = df_info.copy()
        
        results["d_obj"] = pd.to_datetime(results["MeetingDate"].astype(str).str.strip(), errors='coerce').dt.date
        if "MeetingID" in results.columns:
            results["m"] = pd.to_numeric(results["MeetingID"], errors='coerce')
        
        results = results.sort_values(by=["d_obj", "m"], ascending=[False, False])
        
        if s_id: results = results[results["MeetingID"].astype(str) == s_id]
        if s_date: results = results[results["d_obj"] == s_date]

        results = results.drop_duplicates(subset=['MeetingID'])
        
        limit = st.session_state.meeting_limit
        if not s_id and not s_date:
            display_results = results.head(limit)
            st.caption(f"Showing {len(display_results)} most recent meetings.")
        else:
            display_results = results

        for _, m in display_results.iterrows():
            m_id = str(m.get('MeetingID'))
            m_name = m.get('MeetingName')
            status = m.get('MeetingStatus', 'Open')
            m_date = str(m.get('d_obj')).replace("-", "/")
            
            att_subset = df_att[df_att["MeetingID"].astype(str) == m_id]
            total_count = len(att_subset)
            signed_count = len(att_subset[att_subset["Status"] == "Signed"])
            
            status_icon = "🟢" if status == "Open" else "🔴"
            title_str = f"{status_icon} {m_date} | {m_name} | {signed_count}/{total_count} Signed"
            
            with st.expander(title_str):
                r1, r2, r3 = st.columns([1, 1, 2])
                
                with r1:
                    if st.button(f"{
