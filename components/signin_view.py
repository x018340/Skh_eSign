import streamlit as st
from streamlit_drawable_canvas import st_canvas
from core.connection import get_sheet_object
from core.state import refresh_attendees_only
from utils import safe_int, safe_str, is_canvas_blank
import pandas as pd
from PIL import Image
from io import BytesIO
import base64
import gspread
import time

def show_signin(mid_param):
    ensure_data_loaded = st.session_state.df_info
    df_info = st.session_state.df_info
    
    meeting = df_info[df_info["MeetingID"].astype(str) == str(mid_param)]
    
    if meeting.empty:
        st.error(f"❌ Meeting ID {mid_param} not found.")
        if st.button("🔄 Reload Data"):
            from core.state import refresh_all_data
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
                fill_color="white", stroke_width=5, stroke_color="black",
                background_color="#FFFFFF", height=c_height, width=c_width, 
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
                        retries = 10
                        for i in range(retries):
                            try:
                                ws_attendees.batch_update([
                                    {'range': gspread.utils.rowcol_to_a1(row_update_idx, status_idx), 'values': [['Signed']]},
                                    {'range': gspread.utils.rowcol_to_a1(row_update_idx, sig_idx), 'values': [[full_base64]]}
                                ])
                                break
                            except gspread.exceptions.APIError as e:
                                if i == retries - 1: raise e
                                time.sleep(2 + i)

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
