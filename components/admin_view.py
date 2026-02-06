import streamlit as st
import pandas as pd
import time
import random
from datetime import datetime
from config import DEPLOYMENT_URL
from utils import map_dict_to_row, safe_int
from core.state import refresh_all_data
from services.data_service import get_sheet_object
from services.pdf_service import generate_qr_card, create_attendance_pdf

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

    # 1. ARRANGE MEETING
    if menu == "🗓️ Arrange Meeting":
        st.title("Arrange New Meeting")
        df_master = st.session_state.df_master
        
        if df_master is None or df_master.empty:
            st.warning("⚠️ Database connection unstable. Please click Refresh.")
            return

        # Success Screen after creation
        if "created_meeting_data" in st.session_state and st.session_state.created_meeting_data:
            lm = st.session_state.created_meeting_data
            st.success(f"🎉 Meeting Created: **{lm['name']}** (ID: {lm['id']})")
            card_bytes = generate_qr_card(lm['url'], lm['name'], lm['loc'], lm['time'])
            
            c1, c2 = st.columns(2)
            with c1: st.image(card_bytes, caption="Preview", width=250)
            with c2:
                st.download_button("📥 Download QR Card", card_bytes, f"QR_{lm['id']}.png", "image/png", type="primary")
                if st.button("⬅️ Create Another"):
                    st.session_state.created_meeting_data = None
                    st.rerun()
            return

        # Input Form
        col1, col2 = st.columns(2)
        name = col1.text_input("Meeting Name")
        loc = col2.text_input("Location")
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
        
        selected_names = st.multiselect("Attendees", filtered_emp["FullName"].tolist())

        if st.button("Create Meeting & Generate QR", type="primary", disabled=not (name and selected_names)):
            with st.spinner("Creating..."):
                df_info_live = st.session_state.df_info
                max_id = int(pd.to_numeric(df_info_live["MeetingID"], errors='coerce').max() or 0)
                new_id = max_id + 1
                
                date_str = date.strftime('%Y/%m/%d')
                time_range = f"{date_str} {t_start.strftime('%H:%M')}~{t_end.strftime('%H:%M')}"
                
                # Update Meeting Info
                ws_info = get_sheet_object("Meeting_Info")
                ws_info.append_row(map_dict_to_row(df_info_live.columns.tolist(), {
                    "MeetingID": new_id, "MeetingName": name, "MeetingDate": str(date), 
                    "Location": loc, "TimeRange": time_range, "MeetingStatus": "Open"
                }))
                
                # Update Attendees
                ws_att = get_sheet_object("Meeting_Attendees")
                att_cols = st.session_state.df_att.columns.tolist()
                rows = []
                for n in selected_names:
                    emp = df_master[df_master["FullName"] == n].iloc[0]
                    rows.append(map_dict_to_row(att_cols, {
                        "AttendeeName": n, "JobTitle": emp.get("JobTitle",""),
                        "MeetingID": new_id, "RankID": safe_int(emp.get("RankID"), 999), 
                        "Status": "Pending", "SignatureBase64": ""
                    }))
                if rows: ws_att.append_rows(rows)
                
                refresh_all_data()
                st.session_state.created_meeting_data = {
                    'id': new_id, 'name': name, 'loc': loc, 'time': time_range,
                    'url': f"https://{DEPLOYMENT_URL}/?mid={new_id}"
                }
                st.rerun()

    # 2. MEETING CONTROL
    elif menu == "🛡️ Meeting Control":
        st.title("Meeting Control")
        df_info = st.session_state.df_info
        df_att = st.session_state.df_att
        
        c1, c2 = st.columns(2)
        s_id = c1.text_input("ID Filter")
        s_date = c2.date_input("Date Filter", value=None)
        
        results = df_info.copy()
        results["d_obj"] = pd.to_datetime(results["MeetingDate"], errors='coerce').dt.date
        results = results.sort_values(by=["d_obj", "MeetingID"], ascending=[False, False])
        
        if s_id: results = results[results["MeetingID"].astype(str) == s_id]
        if s_date: results = results[results["d_obj"] == s_date]

        display_results = results.head(st.session_state.meeting_limit)

        for _, m in display_results.iterrows():
            m_id = str(m.get('MeetingID'))
            status = m.get('MeetingStatus', 'Open')
            att_subset = df_att[df_att["MeetingID"].astype(str) == m_id]
            signed_count = len(att_subset[att_subset["Status"] == "Signed"])
            
            with st.expander(f"{'🟢' if status=='Open' else '🔴'} {m.get('MeetingDate')} | {m.get('MeetingName')} ({signed_count}/{len(att_subset)})"):
                r1, r2, r3 = st.columns([1, 1, 2])
                
                with r1: # Toggle Status
                    if st.button(f"{'🔒 Close' if status=='Open' else '🔓 Open'}", key=f"lock_{m_id}"):
                        ws_info = get_sheet_object("Meeting_Info")
                        all_v = ws_info.get_all_values()
                        idx = [i for i, r in enumerate(all_v) if r[0] == m_id][0] + 1
                        ws_info.update_cell(idx, all_v[0].index("MeetingStatus")+1, "Close" if status=="Open" else "Open")
                        refresh_all_data()
                        st.rerun()

                with r2: # Download QR
                    m_url = f"https://{DEPLOYMENT_URL}/?mid={m_id}"
                    qr_b = generate_qr_card(m_url, m.get('MeetingName'), m.get('Location'), m.get('TimeRange'))
                    st.download_button("📥 QR", qr_b, f"QR_{m_id}.png", key=f"qrdl_{m_id}")

                with r3: # PDF
                    if st.button("📄 Generate PDF", key=f"gen_{m_id}"):
                        pdf_bytes = create_attendance_pdf(m, att_subset)
                        st.session_state.pdf_cache[f"pdf_{m_id}"] = pdf_bytes
                        st.rerun()
                    
                    if f"pdf_{m_id}" in st.session_state.pdf_cache:
                        st.download_button("📥 Download PDF", st.session_state.pdf_cache[f"pdf_{m_id}"], f"Report_{m_id}.pdf", key=f"dl_{m_id}")
        
        if st.button("Load More"):
            st.session_state.meeting_limit += 10
            st.rerun()

    # 3. EMPLOYEE MASTER
    elif menu == "👥 Employee Master":
        st.title("Employee Master")
        df_master = st.session_state.df_master
        
        with st.expander("➕ Add New Employee"):
            with st.form("add_emp"):
                c1, c2 = st.columns(2)
                r = c1.number_input("Rank ID", value=99)
                n = c2.text_input("Name")
                j = c1.text_input("Job Title")
                d = c2.text_input("Department")
                if st.form_submit_button("Add"):
                    ws = get_sheet_object("Employee_Master")
                    ws.append_row(map_dict_to_row(df_master.columns.tolist(), {"RankID": r, "FullName": n, "JobTitle": j, "Department": d}))
                    refresh_all_data()
                    st.rerun()
        
        edited_df = st.data_editor(df_master, num_rows="dynamic", use_container_width=True)
        if st.button("💾 Save Changes"):
            ws = get_sheet_object("Employee_Master")
            ws.clear()
            ws.update([edited_df.columns.tolist()] + edited_df.values.tolist())
            refresh_all_data()
            st.success("Saved!")
