import streamlit as st
import pandas as pd
import gspread
# Modern Auth Library
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

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
# Updated to your new deployment URL
DEPLOYMENT_URL = "skhesign-jnff8wr9fkhrp6jqpsvfsjh.streamlit.app"
ADMIN_KEY = st.secrets["general"]["admin_password"]  # Now using Secrets
DRIVE_FOLDER_ID = st.secrets["general"]["drive_folder_id"]

st.set_page_config(page_title="SKH E-Sign System", page_icon="✍️", layout="wide")

# ==============================================================================
# 1. CONNECTION (Modernized Auth)
# ==============================================================================
@st.cache_resource
def get_gcp_services():
    """Builds both Sheets and Drive services using modern auth."""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=[
            "https://spreadsheets.google.com/feeds", 
            "https://www.googleapis.com/auth/drive"
        ]
    )
    # Gspread for Sheets
    client_sheets = gspread.authorize(creds)
    # Build Drive API for Images
    service_drive = build('drive', 'v3', credentials=creds)
    
    return client_sheets, service_drive

def get_sheet_object(worksheet_name):
    client, _ = get_gcp_services()
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
# 2. DATA HANDLING
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
    return pd.DataFrame() 

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
    with st.spinner("🔄 Syncing All Databases..."):
        st.session_state.df_master = api_read_with_retry("Employee_Master")
        st.session_state.df_info = api_read_with_retry("Meeting_Info")
        st.session_state.df_att = api_read_with_retry("Meeting_Attendees")
        st.session_state.pdf_cache = {}

def refresh_attendees_only():
    st.session_state.df_att = api_read_with_retry("Meeting_Attendees")
    st.session_state.pdf_cache = {} 

def ensure_data_loaded():
    if (st.session_state.df_info is None or 
        st.session_state.df_att is None or 
        st.session_state.df_master is None or
        st.session_state.df_master.empty): 
        refresh_all_data()

# ==============================================================================
# 3. HELPERS
# ==============================================================================
def safe_str(val):
    return str(val).strip()

def safe_int(val, default=999):
    try: return int(float(val))
    except: return default

def map_dict_to_row(headers, data_dict):
    row = [''] * len(headers) 
    for key, value in data_dict.items():
        if key in headers:
            idx = headers.index(key)
            row[idx] = value
    return row

