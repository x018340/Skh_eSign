import pandas as pd
import gspread
import time
from core.connection import get_sheet_object
from utils import safe_str

def api_read_with_retry(worksheet_name):
    try:
        ws = get_sheet_object(worksheet_name)
        retries = 5
        for i in range(retries):
            try:
                data = ws.get_all_records()
                return pd.DataFrame(data)
            except gspread.exceptions.APIError as e:
                if "429" in str(e):
                    time.sleep((i + 1) * 2)
                elif i == retries - 1:
                    raise e
                else:
                    time.sleep(1)
    except Exception:
        pass
    return pd.DataFrame()

# Note: The main logic for saving signatures is kept in the UI component 
# (signin_view.py) in the original version to handle the specific retry loop
# logic with st.error handling. We keep this file mainly for the read function
# to maintain the split structure without breaking logic.
