import streamlit as st
from config import ADMIN_KEY
from core.state import init_data, ensure_data_loaded
from components.signin_view import show_signin
from components.admin_view import show_admin

st.set_page_config(page_title="SKH E-Sign System", page_icon="✍️", layout="wide")

init_data()

query_params = st.query_params
mid_param = query_params.get("mid", None)
admin_access_param = query_params.get("admin_access", None)

if mid_param:
    ensure_data_loaded()
    show_signin(mid_param)
elif (admin_access_param == ADMIN_KEY) or st.session_state.is_admin:
    st.session_state.is_admin = True
    ensure_data_loaded()
    show_admin()
else:
    st.error("⛔ Access Denied. Please scan a valid meeting QR code or use the Admin link.")
