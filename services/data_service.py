import time
from io import BytesIO
from typing import Optional

import gspread
import pandas as pd
import requests

from core.connection import get_sheet_object
from config import GAS_UPLOAD_URL, GAS_API_KEY, GAS_FOLDER_ID, SIGNATURE_GAS_PREFIX
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
                    raise
                else:
                    time.sleep(1)
    except Exception:
        pass
    return pd.DataFrame()


def _find_attendee_row(ws, attendee_name: str, meeting_id: str):
    all_rows = ws.get_all_values()
    headers = all_rows[0]
    name_idx = headers.index("AttendeeName")
    mid_idx = headers.index("MeetingID")
    status_col = headers.index("Status") + 1
    sig_col = headers.index("SignatureBase64") + 1  # keep same column name for compatibility

    row_update_idx = -1
    for i, r in enumerate(all_rows):
        if i == 0:
            continue
        if safe_str(r[name_idx]) == safe_str(attendee_name) and safe_str(r[mid_idx]) == safe_str(meeting_id):
            row_update_idx = i + 1
            break
    return row_update_idx, status_col, sig_col


def upload_signature_png_to_gas(png_bytes: bytes, meeting_id: str, attendee_name: str) -> str:
    if not (GAS_UPLOAD_URL and GAS_API_KEY and GAS_FOLDER_ID):
        raise RuntimeError("GAS not configured: set [gas] upload_url/api_key/folder_id in Streamlit secrets.")

    import base64
    data_b64 = base64.b64encode(png_bytes).decode("utf-8")
    payload = {
        "action": "upload",
        "api_key": GAS_API_KEY,
        "folderId": GAS_FOLDER_ID,
        "filename": f"signature_mid{meeting_id}_{safe_str(attendee_name)}.png",
        "mimeType": "image/png",
        "data_base64": data_b64,
    }
    r = requests.post(GAS_UPLOAD_URL, json=payload, timeout=30)
    r.raise_for_status()
    js = r.json()
    if not js.get("ok") or not js.get("fileId"):
        raise RuntimeError(f"GAS upload failed: {js}")
    return js["fileId"]


def save_signature(mid_param: str, attendee_name: str, png_bytes: bytes, retries: int = 10) -> None:
    """Persist signature: upload PNG to GAS/Drive then write gas:<fileId> to sheet."""
    ws_attendees = get_sheet_object("Meeting_Attendees")

    file_id = upload_signature_png_to_gas(png_bytes, meeting_id=str(mid_param), attendee_name=attendee_name)
    sig_value = f"{SIGNATURE_GAS_PREFIX}{file_id}"

    row_update_idx, status_col, sig_col = _find_attendee_row(ws_attendees, attendee_name, str(mid_param))
    if row_update_idx <= 0:
        raise ValueError("Record not found on server.")

    for i in range(retries):
        try:
            ws_attendees.batch_update(
                [
                    {"range": gspread.utils.rowcol_to_a1(row_update_idx, status_col), "values": [["Signed"]]},
                    {"range": gspread.utils.rowcol_to_a1(row_update_idx, sig_col), "values": [[sig_value]]},
                ]
            )
            return
        except gspread.exceptions.APIError as e:
            if i == retries - 1:
                raise
            time.sleep(2 + i)
