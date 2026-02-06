import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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
from tenacity import retry, stop_after_attempt, wait_exponential

# --- CONFIGURATION ---
SHEET_NAME = "esign"
FONT_CH = "font_CH.ttf"  # Ensure this file is in your Repo
DEPLOYMENT_URL = "skhesign-jnff8wr9fkhrp6jqpsvfsjh.streamlit.app"

st.set_page_config(page_title="SKH E-Sign System (v2)", page_icon="✍️", layout="wide")

# ==============================================================================
# 1. CONNECTION & SERVICES
# ==============================================================================

@st.cache_resource
def get_services():
    """Authenticates with Google Cloud and returns Sheets and Drive clients."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Load credentials from Secrets
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    # 1. Sheets Client
    client_sheets = gspread.authorize(creds)
    
    # 2. Drive API Service
    service_drive = build('drive', 'v3', credentials=creds)
    
    return client_sheets, service_drive

def get_sheet_object(worksheet_name):
    client, _ = get_services()
    return client.open(SHEET_NAME).worksheet(worksheet_name)

# --- RETRY DECORATOR FOR STABILITY ---
# Replaces manual while loops. Retries 3 times if API fails.
retry_api = retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=5))

@retry_api
def fetch_data(worksheet_name):
    ws = get_sheet_object(worksheet_name)
    return pd.DataFrame(ws.get_all_records())

# ==============================================================================
# 2. HELPER FUNCTIONS
# ==============================================================================

def safe_str(val): return str(val).strip()
def safe_int(val, default=999):
    try: return int(float(val))
    except: return default

def is_canvas_blank(image_data):
    # Check if canvas is empty (sum of alpha channel is 0 or low variance)
    if image_data is None: return True
    return np.sum(image_data[:, :, 3]) == 0

def download_image_from_drive(service, file_id):
    """Downloads an image from Drive into memory."""
    try:
        request = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        return fh
    except Exception as e:
        print(f"DL Error: {e}")
        return None

def generate_qr_card(url, m_name, m_loc, m_time):
    # (Same as your original function)
    m_name = str(m_name); m_loc = str(m_loc); m_time = str(m_time)
    qr = qrcode.make(url).resize((350, 350))
    img = Image.new('RGB', (600, 850), 'white')
    draw = ImageDraw.Draw(img)
    try:
        font_header = ImageFont.truetype(FONT_CH, 40)
        font_body = ImageFont.truetype(FONT_CH, 22)
    except:
        font_header = ImageFont.load_default()
        font_body = ImageFont.load_default()

    wrapper = textwrap.TextWrapper(width=14)
    current_h = 60
    for line in wrapper.wrap(m_name):
        draw.text((300, current_h), line, fill="black", font=font_header, anchor="mm")
        current_h += 55
    
    current_h += 20
    draw.multiline_text((300, current_h), f"地點：{m_loc}\n時間：{m_time}", fill="black", font=font_body, anchor="ma", align="center")
    
    current_h += 100
    draw.text((300, current_h), "會議簽到", fill="black", font=font_body, anchor="mm")
    img.paste(qr, ((600 - 350) // 2, current_h + 30))
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ==============================================================================
# 3. STATE MANAGEMENT
# ==============================================================================

def init_data():
    if "df_info" not in st.session_state: st.session_state.df_info = None
    if "df_att" not in st.session_state: st.session_state.df_att = None
    if "df_master" not in st.session_state: st.session_state.df_master = None
    if "is_admin" not in st.session_state: st.session_state.is_admin = False
    if "pad_size" not in st.session_state: st.session_state.pad_size = 320

def refresh_data():
    with st.spinner("🔄 Syncing Data..."):
        st.session_state.df_info = fetch_data("Meeting_Info")
        st.session_state.df_att = fetch_data("Meeting_Attendees")
        st.session_state.df_master = fetch_data("Employee_Master")

# ==============================================================================
# 4. MAIN APP LOGIC
# ==============================================================================

init_data()
query_params = st.query_params
mid_param = query_params.get("mid", None)

# ------------------------------------------------------------------------------
# ROUTE A: PUBLIC SIGNING (With Google Drive Integration)
# ------------------------------------------------------------------------------
if mid_param:
    if st.session_state.df_info is None: refresh_data()
    
    df_info = st.session_state.df_info
    meeting = df_info[df_info["MeetingID"].astype(str) == str(mid_param)]
    
    if meeting.empty:
        st.error("Meeting not found.")
    else:
        m = meeting.iloc[0]
        if m.get('MeetingStatus') == "Close":
            st.error("⛔ Meeting Closed.")
            st.stop()
            
        st.title(f"{m.get('MeetingName')}")
        st.write(f"📍 {m.get('Location')} | 🕒 {m.get('TimeRange')}")
        st.divider()
        
        # Display Success Message if just signed
        if "success_msg" in st.session_state:
            st.success(st.session_state["success_msg"])
            del st.session_state["success_msg"]

        # Filter Attendees
        df_att = st.session_state.df_att
        curr_att = df_att[df_att["MeetingID"].astype(str) == str(mid_param)].copy()
        
        # Sorting
        if "RankID" in curr_att.columns:
            curr_att["RankID_Int"] = pd.to_numeric(curr_att["RankID"], errors='coerce').fillna(999)
            curr_att = curr_att.sort_values("RankID_Int")
            
        # Select Box
        options = [f"{'✅ ' if row['Status']=='Signed' else '⬜ '}{row['AttendeeName']} ({row['JobTitle']})" 
                   for _, row in curr_att.iterrows()]
        
        sel_idx = st.session_state.get("signer_select_index", 0)
        selection = st.selectbox("Select Name:", ["-- Select --"] + options, index=sel_idx)

        if selection != "-- Select --":
            actual_name = selection.split(" (")[0].replace("✅ ", "").replace("⬜ ", "")
            
            # Canvas
            c_width = st.slider("Pad Size", 250, 600, st.session_state.pad_size)
            st.session_state.pad_size = c_width
            
            canvas = st_canvas(
                stroke_width=3, stroke_color="black", background_color="#eee",
                height=int(c_width*0.5), width=c_width, key="sig_pad"
            )
            
            # --- THE NEW SAVE LOGIC ---
            if st.button("Confirm Signature", type="primary"):
                if is_canvas_blank(canvas.image_data):
                    st.warning("⚠️ Pad is empty.")
                else:
                    with st.status("🚀 Processing...", expanded=True) as status:
                        try:
                            # 1. Upload to Drive
                            status.write("📤 Uploading image to Google Drive...")
                            img = Image.fromarray(canvas.image_data.astype('uint8'), 'RGBA')
                            buf = BytesIO()
                            img.save(buf, format="PNG")
                            buf.seek(0)
                            
                            _, drive_svc = get_services()
                            folder_id = st.secrets["general"]["drive_folder_id"]
                            
                            fname = f"{mid_param}_{actual_name}_{int(time.time())}.png"
                            meta = {'name': fname, 'parents': [folder_id]}
                            media = MediaIoBaseUpload(buf, mimetype='image/png')
                            
                            file = drive_svc.files().create(body=meta, media_body=media, fields='id').execute()
                            file_id = file.get('id')
                            status.write("✅ Image Secured!")

                            # 2. Update Sheet with File ID
                            status.write("📝 Updating Register...")
                            ws = get_sheet_object("Meeting_Attendees")
                            
                            # Find Row
                            cell = ws.find(actual_name) # Basic find, assuming unique names for simplicity
                            # For robust find: Download column A and match index (better for duplicates)
                            
                            # Using the robust method as per best practice:
                            all_vals = ws.get_all_values()
                            name_idx = all_vals[0].index("AttendeeName")
                            mid_idx = all_vals[0].index("MeetingID")
                            
                            r_idx = -1
                            for i, row in enumerate(all_vals):
                                if row[name_idx] == actual_name and str(row[mid_idx]) == str(mid_param):
                                    r_idx = i + 1
                                    break
                            
                            if r_idx > 0:
                                ws.update_cell(r_idx, all_vals[0].index("Status")+1, "Signed")
                                ws.update_cell(r_idx, all_vals[0].index("SignatureBase64")+1, file_id) # Saving ID!
                                
                                status.update(label="🎉 Done!", state="complete", expanded=False)
                                st.session_state.df_att = fetch_data("Meeting_Attendees") # Refresh local
                                st.session_state["success_msg"] = f"Signed: {actual_name}"
                                st.session_state.signer_select_index = 0
                                time.sleep(1)
                                st.rerun()
                            else:
                                status.update(label="❌ Name not found in sheet", state="error")
                                
                        except Exception as e:
                            status.update(label="❌ Error", state="error")
                            st.error(f"Details: {e}")

# ------------------------------------------------------------------------------
# ROUTE B: ADMIN PANEL (Password Protected)
# ------------------------------------------------------------------------------
else:
    # Login Check
    if not st.session_state.is_admin:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Login"):
            if pwd == st.secrets["general"]["admin_password"]:
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("Wrong Password")
        st.stop()

    # Admin Dashboard
    st.sidebar.title("Admin Menu")
    menu = st.sidebar.radio("Go to:", ["Arrange Meeting", "Meeting Control", "Employee Master"])
    
    if st.sidebar.button("Refresh Data"):
        refresh_data()
        st.rerun()
        
    if st.session_state.df_info is None: refresh_data()

    # --- 1. ARRANGE MEETING ---
    if menu == "Arrange Meeting":
        st.title("🗓️ Create Meeting")
        with st.form("create_m"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Name")
            loc = c2.text_input("Location")
            date = c1.date_input("Date")
            t_s = c2.time_input("Start", value=datetime.strptime("12:00", "%H:%M").time())
            
            # Attendee Selection
            df_m = st.session_state.df_master
            depts = sorted(df_m["Department"].astype(str).unique()) if not df_m.empty else []
            f_dept = st.multiselect("Filter Dept", depts)
            
            mask = df_m["Department"].isin(f_dept) if f_dept else [True]*len(df_m)
            names = df_m[mask]["FullName"].tolist() if not df_m.empty else []
            atts = st.multiselect("Attendees", names)
            
            if st.form_submit_button("Create"):
                if name and atts:
                    ws_info = get_sheet_object("Meeting_Info")
                    ws_att = get_sheet_object("Meeting_Attendees")
                    
                    # ID Gen
                    try: 
                        last_id = int(ws_info.col_values(1)[-1]) 
                    except: 
                        last_id = 0
                    new_id = last_id + 1
                    
                    # Save Info
                    t_str = f"{date} {t_s}"
                    ws_info.append_row([new_id, name, str(date), loc, t_str, "Open"])
                    
                    # Save Attendees
                    rows = []
                    for n in atts:
                        emp = df_m[df_m["FullName"]==n].iloc[0]
                        rows.append([n, emp['JobTitle'], new_id, emp['RankID'], "Pending", ""])
                    ws_att.append_rows(rows)
                    
                    # Generate QR
                    m_url = f"https://{DEPLOYMENT_URL}/?mid={new_id}"
                    qr_img = generate_qr_card(m_url, name, loc, t_str)
                    st.success(f"Created Meeting ID: {new_id}")
                    st.download_button("Download QR Card", qr_img, f"QR_{new_id}.png", "image/png")
                    refresh_data()

    # --- 2. MEETING CONTROL ---
    elif menu == "Meeting Control":
        st.title("🛡️ Manage Meetings")
        df_i = st.session_state.df_info
        
        for i, m in df_i.sort_values("MeetingID", ascending=False).head(10).iterrows():
            mid = str(m['MeetingID'])
            with st.expander(f"{m['MeetingDate']} | {m['MeetingName']} ({m['MeetingStatus']})"):
                c1, c2 = st.columns(2)
                
                # PDF Generation (Updated for Drive)
                if c2.button("📄 Generate PDF", key=f"pdf_{mid}"):
                    with st.spinner("Downloading images & generating PDF..."):
                        pdf = FPDF()
                        pdf.add_page()
                        pdf.add_font('CustomFont', '', FONT_CH, uni=True)
                        pdf.set_font('CustomFont', '', 20)
                        pdf.cell(0, 10, f"{m['MeetingName']}", ln=True, align='C')
                        pdf.set_font_size(12)
                        pdf.cell(0, 10, f"Date: {m['MeetingDate']} | Loc: {m['Location']}", ln=True, align='C')
                        pdf.ln(10)
                        
                        pdf.cell(80, 10, "Name", 1)
                        pdf.cell(100, 10, "Signature", 1, 1)
                        
                        df_a = st.session_state.df_att
                        atts = df_a[df_a["MeetingID"].astype(str) == mid]
                        
                        _, drive_svc = get_services()
                        
                        for _, row in atts.iterrows():
                            pdf.cell(80, 20, str(row['AttendeeName']), 1)
                            x, y = pdf.get_x(), pdf.get_y()
                            pdf.cell(100, 20, "", 1, 1)
                            
                            # IMAGE FETCHING
                            sig_id = str(row['SignatureBase64']).strip()
                            if len(sig_id) > 10: # Assuming it's a Drive ID
                                img_bytes = download_image_from_drive(drive_svc, sig_id)
                                if img_bytes:
                                    img_bytes.seek(0)
                                    tmp_name = f"tmp_{random.randint(1,9999)}.png"
                                    with open(tmp_name, "wb") as f:
                                        f.write(img_bytes.read())
                                    try:
                                        pdf.image(tmp_name, x+10, y+2, h=16)
                                        os.remove(tmp_name)
                                    except: pass
                        
                        pdf_bytes = pdf.output(dest='S').encode('latin-1')
                        st.download_button("Download PDF", pdf_bytes, f"Report_{mid}.pdf", "application/pdf")

    # --- 3. MASTER DATA ---
    elif menu == "Employee Master":
        st.title("👥 Employees")
        edited = st.data_editor(st.session_state.df_master, num_rows="dynamic")
        if st.button("Save Changes"):
            ws = get_sheet_object("Employee_Master")
            ws.clear()
            ws.update([edited.columns.tolist()] + edited.values.tolist())
            st.success("Saved!")
