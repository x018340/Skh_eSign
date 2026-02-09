import base64
from io import BytesIO
import time

import gspread
import pandas as pd
import streamlit as st
from PIL import Image
from streamlit_drawable_canvas import st_canvas

from core.state import refresh_attendees_only
from services.data_service import save_signature
from utils import is_canvas_blank, safe_int, safe_str

def show_signin(mid_param):
    df_info = st.session_state.df_info
    meeting = df_info[df_info["MeetingID"].astype(str) == str(mid_param)]

    if meeting.empty:
        st.error(f"❌ Meeting ID {mid_param} not found.")
        if st.button("🔄 Reload Data"):
            from core.state import refresh_all_data
            refresh_all_data()
            st.rerun()
        return

    m = meeting.iloc[0]
    status = m.get("MeetingStatus", "Open")

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
        icon = "✅ " if row.get("Status") == "Signed" else "⬜ "
        return f"{icon}{row.get('AttendeeName')} ({row.get('JobTitle')})"

    options = current_att.apply(fmt, axis=1).tolist()

    if "signer_select_index" not in st.session_state:
        st.session_state.signer_select_index = 0

    selection = st.selectbox(
        "Select your name to sign:",
        ["-- Select --"] + options,
        index=st.session_state.signer_select_index,
        key="signer_sb",
    )

    if selection == "-- Select --":
        return

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
        key=f"canvas_{actual_name}_{c_width}",
    )

    # --- UPDATED SAVING LOGIC ---
    # We moved the logic INSIDE the button check.
    # We use st.status to show progress.
    # We DO NOT rerun if there is an exception, so you can read the error.
    
    if st.button("Confirm Signature", type="primary"):
        if is_canvas_blank(canvas.image_data):
            st.warning("⚠️ Please sign on the pad before confirming.")
        else:
            # Create a status container that persists
            with st.status("🚀 Processing Signature...", expanded=True) as status:
                try:
                    # 1. Prepare Image
                    status.write("🖼️ Processing image data...")
                    img = Image.fromarray(canvas.image_data.astype("uint8"), "RGBA")
                    buffered = BytesIO()
                    img.save(buffered, format="PNG")
                    png_bytes = buffered.getvalue()

                    # 2. Upload and Update Sheet (Calls data_service.py)
                    # This function handles both Drive Upload and Sheet Update
                    status.write("☁️ Uploading to Google Drive & Updating Sheet...")
                    save_signature(str(mid_param), safe_str(actual_name), png_bytes, retries=5)
                    
                    # 3. Success
                    status.write("✅ Data successfully saved!")
                    status.update(label="🎉 Signature Confirmed!", state="complete", expanded=False)
                    
                    # 4. Refresh Local Data
                    refresh_attendees_only()
                    st.session_state["success_msg"] = f"✅ Saved: {actual_name}"
                    st.session_state.signer_select_index = 0
                    
                    time.sleep(1) # Give user a moment to see the green checkmark
                    st.rerun()

                except Exception as e:
                    # 🛑 ERROR HANDLING: Do NOT rerun. Show the error clearly.
                    status.update(label="❌ Save Failed", state="error", expanded=True)
                    st.error(f"**System Error:** {str(e)}")
                    st.write("Please check:")
                    st.write("1. Is `google-api-python-client` in requirements.txt?")
                    st.write("2. Does the Service Account have 'Editor' access to the Drive Folder?")
