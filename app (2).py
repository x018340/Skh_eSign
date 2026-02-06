import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_drawable_canvas import st_canvas
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from fpdf import FPDF
import qrcode
from datetime import datetime
import numpy as np
import os
import time
import random
import textwrap

# --- CONFIGURATION ---
SHEET_NAME = "esign"
FONT_CH = "font_CH.ttf"
FONT_EN = "font_EN.ttf"
DEPLOYMENT_URL = "zvjyaxns2ktjdrlzt7y3u8.streamlit.app"
ADMIN_KEY = "SKH_DIM"  # 🔐 The Secret Key

st.set_page_config(page_title="SKH E-Sign System", page_icon="✍️", layout="wide")

# ==============================================================================
# 1. CONNECTION (Cached Resource)
# ==============================================================================
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def get_sheet_object(worksheet_name):
    client = get_gspread_client()
    retries = 3
    for i in range(retries):
        try:
            return client.open(SHEET_NAME).worksheet(worksheet_name)
        except gspread.exceptions.APIError as e:
            if "429" in str(e):
                time.sleep(2 + i)
            elif i == retries - 1:
                raise e
            else:
                time.sleep(1)
    return client.open(SHEET_NAME).worksheet(worksheet_name)

# ==============================================================================
# 2. DATA HANDLING (Session State)
# ==============================================================================

def api_read_with_retry(worksheet_name):
    try:
        ws = get_sheet_object(worksheet_name)
        retries = 5
        for i in range(retries):
            try:
                data = ws.get_all_records()
                return pd.DataFrame(data)
            except gspread.exceptions.APIError as e:
                if "429" in str(e):
                    time.sleep((i + 1) * 2)
                elif i == retries - 1:
                    raise e
                else:
                    time.sleep(1)
    except Exception:
        pass
    return pd.DataFrame() # Return empty on total failure to prevent NoneType crash

def init_data():
    if "df_master" not in st.session_state: st.session_state.df_master = None
    if "df_info" not in st.session_state: st.session_state.df_info = None
    if "df_att" not in st.session_state: st.session_state.df_att = None
    if "processing_sign" not in st.session_state: st.session_state.processing_sign = False
    if "pdf_cache" not in st.session_state: st.session_state.pdf_cache = {}
    if "meeting_limit" not in st.session_state: st.session_state.meeting_limit = 10
    if "pad_size" not in st.session_state: st.session_state.pad_size = 320
    if "is_admin" not in st.session_state: st.session_state.is_admin = False

def refresh_all_data():
    """Heavy refresh: Downloads EVERYTHING."""
    with st.spinner("🔄 Syncing All Databases..."):
        st.session_state.df_master = api_read_with_retry("Employee_Master")
        st.session_state.df_info = api_read_with_retry("Meeting_Info")
        st.session_state.df_att = api_read_with_retry("Meeting_Attendees")
        st.session_state.pdf_cache = {}

def refresh_attendees_only():
    """Light refresh: Only downloads Attendees (saves 66% API calls)."""
    st.session_state.df_att = api_read_with_retry("Meeting_Attendees")
    st.session_state.pdf_cache = {} # Must clear cache because signatures changed

def ensure_data_loaded():
    if (st.session_state.df_info is None or 
        st.session_state.df_att is None or 
        st.session_state.df_master is None or
        st.session_state.df_master.empty): # Added check for empty
        refresh_all_data()

# ==============================================================================
# 3. HELPERS
# ==============================================================================
def safe_str(val):
    return str(val).strip()

def safe_int(val, default=999):
    try:
        return int(float(val))
    except:
        return default

def map_dict_to_row(headers, data_dict):
    row = [''] * len(headers) 
    for key, value in data_dict.items():
        if key in headers:
            idx = headers.index(key)
            row[idx] = value
    return row

