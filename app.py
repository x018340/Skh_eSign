import streamlit as st
from core.state import init_state
from views.signin_view import render_signin
from views.admin_view import render_admin
import config

init_state()

query = st.query_params
if "mid" in query:
    render_signin(query["mid"])
elif query.get("admin_access") == config.ADMIN_PWD or st.session_state.is_admin:
    st.session_state.is_admin = True
    render_admin()
else:
    st.info("Please scan a QR code to sign in.")
