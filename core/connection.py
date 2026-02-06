import streamlit as st
import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials
from config import GCP_CREDS, SHEET_NAME

@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(GCP_CREDS), scope)
    return gspread.authorize(creds)

def get_sheet_object(worksheet_name):
    client = get_gspread_client()
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
