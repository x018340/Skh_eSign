import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
from io import BytesIO
import base64
import numpy as np
from data_service import refresh_attendees_only, save_signature_to_sheet
from query_utils import sort_attendees, format_attendee_option

def render_signin(mid_param):
    st.title("Meeting Sign-in")
    df_info = st.session_state.df_info
    meeting = df_info[df_info["MeetingID"].astype(str) == str(mid_param)]
    
    if meeting.empty:
        st.error("Meeting not found.")
        return

    m = meeting.iloc[0]
    if m.get('MeetingStatus') == "Close":
        st.error("⛔ This meeting is CLOSED.")
        return

    st.subheader(f"{m.get('MeetingName')}")
    st.write(f"📍 {m.get('Location')} | 🕒 {m.get('TimeRange')}")

    df_att = st.session_state.df_att
    current_att = sort_attendees(df_att[df_att["MeetingID"].astype(str) == str(mid_param)])
    options = current_att.apply(format_attendee_option, axis=1).tolist()
    
    selection = st.selectbox("Select your name:", ["-- Select --"] + options, index=st.session_state.signer_select_index)
    
    if selection != "-- Select --":
        actual_name = selection.split(" (")[0].replace("✅ ", "").replace("⬜ ", "")
        
        c_width = st.slider("Pad Scale", 250, 800, st.session_state.pad_size)
        canvas = st_canvas(fill_color="white", stroke_width=5, height=int(c_width*0.52), width=c_width, key=f"cv_{actual_name}")
        
        if st.button("Confirm Signature"):
            if canvas.image_data is not None and np.std(canvas.image_data) > 1.0:
                img = Image.fromarray(canvas.image_data.astype('uint8'), 'RGBA')
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                
                if save_signature_to_sheet(mid_param, actual_name, f"data:image/png;base64,{img_str}"):
                    st.success("Signed!")
                    refresh_attendees_only()
                    st.rerun()
            else:
                st.warning("Please sign first.")