def generate_qr_card(url, m_name, m_loc, m_time):
    m_name = str(m_name)
    m_loc = str(m_loc)
    m_time = str(m_time)
    qr = qrcode.make(url)
    qr = qr.resize((350, 350))
    W, H = 600, 850 
    img = Image.new('RGB', (W, H), 'white')
    draw = ImageDraw.Draw(img)
    try:
        font_header = ImageFont.truetype(FONT_CH, 40)
        font_body = ImageFont.truetype(FONT_CH, 22)
    except:
        font_header = ImageFont.load_default()
        font_body = ImageFont.load_default()

    wrapper = textwrap.TextWrapper(width=14) 
    name_lines = wrapper.wrap(text=m_name)
    current_h = 60
    for line in name_lines:
        draw.text((W/2, current_h), line, fill="black", font=font_header, anchor="mm")
        current_h += 55 
    
    current_h += 20 
    info_text = f"地點：{m_loc}\n時間：{m_time}"
    draw.multiline_text((W/2, current_h), info_text, fill="black", font=font_body, anchor="ma", align="center")
    
    current_h += 100 
    draw.text((W/2, current_h), "會議簽到", fill="black", font=font_body, anchor="mm")
    
    current_h += 30 
    qr_x = (W - 350) // 2 
    img.paste(qr, (qr_x, current_h))
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def base64_to_image(base64_str):
    try:
        if not base64_str: return None
        if "," in base64_str: header, encoded = base64_str.split(",", 1)
        else: encoded = base64_str
        data = base64.b64decode(encoded)
        return Image.open(BytesIO(data))
    except:
        return None

def is_canvas_blank(image_data):
    if image_data is None: return True
    return np.std(image_data) < 1.0

# ==============================================================================
# 4. LOGIC START
# ==============================================================================
query_params = st.query_params
mid_param = query_params.get("mid", None)
admin_access_param = query_params.get("admin_access", None)

init_data()

# ------------------------------------------------------------------------------
# ROUTE A: SIGN-IN VIEW (Mobile/Public)
# ------------------------------------------------------------------------------
if mid_param:
    ensure_data_loaded()
    df_info = st.session_state.df_info
    
    meeting = df_info[df_info["MeetingID"].astype(str) == str(mid_param)]
    
    if meeting.empty:
        st.error(f"❌ Meeting ID {mid_param} not found.")
        if st.button("🔄 Reload Data"):
            refresh_all_data()
            st.rerun()
    else:
        m = meeting.iloc[0]
        status = m.get('MeetingStatus', 'Open')
        
        st.title(f"{m.get('MeetingName', 'No Name')}")
        st.write(f"📍 **{m.get('Location', '')}**")
        st.write(f"🕒 **{m.get('TimeRange', '')}**")
        st.divider()

        if status == "Close":
            st.error("⛔ This meeting is currently CLOSED.")
            st.stop()
        
        if "success_msg" in st.session_state:
            st.success(st.session_state["success_msg"])
            del st.session_state["success_msg"]

        df_att = st.session_state.df_att
        current_att = df_att[df_att["MeetingID"].astype(str) == str(mid_param)].copy()
        
        if "RankID" in current_att.columns:
            current_att["RankID_Int"] = current_att["RankID"].apply(lambda x: safe_int(x, 999))
            current_att = current_att.sort_values("RankID_Int")
        
        def fmt(row):
            status = "✅ " if row.get('Status') == "Signed" else "⬜ "
            return f"{status}{row.get('AttendeeName')} ({row.get('JobTitle')})"
        
        options = current_att.apply(fmt, axis=1).tolist()
        
        if "signer_select_index" not in st.session_state:
            st.session_state.signer_select_index = 0
            
        selection = st.selectbox(
            "Select your name to sign:", 
            ["-- Select --"] + options,
            index=st.session_state.signer_select_index,
            key="signer_sb"
        )
        
        if selection != "-- Select --":
            actual_name = selection.split(" (")[0].replace("✅ ", "").replace("⬜ ", "")
            st.write(f"Signing for: **{actual_name}**")
            
            with st.expander("📐 Adjust Pad Size"):
                col_s, col_r = st.columns([4, 1])
                with col_r:
                    if st.button("↺", help="Reset to 320px"):
                        st.session_state.pad_size = 320
                        st.rerun()
                with col_s:
                    c_width = st.slider("Pad Scale (px)", 250, 800, st.session_state.pad_size, key="pad_size")
                c_height = int(c_width * 0.52)
            
            canvas = st_canvas(
                fill_color="white", 
                stroke_width=5,
                stroke_color="black",
                background_color="#FFFFFF",
                height=c_height, 
                width=c_width, 
                key=f"canvas_{actual_name}_{c_width}"
            )
            
            if st.session_state.processing_sign:
                st.button("⏳ Saving... Please Wait", disabled=True)
            else:
                if st.button("Confirm Signature"):
                    if is_canvas_blank(canvas.image_data):
                        st.warning("⚠️ Please sign on the pad before confirming.")
                    else:
                        st.session_state.processing_sign = True
                        st.rerun() 

            # --- SIGNATURE SAVING LOGIC (With 10 Retries) ---
            if st.session_state.processing_sign:
                try:
                    img = Image.fromarray(canvas.image_data.astype('uint8'), 'RGBA')
                    buffered = BytesIO()
                    img.save(buffered, format="PNG")
                    img_str = base64.b64encode(buffered.getvalue()).decode()
                    full_base64 = f"data:image/png;base64,{img_str}"
                    
                    ws_attendees = get_sheet_object("Meeting_Attendees")
                    all_rows = ws_attendees.get_all_values()
                    headers = all_rows[0]
                    name_idx = headers.index("AttendeeName")
                    mid_idx = headers.index("MeetingID")
                    status_idx = headers.index("Status") + 1
                    sig_idx = headers.index("SignatureBase64") + 1

                    row_update_idx = -1
                    for i, r in enumerate(all_rows):
                        if i == 0: continue
                        if safe_str(r[name_idx]) == safe_str(actual_name) and safe_str(r[mid_idx]) == safe_str(mid_param):
                            row_update_idx = i + 1
                            break
                    
                    if row_update_idx > 0:
                        # 🔥 10 RETRIES LOGIC START
                        retries = 10
                        for i in range(retries):
                            try:
                                ws_attendees.batch_update([
                                    {'range': gspread.utils.rowcol_to_a1(row_update_idx, status_idx), 'values': [['Signed']]},
                                    {'range': gspread.utils.rowcol_to_a1(row_update_idx, sig_idx), 'values': [[full_base64]]}
                                ])
                                break # Success!
                            except gspread.exceptions.APIError as e:
                                if i == retries - 1: raise e # Crash only on last try
                                time.sleep(2 + i) # Wait 2s, 3s, 4s...
                        # 🔥 10 RETRIES LOGIC END

                        # 🔥 OPTIMIZATION: Only refresh attendees
                        refresh_attendees_only()
                        st.session_state["success_msg"] = f"✅ Saved: {actual_name}"
                        st.session_state.signer_select_index = 0
                    else:
                        st.error("Record not found on server.")
                except Exception as e:
                    st.error(f"Save Failed (Server Busy). Try again later. ({e})")
                finally:
                    st.session_state.processing_sign = False 
                    st.rerun()

