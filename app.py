import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
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
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

# --- CONFIGURATION ---
SHEET_NAME = "esign"
FONT_CH = "font_CH.ttf"  # Ensure this file exists in your repo
FONT_EN = "font_EN.ttf"  # Ensure this file exists in your repo
DEPLOYMENT_URL = "skhesign-jnff8wr9fkhrp6jqpsvfsjh.streamlit.app" # New URL

st.set_page_config(page_title="SKH E-Sign System", page_icon="✍️", layout="wide")

# ==============================================================================
# 1. CONNECTION & SERVICES (Refactored for Drive + Modern Auth)
# ==============================================================================

# Retry strategy: Try 3 times, wait 2 seconds between tries if API fails
retry_api = retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    retry=retry_if_exception_type((gspread.exceptions.APIError, Exception))
)

@st.cache_resource
def get_services():
    """
    Initializes connections to Google Sheets and Google Drive 
    using the modern google.oauth2 library.
    """
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Load secrets
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    # Create Credentials object
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    
    # 1. Sheets Client
    client_sheets = gspread.authorize(creds)
    
    # 2. Drive Client
    service_drive = build('drive', 'v3', credentials=creds)
    
    return client_sheets, service_drive

def get_sheet_object(worksheet_name):
    client, _ = get_services()
    return client.open(SHEET_NAME).worksheet(worksheet_name)

# ==============================================================================
# 2. DRIVE HELPERS (New Logic)
# ==============================================================================

def upload_signature_to_drive(image_data, filename):
    """
    Uploads a PNG byte stream to Google Drive.
    Returns the File ID.
    """
    _, drive_service = get_services()
    folder_id = st.secrets["general"]["drive_folder_id"]
    
    metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    
    media = MediaIoBaseUpload(image_data, mimetype='image/png')
    
    file = drive_service.files().create(
        body=metadata,
        media_body=media,
        fields='id'
    ).execute()
    
    return file.get('id')

def download_image_from_drive(file_id):
    """
    Downloads an image by ID from Google Drive.
    Returns BytesIO object.
    """
    try:
        _, drive_service = get_services()
        request = drive_service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return fh
    except Exception as e:
        print(f"Error downloading {file_id}: {e}")
        return None

# ==============================================================================
# 3. DATA HANDLING
# ==============================================================================

@retry_api
def api_read_safe(worksheet_name):
    ws = get_sheet_object(worksheet_name)
    data = ws.get_all_records()
    return pd.DataFrame(data)

def init_data():
    if "df_master" not in st.session_state: st.session_state.df_master = None
    if "df_info" not in st.session_state: st.session_state.df_info = None
    if "df_att" not in st.session_state: st.session_state.df_att = None
    if "pdf_cache" not in st.session_state: st.session_state.pdf_cache = {}
    if "meeting_limit" not in st.session_state: st.session_state.meeting_limit = 10
    if "pad_size" not in st.session_state: st.session_state.pad_size = 320
    if "is_admin" not in st.session_state: st.session_state.is_admin = False

def refresh_all_data():
    with st.spinner("🔄 Syncing Database..."):
        st.session_state.df_master = api_read_safe("Employee_Master")
        st.session_state.df_info = api_read_safe("Meeting_Info")
        st.session_state.df_att = api_read_safe("Meeting_Attendees")
        st.session_state.pdf_cache = {}

def refresh_attendees_only():
    st.session_state.df_att = api_read_safe("Meeting_Attendees")
    st.session_state.pdf_cache = {}

def ensure_data_loaded():
    if (st.session_state.df_info is None or 
        st.session_state.df_att is None or 
        st.session_state.df_master is None):
        refresh_all_data()

# ==============================================================================
# 4. UTILS (QR, Layout, Validation)
# ==============================================================================

def safe_str(val): return str(val).strip()
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
    # (Same as your original code)
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
    draw.multiline_text((W/2, current_h), f"地點：{m_loc}\n時間：{m_time}", fill="black", font=font_body, anchor="ma", align="center")
    current_h += 100 
    draw.text((W/2, current_h), "會議簽到", fill="black", font=font_body, anchor="mm")
    current_h += 30 
    qr_x = (W - 350) // 2 
    img.paste(qr, (qr_x, current_h))
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def is_canvas_blank(image_data):
    if image_data is None: return True
    return np.std(image_data) < 1.0

