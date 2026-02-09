import streamlit as st
import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build # NEW
from config import SHEET_NAME

@st.cache_resource
def get_services():
    # We use the same credentials for both Sheets and Drive
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    # 1. Sheets Client
    client_sheets = gspread.authorize(creds)
    
    # 2. Drive Client (NEW)
    service_drive = build('drive', 'v3', credentials=creds)
    
    return client_sheets, service_drive

def get_sheet_object(worksheet_name):
    client, _ = get_services() # Update to use the new common provider
    retries = 3
    for i in range(retries):
        try:
            return client.open(SHEET_NAME).worksheet(worksheet_name)
        except gspread.exceptions.APIError as e:
            if "429" in str(e):
                time.sleep(2 + i)
            elif i == retries - 1:
                raise e
            else:
                time.sleep(1)
    return client.open(SHEET_NAME).worksheet(worksheet_name)
