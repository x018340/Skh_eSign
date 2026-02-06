import streamlit as st

# Deployment Settings
DEPLOYMENT_URL = "skhesign-jnff8wr9fkhrp6jqpsvfsjh.streamlit.app"
SHEET_NAME = "esign"

# Secrets Mapping
GCP_CREDS = st.secrets["gcp_service_account"]
ADMIN_PASSWORD = st.secrets["general"]["admin_password"]
DRIVE_FOLDER_ID = st.secrets["general"]["drive_folder_id"]

# Assets
FONT_CH = "font_CH.ttf"
FONT_EN = "font_EN.ttf"
