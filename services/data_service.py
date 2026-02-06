import pandas as pd
import gspread
import time
from core.connection import get_sheet_object

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

def save_signature_to_sheet(mid, name, base64_sig):
    """Identical Base64 save logic."""
    ws = get_sheet_object("Meeting_Attendees")
    all_rows = ws.get_all_values()
    headers = all_rows[0]
    
    name_idx = headers.index("AttendeeName")
    mid_idx = headers.index("MeetingID")
    status_idx = headers.index("Status") + 1
    sig_idx = headers.index("SignatureBase64") + 1

    row_update_idx = -1
    for i, r in enumerate(all_rows):
        if i == 0: continue
        if str(r[name_idx]).strip() == str(name).strip() and str(r[mid_idx]) == str(mid):
            row_update_idx = i + 1
            break
    
    if row_update_idx > 0:
        retries = 10
        for i in range(retries):
            try:
                ws.batch_update([
                    {'range': gspread.utils.rowcol_to_a1(row_update_idx, status_idx), 'values': [['Signed']]},
                    {'range': gspread.utils.rowcol_to_a1(row_update_idx, sig_idx), 'values': [[base64_sig]]}
                ])
                return True
            except:
                time.sleep(2 + i)
    return False