# ==============================================================================
# 5. MAIN LOGIC
# ==============================================================================
query_params = st.query_params
mid_param = query_params.get("mid", None)

init_data()

# ------------------------------------------------------------------------------
# ROUTE A: SIGN-IN VIEW (Public)
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
        
        # Sort and Format list
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
                    if st.button("↺"):
                        st.session_state.pad_size = 320
                        st.rerun()
                with col_s:
                    c_width = st.slider("Pad Scale", 250, 800, st.session_state.pad_size, key="pad_size")
                c_height = int(c_width * 0.52)
            
            canvas = st_canvas(
                fill_color="white", stroke_width=5, stroke_color="black",
                background_color="#FFFFFF", height=c_height, width=c_width,
                key=f"canvas_{actual_name}_{c_width}"
            )
            
            # --- NEW: SIGNATURE LOGIC WITH DRIVE & ST.STATUS ---
            if st.button("Confirm Signature", type="primary"):
                if is_canvas_blank(canvas.image_data):
                    st.warning("⚠️ Please sign on the pad first.")
                else:
                    with st.status("🚀 Processing...", expanded=True) as status:
                        try:
                            # 1. Upload Image to Drive
                            status.write("📤 Uploading signature to Drive...")
                            img = Image.fromarray(canvas.image_data.astype('uint8'), 'RGBA')
                            buffered = BytesIO()
                            img.save(buffered, format="PNG")
                            buffered.seek(0)
                            
                            timestamp = int(time.time())
                            fname = f"{mid_param}_{actual_name.replace(' ', '_')}_{timestamp}.png"
                            
                            # Call our helper function
                            file_id = upload_signature_to_drive(buffered, fname)
                            status.write("✅ Image stored securely!")

                            # 2. Update Sheet with ID
                            status.write("📝 Updating Register...")
                            ws_att = get_sheet_object("Meeting_Attendees")
                            
                            # Find row (optimized lookup)
                            # We only fetch columns needed to find the row to save bandwidth
                            # But for safety in this version, we stick to logic that works
                            all_rows = ws_att.get_all_values()
                            headers = all_rows[0]
                            name_idx = headers.index("AttendeeName")
                            mid_idx = headers.index("MeetingID")
                            status_col = headers.index("Status") + 1
                            sig_col = headers.index("SignatureBase64") + 1 # Storing ID here!

                            row_idx = -1
                            for i, r in enumerate(all_rows):
                                if i==0: continue
                                if safe_str(r[name_idx]) == safe_str(actual_name) and safe_str(r[mid_idx]) == safe_str(mid_param):
                                    row_idx = i + 1
                                    break
                            
                            if row_idx > 0:
                                ws_att.batch_update([
                                    {'range': gspread.utils.rowcol_to_a1(row_idx, status_col), 'values': [['Signed']]},
                                    {'range': gspread.utils.rowcol_to_a1(row_idx, sig_col), 'values': [[file_id]]}
                                ])
                                status.update(label="🎉 Done!", state="complete", expanded=False)
                                
                                st.session_state["success_msg"] = f"✅ Signed: {actual_name}"
                                st.session_state.signer_select_index = 0
                                refresh_attendees_only()
                                time.sleep(1)
                                st.rerun()
                            else:
                                status.update(label="❌ Error", state="error")
                                st.error("Row not found in sheet.")

                        except Exception as e:
                            status.update(label="❌ Failed", state="error")
                            st.error(f"Error: {e}")