# ------------------------------------------------------------------------------
# ROUTE B: ADMIN (Protected)
# ------------------------------------------------------------------------------
elif (admin_access_param == ADMIN_KEY) or st.session_state.is_admin:
    st.session_state.is_admin = True
    
    st.sidebar.title("Navigation")
    menu = st.sidebar.radio("Go to:", ["🗓️ Arrange Meeting", "🛡️ Meeting Control", "👥 Employee Master"])
    
    st.sidebar.divider()
    if st.sidebar.button("🔄 Refresh Data (Sync)"):
        refresh_all_data()
        st.session_state.meeting_limit = 10 
        st.sidebar.success("Updated!")
        time.sleep(1)
        st.rerun()

    ensure_data_loaded()

    # --- 1. ARRANGE MEETING ---
    if menu == "🗓️ Arrange Meeting":
        st.title("Arrange New Meeting")
        
        # 🔥 CRASH PREVENTION: Check if Master Data exists
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
                    if st.button(f"{'🔒 Close' if status=='Open' else '🔓 Open'}", key=f"btn_lock_{m_id}"):
                        new_status = "Close" if status == "Open" else "Open"
                        try:
                            # 1. Get Sheet with Retry
                            ws_info = get_sheet_object("Meeting_Info")
                            
                            # 2. Get Values with Manual Retry
                            all_vals = []
                            for i in range(3):
                                try:
                                    all_vals = ws_info.get_all_values()
                                    break
                                except gspread.exceptions.APIError as e:
                                    if "429" in str(e): time.sleep(2)
                                    elif i == 2: raise e
                            
                            headers = all_vals[0]
                            id_idx = headers.index("MeetingID")
                            status_idx = headers.index("MeetingStatus") + 1
                            
                            row_idx = -1
                            for i, r in enumerate(all_vals):
                                if i==0: continue
                                if safe_str(r[id_idx]) == m_id:
                                    row_idx = i + 1
                                    break
                            
                            if row_idx > 0:
                                # 3. Update with Manual Retry
                                for i in range(3):
                                    try:
                                        ws_info.update_cell(row_idx, status_idx, new_status)
                                        break
                                    except gspread.exceptions.APIError as e:
                                        if "429" in str(e): time.sleep(2)
                                        elif i == 2: raise e
                                        
                                refresh_all_data()
                                st.rerun()
                        except Exception as e:
                            st.error(f"Operation failed due to connection: {e}")

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
                        
                        st.download_button(
                            "📥 Download PDF", 
                            st.session_state.pdf_cache[pdf_key], 
                            fname, 
                            "application/pdf",
                            key=f"dl_{m_id}"
                        )
                    else:
                        if st.button("📄 Generate PDF", key=f"gen_{m_id}"):
                            refresh_all_data() 
                            fresh_info = st.session_state.df_info
                            fresh_att = st.session_state.df_att
                            
                            fresh_m_list = fresh_info[fresh_info["MeetingID"].astype(str) == m_id]
                            if fresh_m_list.empty:
                                st.error("Sync Error. Try again.")
                                st.stop()
                            fresh_m = fresh_m_list.iloc[0]
                            fresh_att_subset = fresh_att[fresh_att["MeetingID"].astype(str) == m_id]

                            with st.spinner("Generating..."):
                                if "RankID" in fresh_att_subset.columns:
                                    fresh_att_subset["RankID_Int"] = fresh_att_subset["RankID"].apply(lambda x: safe_int(x, 999))
                                    fresh_att_subset = fresh_att_subset.sort_values("RankID_Int")
                                
                                pdf = FPDF()
                                pdf.add_page()
                                pdf.add_font('CustomFont', '', FONT_CH, uni=True)
                                pdf.set_font('CustomFont', '', 24)
                                
                                # FIX: PDF Title Wrapping
                                pdf.multi_cell(w=0, h=12, txt=f"{fresh_m.get('MeetingName')}簽到", align="C")
                                pdf.set_x(10)
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
                                            tmp_name = f"tmp_{m_id}_{i}_{random.randint(1000,9999)}.png"
                                            img.save(tmp_name)
                                            pdf.image(tmp_name, x+35, y+4, h=17)
                                            try: os.remove(tmp_name)
                                            except: pass
                                
                                st.session_state.pdf_cache[pdf_key] = bytes(pdf.output())
                                st.rerun()
        
        if not s_id and not s_date:
            st.divider()
            if st.button("⬇️ Load 10 More Records", type="secondary", use_container_width=True):
                st.session_state.meeting_limit += 10
                st.rerun()

    # --- 3. EMPLOYEE MASTER ---
    elif menu == "👥 Employee Master":
        st.title("Employee Master")
        
        # FIX: Check if Master Data Exists
        df_master = st.session_state.df_master
        if df_master is None or df_master.empty or "FullName" not in df_master.columns:
            st.warning("⚠️ Database connection unstable or empty. Please click Refresh.")
            if st.button("🔄 Retry Connection"):
                refresh_all_data()
                st.rerun()
            st.stop()
        
        with st.expander("➕ Add New Employee", expanded=False):
            with st.form("add_emp"):
                c1, c2 = st.columns(2)
                new_rank = c1.number_input("Rank ID", min_value=1, step=1, value=99)
                new_name_input = c2.text_input("Full Name")
                new_job_input = c1.text_input("Job Title")
                new_dept_input = c2.text_input("Department")
                
                if st.form_submit_button("Add to Master"):
                    if new_name_input and new_dept_input:
                        try:
                            ws_master = get_sheet_object("Employee_Master")
                            headers = st.session_state.df_master.columns.tolist()
                            row = map_dict_to_row(headers, {
                                "RankID": int(new_rank), "FullName": new_name_input,
                                "JobTitle": new_job_input, "Department": new_dept_input
                            })
                            ws_master.append_row(row)
                            refresh_all_data()
                            st.success(f"Added {new_name_input}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error adding employee: {e}")
        
        st.divider()
        st.write("### ✏️ Edit Employee Data")
        
        if st.session_state.df_master is not None:
            edited_df = st.data_editor(
                st.session_state.df_master, 
                num_rows="dynamic",
                use_container_width=True,
                height=600
            )
            
            if st.button("💾 Save Changes to Cloud", type="primary"):
                with st.spinner("Saving changes to Google Sheets..."):
                    try:
                        ws_master = get_sheet_object("Employee_Master")
                        ws_master.clear()
                        data_to_upload = [edited_df.columns.tolist()] + edited_df.values.tolist()
                        ws_master.update(data_to_upload)
                        refresh_all_data()
                        st.success("✅ Changes saved successfully!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Save failed: {e}")

# ------------------------------------------------------------------------------
# ROUTE C: ACCESS DENIED (No ID + No Admin Key)
# ------------------------------------------------------------------------------
else:
    st.error("⛔ Access Denied. Please scan a valid meeting QR code or use the Admin link.")
    st.stop()

