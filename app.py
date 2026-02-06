import streamlit as st
import pandas as pd
import gspread
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

# --- CONFIGURATION FROM SECRETS ---
SHEET_NAME = "esign"
FONT_CH = "font_CH.ttf"
FONT_EN = "font_EN.ttf"
DEPLOYMENT_URL = "skhesign-jnff8wr9fkhrp6jqpsvfsjh.streamlit.app"
ADMIN_PASSWORD = st.secrets["general"]["admin_password"]
DRIVE_FOLDER_ID = st.secrets["general"]["drive_folder_id"]

st.set_page_config(page_title="SKH E-Sign System Pro", page_icon="✍️", layout="wide")

# ==============================================================================
# 1. CONNECTION (Modernized API)
# ==============================================================================
@st.cache_resource
def get_services():
    """Returns both Gspread client and Drive API service."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
    
    gc = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    
    return gc, drive_service

def get_sheet_object(worksheet_name):
    gc, _ = get_services()
    return gc.open(SHEET_NAME).worksheet(worksheet_name)

# ==============================================================================
# 2. DATA HANDLING
# ==============================================================================
def api_read_with_retry(worksheet_name):
    try:
        ws = get_sheet_object(worksheet_name)
        return pd.DataFrame(ws.get_all_records())
    except Exception as e:
        st.error(f"Data Read Error: {e}")
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
    with st.spinner("🔄 Syncing Databases..."):
        st.session_state.df_master = api_read_with_retry("Employee_Master")
        st.session_state.df_info = api_read_with_retry("Meeting_Info")
        st.session_state.df_att = api_read_with_retry("Meeting_Attendees")
        st.session_state.pdf_cache = {}

def refresh_attendees_only():
    st.session_state.df_att = api_read_with_retry("Meeting_Attendees")
    st.session_state.pdf_cache = {}

def ensure_data_loaded():
    if st.session_state.df_master is None or st.session_state.df_master.empty:
        refresh_all_data()

# ==============================================================================
# 3. HELPERS
# ==============================================================================
def safe_str(val): return str(val).strip()

def safe_int(val, default=999):
    try: return int(float(val))
    except: return default

def map_dict_to_row(headers, data_dict):
    row = [''] * len(headers) 
    for key, value in data_dict.items():
        if key in headers: row[headers.index(key)] = value
    return row

def generate_qr_card(url, m_name, m_loc, m_time):
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
    name_lines = wrapper.wrap(text=str(m_name))
    current_h = 60
    for line in name_lines:
        draw.text((W/2, current_h), line, fill="black", font=font_header, anchor="mm")
        current_h += 55 
    
    draw.multiline_text((W/2, current_h + 20), f"地點：{m_loc}\n時間：{m_time}", fill="black", font=font_body, anchor="ma", align="center")
    draw.text((W/2, current_h + 120), "會議簽到", fill="black", font=font_body, anchor="mm")
    img.paste(qr, ((W - 350) // 2, current_h + 150))
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def download_file_from_drive(file_id):
    """Downloads image from Drive by ID."""
    _, drive_service = get_services()
    try:
        request = drive_service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            _, done = downloader.next_chunk()
        return fh
    except Exception as e:
        return None

def is_canvas_blank(image_data):
    if image_data is None: return True
    return np.std(image_data) < 1.0

# ==============================================================================
# 4. ROUTING
# ==============================================================================
query_params = st.query_params
mid_param = query_params.get("mid", None)
admin_access_param = query_params.get("admin_access", None)

init_data()

# ------------------------------------------------------------------------------
# ROUTE A: SIGN-IN (MOBILE)
# ------------------------------------------------------------------------------
if mid_param:
    ensure_data_loaded()
    df_info = st.session_state.df_info
    meeting = df_info[df_info["MeetingID"].astype(str) == str(mid_param)]
    
    if meeting.empty:
        st.error(f"❌ Meeting ID {mid_param} not found.")
        if st.button("🔄 Reload"): refresh_all_data(); st.rerun()
    else:
        m = meeting.iloc[0]
        if m.get('MeetingStatus') == "Close":
            st.error("⛔ This meeting is currently CLOSED."); st.stop()
        
        st.title(f"{m.get('MeetingName')}")
        st.write(f"📍 {m.get('Location')} | 🕒 {m.get('TimeRange')}")
        st.divider()

        if "success_msg" in st.session_state:
            st.success(st.session_state["success_msg"])
            del st.session_state["success_msg"]

        df_att = st.session_state.df_att
        current_att = df_att[df_att["MeetingID"].astype(str) == str(mid_param)].copy()
        if "RankID" in current_att.columns:
            current_att["RankID_Int"] = current_att["RankID"].apply(lambda x: safe_int(x, 999))
            current_att = current_att.sort_values("RankID_Int")
        
        options = current_att.apply(lambda r: f"{'✅ ' if r.get('Status') == 'Signed' else '⬜ '}{r.get('AttendeeName')} ({r.get('JobTitle')})", axis=1).tolist()
        
        selection = st.selectbox("Select your name:", ["-- Select --"] + options, key="signer_sb")
        
        if selection != "-- Select --":
            actual_name = selection.split(" (")[0].replace("✅ ", "").replace("⬜ ", "")
            st.write(f"Signing for: **{actual_name}**")
            
            with st.expander("📐 Adjust Pad"):
                c_width = st.slider("Pad Scale", 250, 800, st.session_state.pad_size)
                c_height = int(c_width * 0.52)
            
            canvas = st_canvas(fill_color="white", stroke_width=4, stroke_color="black", height=c_height, width=c_width, key=f"canv_{actual_name}")
            
            if st.button("Confirm Signature", type="primary"):
                if is_canvas_blank(canvas.image_data):
                    st.warning("⚠️ Please sign first.")
                else:
                    with st.status("🚀 Processing Signature...", expanded=True) as status:
                        try:
                            # STEP 1: Upload to Drive
                            status.write("📤 Saving image to Google Drive...")
                            img = Image.fromarray(canvas.image_data.astype('uint8'), 'RGBA')
                            buf = BytesIO()
                            img.save(buf, format="PNG")
                            buf.seek(0)

                            _, drive_service = get_services()
                            file_meta = {'name': f"{mid_param}_{actual_name}.png", 'parents': [DRIVE_FOLDER_ID]}
                            media = MediaIoBaseUpload(buf, mimetype='image/png')
                            file = drive_service.files().create(body=file_meta, media_body=media, fields='id').execute()
                            file_id = file.get('id')

                            # STEP 2: Update Sheet
                            status.write("📝 Updating meeting register...")
                            ws_att = get_sheet_object("Meeting_Attendees")
                            all_data = ws_att.get_all_values()
                            headers = all_data[0]
                            row_idx = -1
                            for i, r in enumerate(all_data):
                                if i == 0: continue
                                if safe_str(r[headers.index("AttendeeName")]) == safe_str(actual_name) and \
                                   safe_str(r[headers.index("MeetingID")]) == safe_str(mid_param):
                                    row_idx = i + 1; break
                            
                            if row_idx > 0:
                                ws_att.update_cell(row_idx, headers.index("Status")+1, "Signed")
                                ws_att.update_cell(row_idx, headers.index("SignatureBase64")+1, file_id)
                                
                                status.update(label="✅ Success!", state="complete")
                                st.balloons()
                                st.session_state["success_msg"] = f"Done: {actual_name}"
                                refresh_attendees_only()
                                time.sleep(1); st.rerun()
                        except Exception as e:
                            status.update(label="❌ Failed", state="error")
                            st.error(f"Error: {e}")

# ------------------------------------------------------------------------------
# ROUTE B: ADMIN
# ------------------------------------------------------------------------------
elif (admin_access_param == ADMIN_PASSWORD) or st.session_state.is_admin:
    st.session_state.is_admin = True
    st.sidebar.title("Admin Panel")
    menu = st.sidebar.radio("Menu", ["🗓️ Arrange", "🛡️ Control", "👥 Employees"])
    
    if st.sidebar.button("🔄 Sync Cloud"): refresh_all_data(); st.rerun()

    ensure_data_loaded()

    if menu == "🗓️ Arrange":
        st.title("New Meeting")
        df_master = st.session_state.df_master
        
        c1, c2 = st.columns(2)
        name = c1.text_input("Meeting Name")
        loc = c2.text_input("Location")
        date = c1.date_input("Date")
        t_start = st.time_input("Start", value=datetime.strptime("09:00", "%H:%M").time())
        
        depts = sorted(df_master["Department"].unique().tolist())
        sel_dept = st.multiselect("Filter Dept", depts)
        
        filtered = df_master[df_master["Department"].isin(sel_dept)] if sel_dept else df_master
        selected_names = st.multiselect("Attendees", filtered["FullName"].tolist())

        if st.button("Create Meeting", type="primary") and name and selected_names:
            ws_info = get_sheet_object("Meeting_Info")
            new_id = int(pd.to_numeric(st.session_state.df_info["MeetingID"], errors='coerce').max() or 0) + 1
            
            ws_info.append_row(map_dict_to_row(st.session_state.df_info.columns.tolist(), {
                "MeetingID": new_id, "MeetingName": name, "MeetingDate": str(date), 
                "Location": loc, "TimeRange": f"{date} {t_start}", "MeetingStatus": "Open"
            }))
            
            rows = []
            for n in selected_names:
                emp = df_master[df_master["FullName"] == n].iloc[0]
                rows.append(map_dict_to_row(st.session_state.df_att.columns.tolist(), {
                    "AttendeeName": n, "JobTitle": emp.get("JobTitle"), "MeetingID": new_id, 
                    "RankID": emp.get("RankID"), "Status": "Pending"
                }))
            get_sheet_object("Meeting_Attendees").append_rows(rows)
            refresh_all_data(); st.success("Created!"); st.rerun()

    elif menu == "🛡️ Control":
        st.title("Meeting History")
        df_info = st.session_state.df_info
        df_att = st.session_state.df_att
        
        for _, m in df_info.sort_values("MeetingID", ascending=False).head(st.session_state.meeting_limit).iterrows():
            m_id = str(m['MeetingID'])
            att_sub = df_att[df_att["MeetingID"].astype(str) == m_id]
            
            with st.expander(f"{m['MeetingDate']} | {m['MeetingName']} ({len(att_sub[att_sub['Status']=='Signed'])}/{len(att_sub)})"):
                c1, c2, c3 = st.columns(3)
                if c1.button("Toggle Lock", key=f"lock_{m_id}"):
                    new_s = "Close" if m['MeetingStatus'] == "Open" else "Open"
                    ws = get_sheet_object("Meeting_Info")
                    cell = ws.find(m_id)
                    ws.update_cell(cell.row, ws.find("MeetingStatus").col, new_s)
                    refresh_all_data(); st.rerun()
                
                qr_bytes = generate_qr_card(f"https://{DEPLOYMENT_URL}/?mid={m_id}", m['MeetingName'], m['Location'], m['TimeRange'])
                c2.download_button("📥 QR Code", qr_bytes, f"QR_{m_id}.png", "image/png")

                if c3.button("📄 Generate PDF", key=f"pdf_{m_id}"):
                    with st.spinner("Downloading images and building PDF..."):
                        pdf = FPDF()
                        pdf.add_page()
                        pdf.add_font('CH', '', FONT_CH, uni=True)
                        pdf.set_font('CH', '', 20)
                        pdf.cell(0, 10, f"{m['MeetingName']} 簽到表", ln=True, align='C')
                        pdf.set_font_size(12)
                        pdf.cell(0, 10, f"時間: {m['TimeRange']} | 地點: {m['Location']}", ln=True, align='C')
                        pdf.ln(5)
                        
                        pdf.cell(80, 10, "姓名", 1, 0, 'C')
                        pdf.cell(100, 10, "簽名", 1, 1, 'C')
                        
                        for i, row in att_sub.iterrows():
                            pdf.cell(80, 20, str(row['AttendeeName']), 1, 0, 'C')
                            x, y = pdf.get_x(), pdf.get_y()
                            pdf.cell(100, 20, "", 1, 1)
                            
                            file_id = row.get('SignatureBase64')
                            if file_id and len(str(file_id)) > 5:
                                img_bytes = download_file_from_drive(file_id)
                                if img_bytes:
                                    img_bytes.seek(0)
                                    tmp_path = f"tmp_{file_id}.png"
                                    with open(tmp_path, "wb") as f: f.write(img_bytes.read())
                                    pdf.image(tmp_path, x+30, y+2, h=15)
                                    os.remove(tmp_path)
                        
                        st.download_button("📥 Download PDF", pdf.output(dest='S'), f"Report_{m_id}.pdf", "application/pdf")

    elif menu == "👥 Employees":
        st.title("Employee Master")
        edited = st.data_editor(st.session_state.df_master, num_rows="dynamic", use_container_width=True)
        if st.button("Save Changes"):
            ws = get_sheet_object("Employee_Master")
            ws.clear()
            ws.update([edited.columns.tolist()] + edited.values.tolist())
            refresh_all_data(); st.success("Saved!")

else:
    st.error("⛔ Access Denied. Use a QR code or Admin credentials.")
