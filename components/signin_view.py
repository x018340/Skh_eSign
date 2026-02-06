import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
from io import BytesIO
import base64
from utils import safe_int, is_canvas_blank
from services.data_service import save_signature_to_sheet
from core.state import refresh_attendees_only

def show_signin(mid_param):
    df_info = st.session_state.df_info
    meeting = df_info[df_info["MeetingID"].astype(str) == str(mid_param)]
    
    if meeting.empty:
        st.error(f"❌ Meeting ID {mid_param} not found.")
        return

    m = meeting.iloc[0]
    if m.get('MeetingStatus') == "Close":
        st.error("⛔ This meeting is currently CLOSED.")
        return
    
    st.title(f"{m.get('MeetingName')}")
    st.write(f"📍 **{m.get('Location')}**  🕒 **{m.get('TimeRange')}**")

    if "success_msg" in st.session_state:
        st.success(st.session_state["success_msg"])
        del st.session_state["success_msg"]

    current_att = st.session_state.df_att[st.session_state.df_att["MeetingID"].astype(str) == str(mid_param)].copy()
    if "RankID" in current_att.columns:
        current_att["RankID_Int"] = current_att["RankID"].apply(lambda x: safe_int(x, 999))
        current_att = current_att.sort_values("RankID_Int")
    
    options = current_att.apply(lambda r: f"{'✅ ' if r.get('Status') == 'Signed' else '⬜ '}{r.get('AttendeeName')} ({r.get('JobTitle')})", axis=1).tolist()
    
    selection = st.selectbox("Select your name:", ["-- Select --"] + options, key="signer_sb")
    
    if selection != "-- Select --":
        actual_name = selection.split(" (")[0].replace("✅ ", "").replace("⬜ ", "")
        
        c_width = st.slider("Pad Scale (px)", 250, 800, st.session_state.pad_size)
        c_height = int(c_width * 0.52)
        
        canvas = st_canvas(fill_color="white", stroke_width=5, stroke_color="black", background_color="#FFFFFF", height=c_height, width=c_width, key=f"cv_{actual_name}")
        
        if st.button("Confirm Signature"):
            if is_canvas_blank(canvas.image_data):
                st.warning("⚠️ Please sign first.")
            else:
                with st.spinner("Saving..."):
                    img = Image.fromarray(canvas.image_data.astype('uint8'), 'RGBA')
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    b64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
                    
                    if save_signature_to_sheet(mid_param, actual_name, b64):
                        refresh_attendees_only()
                        st.session_state["success_msg"] = f"✅ Saved: {actual_name}"
                        st.rerun()
                    else:
                        st.error("Save failed.")