def generate_qr_card(url, m_name, m_loc, m_time):
    m_name, m_loc, m_time = str(m_name), str(m_loc), str(m_time)
    qr = qrcode.make(url).resize((350, 350))
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
    img.paste(qr, ((W - 350) // 2, current_h))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def download_image_from_drive(service, file_id):
    """Retrieves image from Drive for PDF generation."""
    try:
        request = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            _, done = downloader.next_chunk()
        fh.seek(0)
        return Image.open(fh)
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
# ROUTE A: SIGN-IN VIEW (Modified with Drive + st.status)
# ------------------------------------------------------------------------------
if mid_param:
    ensure_data_loaded()
    df_info = st.session_state.df_info
    meeting = df_info[df_info["MeetingID"].astype(str) == str(mid_param)]
    
    if meeting.empty:
        st.error(f"❌ Meeting ID {mid_param} not found.")
        if st.button("🔄 Reload Data"): refresh_all_data(); st.rerun()
    else:
        m = meeting.iloc[0]
        status_mtg = m.get('MeetingStatus', 'Open')
        st.title(f"{m.get('MeetingName', 'No Name')}")
        st.write(f"📍 **{m.get('Location', '')}** | 🕒 **{m.get('TimeRange', '')}**")
        st.divider()

        if status_mtg == "Close":
            st.error("⛔ This meeting is currently CLOSED."); st.stop()
        
        if "success_msg" in st.session_state:
            st.success(st.session_state["success_msg"])
            del st.session_state["success_msg"]

        df_att = st.session_state.df_att
        current_att = df_att[df_att["MeetingID"].astype(str) == str(mid_param)].copy()
        
        if "RankID" in current_att.columns:
            current_att["RankID_Int"] = current_att["RankID"].apply(lambda x: safe_int(x, 999))
            current_att = current_att.sort_values("RankID_Int")
        
        options = current_att.apply(lambda r: f"{'✅ ' if r.get('Status') == 'Signed' else '⬜ '}{r.get('AttendeeName')} ({r.get('JobTitle')})", axis=1).tolist()
        
        if "signer_select_index" not in st.session_state: st.session_state.signer_select_index = 0
            
        selection = st.selectbox("Select your name to sign:", ["-- Select --"] + options, 
                                 index=st.session_state.signer_select_index, key="signer_sb")
        
        if selection != "-- Select --":
            actual_name = selection.split(" (")[0].replace("✅ ", "").replace("⬜ ", "")
            st.write(f"Signing for: **{actual_name}**")
            
            with st.expander("📐 Adjust Pad Size"):
                col_s, col_r = st.columns([4, 1])
                with col_r:
                    if st.button("↺"): st.session_state.pad_size = 320; st.rerun()
                c_width = col_s.slider("Pad Scale (px)", 250, 800, st.session_state.pad_size, key="pad_size")
                c_height = int(c_width * 0.52)
            
            canvas = st_canvas(fill_color="white", stroke_width=5, stroke_color="black",
                               background_color="#FFFFFF", height=c_height, width=c_width, key=f"cv_{actual_name}")
            
            # --- SUBMIT LOGIC ---
            if st.button("Confirm Signature", type="primary"):
                if is_canvas_blank(canvas.image_data):
                    st.warning("⚠️ Please sign before confirming.")
                else:
                    with st.status("🚀 Processing Signature...", expanded=True) as status_ui:
                        try:
                            # 1. Image Prep
                            status_ui.write("🎨 Finalizing signature image...")
                            img = Image.fromarray(canvas.image_data.astype('uint8'), 'RGBA')
                            buffered = BytesIO()
                            img.save(buffered, format="PNG")
                            buffered.seek(0)

                            # 2. Drive Upload
                            status_ui.write("📤 Uploading to Google Drive...")
                            client_s, service_d = get_gcp_services()
                            file_meta = {
                                'name': f"{mid_param}_{actual_name}_{int(time.time())}.png",
                                'parents': [DRIVE_FOLDER_ID]
                            }
                            media = MediaIoBaseUpload(buffered, mimetype='image/png')
                            drive_file = service_d.files().create(body=file_meta, media_body=media, fields='id').execute()
                            file_id = drive_file.get('id')

                            # 3. Sheet Update
                            status_ui.write("📝 Updating Register...")
                            ws_att = get_sheet_object("Meeting_Attendees")
                            all_rows = ws_att.get_all_values()
                            headers = all_rows[0]
                            name_idx, mid_idx = headers.index("AttendeeName"), headers.index("MeetingID")
                            status_idx, sig_idx = headers.index("Status")+1, headers.index("SignatureBase64")+1

                            row_idx = -1
                            for i, r in enumerate(all_rows):
                                if i == 0: continue
                                if safe_str(r[name_idx]) == safe_str(actual_name) and safe_str(r[mid_idx]) == safe_str(mid_param):
                                    row_idx = i + 1; break
                            
                            if row_idx > 0:
                                ws_att.batch_update([
                                    {'range': gspread.utils.rowcol_to_a1(row_idx, status_idx), 'values': [['Signed']]},
                                    {'range': gspread.utils.rowcol_to_a1(row_idx, sig_idx), 'values': [[file_id]]}
                                ])
                                status_ui.update(label="✅ Attendance Recorded!", state="complete")
                                st.balloons()
                                refresh_attendees_only()
                                st.session_state["success_msg"] = f"✅ Saved: {actual_name}"
                                st.session_state.signer_select_index = 0
                                time.sleep(1); st.rerun()
                            else:
                                status_ui.update(label="❌ Error: Name not found", state="error")
                        except Exception as e:
                            st.error(f"Failed: {e}")

# ------------------------------------------------------------------------------
# ROUTE B: ADMIN (Modified PDF logic to download from Drive)
# ------------------------------------------------------------------------------
elif (admin_access_param == ADMIN_KEY) or st.session_state.is_admin:
    st.session_state.is_admin = True
    st.sidebar.title("Navigation")
    menu = st.sidebar.radio("Go to:", ["🗓️ Arrange Meeting", "🛡️ Meeting Control", "👥 Employee Master"])
    
    if st.sidebar.button("🔄 Refresh Data (Sync)"):
        refresh_all_data(); st.session_state.meeting_limit = 10; st.rerun()

    ensure_data_loaded()

    if menu == "🗓️ Arrange Meeting":
        st.title("Arrange New Meeting")
        df_master = st.session_state.df_master
        if df_master is None or df_master.empty:
            st.warning("⚠️ Connection unstable. Please refresh."); st.stop()

        if "created_meeting_data" not in st.session_state: st.session_state.created_meeting_data = None

        if st.session_state.created_meeting_data:
            lm = st.session_state.created_meeting_data
            st.success(f"🎉 Created ID: {lm['id']}")
            card_bytes = generate_qr_card(lm['url'], lm['name'], lm['loc'], lm['time'])
            st.image(card_bytes, width=250)
            st.download_button("📥 Download QR", card_bytes, f"QR_{lm['id']}.png", "image/png")
            if st.button("⬅️ Create Another"): st.session_state.created_meeting_data = None; st.rerun()
        else:
            col1, col2 = st.columns(2)
            name = col1.text_input("Meeting Name")
            loc = col2.text_input("Location")
            date = col1.date_input("Meeting Date")
            t_start = st.columns(2)[0].time_input("Start", value=datetime.strptime("12:00", "%H:%M").time())
            t_end = st.columns(2)[1].time_input("End", value=datetime.strptime("13:00", "%H:%M").time())
            
            depts = sorted(df_master["Department"].astype(str).unique().tolist()) if "Department" in df_master.columns else []
            sel_dept = st.multiselect("Filter by Department", depts)
            filtered_emp = df_master.copy()
            if sel_dept: filtered_emp = filtered_emp[filtered_emp["Department"].astype(str).isin(sel_dept)]
            if "RankID" in filtered_emp.columns:
                filtered_emp["RankID_Int"] = filtered_emp["RankID"].apply(lambda x: safe_int(x, 999))
                filtered_emp = filtered_emp.sort_values("RankID_Int")
            
            selected_names = st.multiselect("Attendees", filtered_emp["FullName"].tolist())

            if st.button("Create Meeting", type="primary", disabled=not (name and loc and selected_names)):
                with st.spinner("Creating..."):
                    df_info_live = st.session_state.df_info
                    new_id = int(pd.to_numeric(df_info_live["MeetingID"], errors='coerce').max() or 0) + 1
                    date_str = date.strftime('%Y/%m/%d')
                    time_range = f"{date_str} {t_start.strftime('%H:%M')}~{t_end.strftime('%H:%M')}"
                    
                    ws_info = get_sheet_object("Meeting_Info")
                    ws_info.append_row(map_dict_to_row(df_info_live.columns.tolist(), {
                        "MeetingID": new_id, "MeetingName": name, "MeetingDate": str(date), 
                        "Location": loc, "TimeRange": time_range, "MeetingStatus": "Open" 
                    }))
                    
                    ws_att = get_sheet_object("Meeting_Attendees")
                    att_cols = st.session_state.df_att.columns.tolist()
                    rows = [map_dict_to_row(att_cols, {
                        "AttendeeName": n, "JobTitle": df_master[df_master["FullName"]==n].iloc[0].get("JobTitle",""),
                        "MeetingID": new_id, "RankID": safe_int(df_master[df_master["FullName"]==n].iloc[0].get("RankID"), 999),
                        "Status": "Pending", "SignatureBase64": ""
                    }) for n in selected_names]
                    if rows: ws_att.append_rows(rows)
                    
                    refresh_all_data()
                    st.session_state.created_meeting_data = {
                        'id': new_id, 'name': name, 'loc': loc, 'time': time_range,
                        'url': f"https://{DEPLOYMENT_URL}/?mid={new_id}"
                    }
                    st.rerun()

    elif menu == "🛡️ Meeting Control":
        st.title("Meeting Control")
        df_info, df_att = st.session_state.df_info, st.session_state.df_att
        results = df_info.copy()
        results["d_obj"] = pd.to_datetime(results["MeetingDate"], errors='coerce').dt.date
        results = results.sort_values(by=["d_obj", "MeetingID"], ascending=[False, False]).drop_duplicates(subset=['MeetingID'])
        
        for _, m in results.head(st.session_state.meeting_limit).iterrows():
            m_id = str(m.get('MeetingID'))
            att_sub = df_att[df_att["MeetingID"].astype(str) == m_id]
            with st.expander(f"{'🟢' if m.get('MeetingStatus')=='Open' else '🔴'} {m.get('MeetingDate')} | {m.get('MeetingName')} | {len(att_sub[att_sub['Status']=='Signed'])}/{len(att_sub)}"):
                c1, c2, c3 = st.columns([1,1,2])
                if c1.button("Lock/Unlock", key=f"lk_{m_id}"):
                    ws = get_sheet_object("Meeting_Info")
                    all_v = ws.get_all_values()
                    idx = [i for i,r in enumerate(all_v) if r[0]==m_id][0]+1
                    ws.update_cell(idx, all_v[0].index("MeetingStatus")+1, "Close" if m.get('MeetingStatus')=="Open" else "Open")
                    refresh_all_data(); st.rerun()
                
                qr_b = generate_qr_card(f"https://{DEPLOYMENT_URL}/?mid={m_id}", m.get('MeetingName'), m.get('Location'), m.get('TimeRange'))
                c2.download_button("QR Card", qr_b, f"QR_{m_id}.png", key=f"q_{m_id}")

                if c3.button("📄 Generate PDF", key=f"pdf_{m_id}"):
                    with st.spinner("Fetching images and building PDF..."):
                        _, drive_service = get_gcp_services()
                        pdf = FPDF()
                        pdf.add_page()
                        pdf.add_font('CH', '', FONT_CH, uni=True)
                        pdf.set_font('CH', '', 24)
                        pdf.multi_cell(0, 12, f"{m.get('MeetingName')} 簽到表", align="C")
                        pdf.set_font_size(14)
                        pdf.cell(0, 10, f"時間：{m.get('TimeRange')}  地點：{m.get('Location')}", ln=True, align="C")
                        pdf.ln(5)
                        pdf.cell(80, 12, "出席人員", 1, 0, 'C')
                        pdf.cell(110, 12, "簽名", 1, 1, 'C')
                        
                        for i, row in att_sub.reset_index().iterrows():
                            pdf.cell(80, 25, str(row.get('AttendeeName')), 1, 0, 'C')
                            x, y = pdf.get_x(), pdf.get_y()
                            pdf.cell(110, 25, "", 1, 1)
                            
                            sig_val = str(row.get('SignatureBase64'))
                            if sig_val and len(sig_val) > 5:
                                # Detection: Is it a File ID or Base64?
                                img_obj = None
                                if "base64" in sig_val: # Backward compatibility
                                    img_obj = Image.open(BytesIO(base64.b64decode(sig_val.split(",")[1])))
                                else: # New logic: Drive File ID
                                    img_obj = download_image_from_drive(drive_service, sig_val)
                                
                                if img_obj:
                                    tmp = f"tmp_{m_id}_{i}.png"
                                    img_obj.save(tmp)
                                    pdf.image(tmp, x+35, y+4, h=17)
                                    os.remove(tmp)
                        
                        st.session_state.pdf_cache[f"pdf_{m_id}"] = bytes(pdf.output())
                        st.rerun()
                
                if f"pdf_{m_id}" in st.session_state.pdf_cache:
                    c3.download_button("📥 Download PDF", st.session_state.pdf_cache[f"pdf_{m_id}"], f"Report_{m_id}.pdf")

    elif menu == "👥 Employee Master":
        st.title("Employee Master")
        df_master = st.session_state.df_master
        if df_master is not None:
            edited = st.data_editor(df_master, num_rows="dynamic", use_container_width=True)
            if st.button("Save Changes"):
                ws = get_sheet_object("Employee_Master")
                ws.clear()
                ws.update([edited.columns.tolist()] + edited.values.tolist())
                refresh_all_data(); st.success("Saved!"); st.rerun()

else:
    st.error("⛔ Access Denied. Please scan a QR code or use the Admin link.")
    st.stop()