# ------------------------------------------------------------------------------
# ROUTE B: ADMIN (Protected)
# ------------------------------------------------------------------------------
else:
    # --- NEW: SECURE LOGIN FLOW ---
    if not st.session_state.is_admin:
        st.title("🔐 Admin Login")
        c1, c2 = st.columns([1,2])
        pwd = c1.text_input("Enter Admin Password", type="password")
        if c1.button("Login"):
            # Check against secrets
            if pwd == st.secrets["general"]["admin_password"]:
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("Incorrect password")
        st.stop() # Stop execution if not logged in

    # --- ADMIN DASHBOARD ---
    st.sidebar.title("Admin Panel")
    if st.sidebar.button("🔓 Logout"):
        st.session_state.is_admin = False
        st.rerun()
        
    menu = st.sidebar.radio("Go to:", ["🗓️ Arrange Meeting", "🛡️ Meeting Control", "👥 Employee Master"])
    
    st.sidebar.divider()
    if st.sidebar.button("🔄 Refresh Data"):
        refresh_all_data()
        st.sidebar.success("Synced!")
        time.sleep(1)
        st.rerun()

    ensure_data_loaded()

    # --- 1. ARRANGE MEETING ---
    if menu == "🗓️ Arrange Meeting":
        st.title("Arrange New Meeting")
        df_master = st.session_state.df_master
        
        if "created_meeting_data" in st.session_state and st.session_state.created_meeting_data:
            lm = st.session_state.created_meeting_data
            st.success(f"🎉 Created: **{lm['name']}** (ID: {lm['id']})")
            
            card_bytes = generate_qr_card(lm['url'], lm['name'], lm['loc'], lm['time'])
            fn = f"QR_{lm['id']}.png"
            
            c1, c2 = st.columns(2)
            c1.image(card_bytes, width=250)
            c2.download_button("📥 Download QR Card", card_bytes, fn, "image/png", type="primary")
            if c2.button("⬅️ Create Another"):
                st.session_state.created_meeting_data = None
                st.rerun()
        else:
            with st.form("create_m"):
                col1, col2 = st.columns(2)
                name = col1.text_input("Meeting Name")
                loc = col2.text_input("Location")
                date = col1.date_input("Date")
                t_start = col1.time_input("Start", value=datetime.strptime("12:00", "%H:%M").time())
                t_end = col2.time_input("End", value=datetime.strptime("13:00", "%H:%M").time())
                
                # Filter Attendees
                depts = sorted(df_master["Department"].astype(str).unique().tolist()) if not df_master.empty else []
                sel_dept = st.multiselect("Filter Department", depts)
                
                f_emp = df_master.copy()
                if sel_dept: f_emp = f_emp[f_emp["Department"].astype(str).isin(sel_dept)]
                
                all_names = f_emp["FullName"].astype(str).unique().tolist()
                selected_names = st.multiselect("Attendees", all_names)
                
                if st.form_submit_button("Create Meeting"):
                    if name and loc and selected_names:
                        with st.spinner("Creating..."):
                            df_info_live = api_read_safe("Meeting_Info")
                            
                            # ID Gen
                            max_id = 0
                            if not df_info_live.empty:
                                max_id = pd.to_numeric(df_info_live["MeetingID"], errors='coerce').fillna(0).max()
                            new_id = int(max_id) + 1
                            
                            range_str = f"{date.strftime('%Y/%m/%d')} {t_start.strftime('%H:%M')}~{t_end.strftime('%H:%M')}"
                            
                            # Save Info
                            ws_info = get_sheet_object("Meeting_Info")
                            ws_info.append_row([new_id, name, str(date), loc, range_str, "Open"])
                            
                            # Save Attendees
                            ws_att = get_sheet_object("Meeting_Attendees")
                            rows = []
                            for n in selected_names:
                                emp = df_master[df_master["FullName"] == n].iloc[0]
                                rows.append([
                                    n, emp.get("JobTitle", ""), new_id, 
                                    int(emp.get("RankID", 999)), "Pending", ""
                                ])
                            # We assume the columns order: Name, Title, MID, RID, Status, Sig
                            # It is safer to map by header, but for brevity in this focused update:
                            if rows: ws_att.append_rows(rows)
                            
                            refresh_all_data()
                            st.session_state.created_meeting_data = {
                                'id': new_id, 'name': name, 'loc': loc, 'time': range_str,
                                'url': f"https://{DEPLOYMENT_URL}/?mid={new_id}"
                            }
                            st.rerun()

    # --- 2. MEETING CONTROL (PDF Logic Updated) ---
    elif menu == "🛡️ Meeting Control":
        st.title("Meeting Control")
        df_info = st.session_state.df_info
        
        # Simple list view
        for _, m in df_info.sort_values("MeetingID", ascending=False).head(st.session_state.meeting_limit).iterrows():
            m_id = str(m['MeetingID'])
            status = m.get('MeetingStatus', 'Open')
            
            with st.expander(f"{'🟢' if status=='Open' else '🔴'} {m['MeetingName']} ({m['MeetingDate']})"):
                c1, c2, c3 = st.columns([1,1,2])
                
                # Close/Open
                if c1.button(f"{'Lock' if status=='Open' else 'Unlock'}", key=f"btn_{m_id}"):
                    ws = get_sheet_object("Meeting_Info")
                    # Find row logic omitted for brevity, essentially same as before
                    # Ideally, use find() or iterate
                    cell = ws.find(m_id)
                    if cell:
                        ws.update_cell(cell.row, 6, "Close" if status=="Open" else "Open") # Col 6 is status
                        refresh_all_data()
                        st.rerun()
                
                # PDF Generation (The Big Update)
                if c3.button("📄 Generate PDF", key=f"pdf_{m_id}"):
                    with st.spinner("Downloading signatures & Generating PDF..."):
                        # Get fresh data
                        fresh_att = api_read_safe("Meeting_Attendees")
                        sub = fresh_att[fresh_att["MeetingID"].astype(str) == m_id]
                        
                        pdf = FPDF()
                        pdf.add_page()
                        try:
                            pdf.add_font('CustomFont', '', FONT_CH, uni=True)
                            pdf.set_font('CustomFont', '', 24)
                        except:
                            pdf.set_font("Arial", "", 24)
                            
                        pdf.cell(0, 15, f"{m['MeetingName']}", ln=True, align="C")
                        pdf.set_font_size(14)
                        pdf.cell(0, 10, f"Loc: {m['Location']} | Time: {m['TimeRange']}", ln=True, align="C")
                        pdf.ln(10)
                        
                        # Table
                        pdf.set_fill_color(220, 220, 220)
                        pdf.cell(80, 10, "Name", 1, 0, 'C', True)
                        pdf.cell(100, 10, "Signature", 1, 1, 'C', True)
                        
                        for i, row in sub.iterrows():
                            pdf.cell(80, 25, str(row['AttendeeName']), 1, 0, 'C')
                            x, y = pdf.get_x(), pdf.get_y()
                            pdf.cell(100, 25, "", 1, 1)
                            
                            # THE DOWNLOAD LOGIC
                            sig_id = str(row.get('SignatureBase64', '')).strip()
                            if len(sig_id) > 10 and "data:image" not in sig_id:
                                # It's a Drive ID!
                                img_stream = download_image_from_drive(sig_id)
                                if img_stream:
                                    # FPDF needs a temp file
                                    tmp_name = f"tmp_{m_id}_{i}.png"
                                    with open(tmp_name, "wb") as f:
                                        f.write(img_stream.read())
                                    try:
                                        pdf.image(tmp_name, x+20, y+2, h=20)
                                        os.remove(tmp_name)
                                    except: pass
                            
                        pdf_bytes = bytes(pdf.output())
                        b64 = base64.b64encode(pdf_bytes).decode()
                        href = f'<a href="data:application/pdf;base64,{b64}" download="Meeting_{m_id}.pdf">Click to Download PDF</a>'
                        st.markdown(href, unsafe_allow_html=True)

    # --- 3. EMPLOYEE MASTER ---
    elif menu == "👥 Employee Master":
        st.title("Employee Master")
        edited = st.data_editor(st.session_state.df_master, num_rows="dynamic", use_container_width=True)
        
        if st.button("💾 Save Changes"):
            ws = get_sheet_object("Employee_Master")
            ws.clear()
            ws.update([edited.columns.tolist()] + edited.values.tolist())
            refresh_all_data()
            st.success("Saved!")
