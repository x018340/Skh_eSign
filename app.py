import streamlit as st
from config import ADMIN_PASSWORD
from core.state import init_state, ensure_data_loaded
from components.signin_view import show_signin
from components.admin_view import show_admin

st.set_page_config(page_title="SKH E-Sign System", page_icon="✍️", layout="wide")

# 1. Initialize
init_state()

# 2. Check Routing
query_params = st.query_params
mid_param = query_params.get("mid")
admin_key_param = query_params.get("admin_access")

# 3. Logic
if mid_param:
    ensure_data_loaded()
    show_signin(mid_param)

elif admin_key_param == ADMIN_PASSWORD or st.session_state.is_admin:
    st.session_state.is_admin = True
    ensure_data_loaded()
    show_admin()

else:
    st.error("⛔ Access Denied.")
