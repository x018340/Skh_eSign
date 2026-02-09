import streamlit as st

# Deployment
DEPLOYMENT_URL = "skhesign-jnff8wr9fkhrp6jqpsvfsjh.streamlit.app"

# Google Sheets
SHEET_NAME = "esign"

# Assets
FONT_CH = "font_CH.ttf"
FONT_EN = "font_EN.ttf"

# Admin
ADMIN_KEY = st.secrets["general"]["admin_password"]  # e.g. "1234" in secrets

# Google Drive (for signature images)
# Folder already created and shared with the service account
DRIVE_FOLDER_ID = "1OwuotOU_w8wV1C9AU78aK4K7Qxmvf_Y4"

# Signature storage format in Google Sheets:
# - Legacy: data:image/png;base64,...
# - New:    drive:<file_id>
SIGNATURE_DRIVE_PREFIX = "drive:"
