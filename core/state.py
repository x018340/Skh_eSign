import streamlit as st
from services.data_service import api_read_with_retry

def init_data():
    if "df_master" not in st.session_state: st.session_state.df_master = None
    if "df_info" not in st.session_state: st.session_state.df_info = None
    if "df_att" not in st.session_state: st.session_state.df_att = None
    if "processing_sign" not in st.session_state: st.session_state.processing_sign = False
    if "pdf_cache" not in st.session_state: st.session_state.pdf_cache = {}
    if "meeting_limit" not in st.session_state: st.session_state.meeting_limit = 10
    if "pad_size" not in st.session_state: st.session_state.pad_size = 320
    if "is_admin" not in st.session_state: st.session_state.is_admin = False
    if "last_save_error" not in st.session_state: st.session_state.last_save_error = None
    if "success_msg" not in st.session_state: st.session_state.success_msg = None

def refresh_all_data():
    with st.spinner("🔄 Syncing All Databases..."):
        st.session_state.df_master = api_read_with_retry("Employee_Master")
        st.session_state.df_info = api_read_with_retry("Meeting_Info")
        st.session_state.df_att = api_read_with_retry("Meeting_Attendees")
        st.session_state.pdf_cache = {}

def refresh_attendees_only():
    st.session_state.df_att = api_read_with_retry("Meeting_Attendees")
    st.session_state.pdf_cache = {}

def ensure_data_loaded():
    if (st.session_state.df_info is None or 
        st.session_state.df_att is None or 
        st.session_state.df_master is None or
        st.session_state.df_master.empty):
        refresh_all_data()
