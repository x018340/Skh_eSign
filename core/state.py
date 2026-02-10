import streamlit as st
from services.data_service import api_read_with_retry


def init_data():
    if "df_master" not in st.session_state:
        st.session_state.df_master = None
    if "df_info" not in st.session_state:
        st.session_state.df_info = None
    if "df_att" not in st.session_state:
        st.session_state.df_att = None

    if "processing_sign" not in st.session_state:
        st.session_state.processing_sign = False
    if "pdf_cache" not in st.session_state:
        st.session_state.pdf_cache = {}
    if "meeting_limit" not in st.session_state:
        st.session_state.meeting_limit = 10
    if "pad_size" not in st.session_state:
        st.session_state.pad_size = 320
    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False


def refresh_all_data(show_spinner: bool = True):
    def _do():
        st.session_state.df_master = api_read_with_retry("Employee_Master")
        st.session_state.df_info = api_read_with_retry("Meeting_Info")
        st.session_state.df_att = api_read_with_retry("Meeting_Attendees")
        st.session_state.pdf_cache = {}

    if show_spinner:
        with st.spinner("🔄 Syncing All Databases..."):
            _do()
    else:
        _do()


def refresh_attendees_only():
    st.session_state.df_att = api_read_with_retry("Meeting_Attendees")
    st.session_state.pdf_cache = {}


def ensure_data_loaded():
    # Best practice: don't auto-reload on empty DataFrames (can cause repeated reload loops).
    # Only load when None (cold start). If empty, UI should show a manual Refresh button.
    if (
        st.session_state.df_info is None
        or st.session_state.df_att is None
        or st.session_state.df_master is None
    ):
        refresh_all_data(show_spinner=False)
