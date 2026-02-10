import os
import random
import time
from datetime import datetime

import gspread
import pandas as pd
import streamlit as st
from fpdf import FPDF
import requests

from config import DEPLOYMENT_URL, FONT_CH, GAS_UPLOAD_URL, GAS_API_KEY, GAS_FOLDER_ID
from core.connection import get_sheet_object
from core.state import refresh_all_data
from services.pdf_service import generate_qr_card
from utils import image_from_signature_value, map_dict_to_row, safe_int, safe_str
from utils import make_white_background_transparent

# 🔥 LAG FIX: Cache the ping for 5 minutes so it doesn't hit the network on every click
@st.cache_data(ttl=300)
def _gas_ping():
    if not GAS_UPLOAD_URL:
        return False, "Missing gas.upload_url"
    try:
        r = requests.get(GAS_UPLOAD_URL, params={"action": "ping"}, timeout=10)
        r.raise_for_status()
        js = r.json()
        return bool(js.get("ok")), js.get("message","")
    except Exception as e:
        return False, str(e)

def show_admin():
    st.sidebar.title("Navigation")
    menu = st.sidebar.radio("Go to:", ["🗓️ Arrange Meeting", "🛡️ Meeting Control", "👥 Employee Master"])
    st.sidebar.divider()

    st.sidebar.subheader("Signature Storage (GAS)")
    ok, msg = _gas_ping()
    if ok:
        st.sidebar.success("✅ GAS online")
    else:
        st.sidebar.error("❌ GAS offline")
        st.sidebar.caption(msg)

    if st.sidebar.button("🔄 Refresh Data (Sync)"):
        refresh_all_data()
        st.session_state.meeting_limit = 10
        st.sidebar.success("Updated!")
        time.sleep(1)
        st.rerun()

    # ---- 🗓️ Arrange Meeting ----
    if menu == "🗓️ Arrange Meeting":
        st.title("Arrange New Meeting")

        df_master = st.session_state.df_master
        if df_master is None or df_master.empty:
            st.warning("⚠️ Database connection unstable. Please click Refresh.")
            st.stop()

        if st.session_state.get("created_meeting_data"):
            lm = st.session_state.created_meeting_data
            st.success(f"🎉 Meeting Created: **{lm['name']}** (ID: {lm['id']})")

            card_bytes = generate_qr_card(lm['url'], str(lm['name']), str(lm['loc']), str(lm['time']))
            qr_filename = f"{str(lm['date']).replace('-','')}_{str(lm['name']).replace(' ','_')}_{lm['id']}.png"

            c1, c2 = st.columns(2)
            with c1: st.image(card_bytes, caption="Preview", width=250)
            with c2:
                st.download_button("📥 Download QR Card", card_bytes, qr_filename, "image/png", type="primary")
                if st.button("⬅️ Create Another Meeting"):
                    st.session_state.created_meeting_data = None
                    st.rerun()
            return

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
        selected_names = st.multiselect("Attendees", filtered_names, key="form_selected")
        st.divider()

        if st.button("Create Meeting & Generate QR", type="primary", disabled=not (name and loc and selected_names)):
            with st.spinner("Creating..."):
                df_info_live = st.session_state.df_info
                max_id = pd.to_numeric(df_info_live["MeetingID"], errors='coerce').max() if not df_info_live.empty else 0
                new_id = int(max_id) + 1

                time_range = f"{date.strftime('%Y/%m/%d')} {t_start.strftime('%H:%M')}~{t_end.strftime('%H:%M')}"

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
                ws_att.append_rows(rows)

                refresh_all_data()
                st.session_state.created_meeting_data = {
                    'id': new_id, 'name': name, 'loc': loc, 'time': time_range, 'date': str(date),
                    'url': f"https://{DEPLOYMENT_URL}/?mid={new_id}"
                }
                st.rerun()

    # ---- 🛡️ Meeting Control ----
    elif menu == "🛡️ Meeting Control":
        st.title("Meeting Control")
        df_info = st.session_state.df_info
        df_att = st.session_state.df_att

        c1, c2 = st.columns(2)
        s_id = c1.text_input("ID Filter")
        s_date = c2.date_input("Date Filter", value=None)

        results = df_info.copy()
        results["d_obj"] = pd.to_datetime(results["MeetingDate"].astype(str).str.strip(), errors='coerce').dt.date
        results = results.sort_values(by=["MeetingDate", "MeetingID"], ascending=[False, False])
        
        if s_id: results = results[results["MeetingID"].astype(str) == s_id]
        if s_date: results = results[results["d_obj"] == s_date]
        results = results.drop_duplicates(subset=['MeetingID'])

        limit = st.session_state.meeting_limit
        display_results = results.head(limit) if (not s_id and not s_date) else results

        for _, m in display_results.iterrows():
            m_id = str(m.get('MeetingID'))
            att_subset = df_att[df_att["MeetingID"].astype(str) == m_id]
            signed_count = len(att_subset[att_subset["Status"] == "Signed"])
            
            title_str = f"{'🟢' if m.get('MeetingStatus')=='Open' else '🔴'} {str(m.get('MeetingDate')).replace('-','/')} | {m.get('MeetingName')} | {signed_count}/{len(att_subset)} Signed"

            with st.expander(title_str):
                r1, r2, r3 = st.columns([1, 1, 2])
                with r1:
                    if st.button(f"{'🔒 Close' if m.get('MeetingStatus')=='Open' else '🔓 Open'}", key=f"lock_{m_id}"):
                        ws = get_sheet_object("Meeting_Info")
                        # (Retry logic here is internal to connection.py)
                        all_v = ws.get_all_values()
                        idx = [i for i, r in enumerate(all_v) if safe_str(r[0]) == m_id]
                        if idx:
                            ws.update_cell(idx[0]+1, 6, "Close" if m.get('MeetingStatus')=="Open" else "Open")
                            refresh_all_data()
                            st.rerun()
                with r2:
                    m_url = f"https://{DEPLOYMENT_URL}/?mid={m_id}"
                    qr_bytes = generate_qr_card(m_url, str(m.get('MeetingName')), str(m.get('Location')), str(m.get('TimeRange')))
                    st.download_button("📥 Download QR", qr_bytes, f"QR_{m_id}.png", "image/png", key=f"qrdl_{m_id}")
                with r3:
                    pdf_key = f"pdf_{m_id}"
                    if pdf_key in st.session_state.pdf_cache:
                        st.download_button("📥 Download PDF", st.session_state.pdf_cache[pdf_key], f"Report_{m_id}.pdf", "application/pdf", key=f"dl_{m_id}")
                    else:
                        if st.button("📄 Generate PDF", key=f"gen_{m_id}"):
                            refresh_all_data()
                            # (PDF generation logic same as your working version)
                            # ... logic omitted for brevity, but keep yours intact ...
                            st.rerun()

        if not s_id and not s_date:
            if st.button("⬇️ Load 10 More Records", width="stretch"): # 🔥 WIDTH FIX
                st.session_state.meeting_limit += 10
                st.rerun()

    # ---- 👥 Employee Master ----
    elif menu == "👥 Employee Master":
        st.title("Employee Master")
        
        # 🔥 LOG FIX: Change width='stretch'
        edited_df = st.data_editor(st.session_state.df_master, num_rows="dynamic", width="stretch", height=600)
        
        if st.button("💾 Save Changes to Cloud", type="primary"):
            with st.spinner("Saving..."):
                ws = get_sheet_object("Employee_Master")
                ws.clear()
                ws.update([edited_df.columns.tolist()] + edited_df.values.tolist())
                refresh_all_data()
                st.success("✅ Saved!")
                st.rerun()
