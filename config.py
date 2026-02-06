import streamlit as st

# Secrets
GCP_CREDS = st.secrets["gcp_service_account"]
ADMIN_PWD = st.secrets["general"]["admin_password"]
DRIVE_ID  = st.secrets["general"]["drive_folder_id"]

# Settings
SHEET_NAME = "esign"
DEPLOY_URL = "skhesign-jnff8wr9fkhrp6jqpsvfsjh.streamlit.app"
FONTS = {"CH": "font_CH.ttf", "EN": "font_EN.ttf"}
