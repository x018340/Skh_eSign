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

# Google Drive/Apps Script Bridge (signature images)
# GAS secrets are expected under [gas] in Streamlit secrets.
GAS_UPLOAD_URL = st.secrets.get("gas", {}).get("upload_url", "")
GAS_API_KEY = st.secrets.get("gas", {}).get("api_key", "")
GAS_FOLDER_ID = st.secrets.get("gas", {}).get("folder_id", "")

# Signature storage format in Google Sheets:
# - Legacy: data:image/png;base64,...
# - New: gas:<fileId>
SIGNATURE_GAS_PREFIX = "gas:"
