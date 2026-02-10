import streamlit as st

from config import ADMIN_KEY
from components.admin_view import show_admin
from components.signin_view import show_signin
# 🔥 Import the new optimized loader
from core.state import ensure_data_loaded, ensure_signin_data_loaded, init_data

st.set_page_config(page_title="SKH E-Sign System", page_icon="✍️", layout="wide")

init_data()

query_params = st.query_params
mid_param = query_params.get("mid", None)
admin_access_param = query_params.get("admin_access", None)

if mid_param:
    # 🔥 OPTIMIZATION: Use the faster loader here
    ensure_signin_data_loaded()
    show_signin(mid_param)
elif (admin_access_param == ADMIN_KEY) or st.session_state.is_admin:
    st.session_state.is_admin = True
    # Admin still needs the heavy loader
    ensure_data_loaded()
    show_admin()
else:
    st.error("⛔ Access Denied. Please scan a valid meeting QR code or use the Admin link.")
