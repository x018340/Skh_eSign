import time
import streamlit as st
import gspread

from config import SHEET_NAME

# Prefer modern google-auth + google-api-python-client for Drive upload/download.
# If these packages are missing in your environment, add to requirements.txt:
#   google-auth
#   google-api-python-client
try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
except Exception:  # pragma: no cover
    Credentials = None
    build = None


SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource
def get_credentials():
    creds_dict = dict(st.secrets["gcp_service_account"])
    if Credentials is None:
        raise ImportError(
            "Missing google-auth / google-api-python-client. "
            "Install: google-auth, google-api-python-client"
        )
    return Credentials.from_service_account_info(creds_dict, scopes=SHEETS_SCOPES)


@st.cache_resource
def get_gspread_client():
    creds = get_credentials()
    return gspread.authorize(creds)


@st.cache_resource
def get_drive_service():
    creds = get_credentials()
    if build is None:
        raise ImportError(
            "Missing google-api-python-client. Install: google-api-python-client"
        )
    # cache_discovery=False reduces some hosting issues
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def get_sheet_object(worksheet_name: str):
    client = get_gspread_client()
    retries = 3
    for i in range(retries):
        try:
            return client.open(SHEET_NAME).worksheet(worksheet_name)
        except gspread.exceptions.APIError as e:
            if "429" in str(e):
                time.sleep(2 + i)
            elif i == retries - 1:
                raise
            else:
                time.sleep(1)
    return client.open(SHEET_NAME).worksheet(worksheet_name)
