import streamlit as st

# Deployment
DEPLOYMENT_URL = "skhesign-jnff8wr9fkhrp6jqpsvfsjh.streamlit.app"

# Google Sheets
SHEET_NAME = "esign"

# Assets
FONT_CH = "font_CH.ttf"
FONT_EN = "font_EN.ttf"

# Admin
ADMIN_KEY = st.secrets["general"]["admin_password"]

# Google Apps Script (GAS) Bridge for signature storage
# Streamlit secrets:
# [gas]
# upload_url = "https://script.google.com/macros/s/....../exec"
# api_key = "YOUR_LONG_RANDOM_SECRET"
# folder_id = "YOUR_DRIVE_FOLDER_ID"
GAS_UPLOAD_URL = st.secrets.get("gas", {}).get("upload_url", "")
GAS_API_KEY = st.secrets.get("gas", {}).get("api_key", "")
GAS_FOLDER_ID = st.secrets.get("gas", {}).get("folder_id", "")

# Sheet signature value formats:
# - legacy: data:image/png;base64,...
# - new:    gas:<fileId>
SIGNATURE_GAS_PREFIX = "gas:"
