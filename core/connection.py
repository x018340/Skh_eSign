import time
import streamlit as st
import gspread

from config import SHEET_NAME

try:
    from google.oauth2.service_account import Credentials
except Exception:  # pragma: no cover
    Credentials = None

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource
def get_credentials():
    creds_dict = dict(st.secrets["gcp_service_account"])
    if Credentials is None:
        raise ImportError("Missing google-auth. Install: google-auth")
    return Credentials.from_service_account_info(creds_dict, scopes=SHEETS_SCOPES)

@st.cache_resource
def get_gspread_client():
    creds = get_credentials()
    return gspread.authorize(creds)

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
