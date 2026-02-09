import time
from io import BytesIO
from typing import Optional

import gspread
import pandas as pd

from config import DRIVE_SIGNATURE_FOLDER_ID, SIGNATURE_DRIVE_PREFIX
from core.connection import get_drive_service, get_sheet_object
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


def upload_signature_png_to_drive(png_bytes: bytes, meeting_id: str, attendee_name: str) -> str:
    """Upload signature PNG bytes to the shared Drive folder and return fileId."""
    drive = get_drive_service()
    file_metadata = {
        "name": f"signature_mid{meeting_id}_{attendee_name}.png",
        "parents": [DRIVE_SIGNATURE_FOLDER_ID],
        "mimeType": "image/png",
    }

    # googleapiclient expects MediaIoBaseUpload
    from googleapiclient.http import MediaIoBaseUpload  # local import for clearer dependency errors
    media = MediaIoBaseUpload(BytesIO(png_bytes), mimetype="image/png", resumable=False)

    created = drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return created["id"]


def save_signature(mid_param: str, attendee_name: str, png_bytes: bytes, retries: int = 10) -> None:
    """Persist signature: upload PNG to Drive then write drive:<fileId> to sheet."""
    ws_attendees = get_sheet_object("Meeting_Attendees")

    # Upload to Drive first (so a failed sheet write doesn't lose the signature)
    file_id = upload_signature_png_to_drive(png_bytes, meeting_id=str(mid_param), attendee_name=safe_str(attendee_name))
    sig_value = f"{SIGNATURE_DRIVE_PREFIX}{file_id}"

    row_update_idx, status_col, sig_col = _find_attendee_row(ws_attendees, attendee_name, str(mid_param))
    if row_update_idx <= 0:
        raise ValueError("Record not found on server.")

    for i in range(retries):
        try:
            ws_attendees.batch_update([
                {"range": gspread.utils.rowcol_to_a1(row_update_idx, status_col), "values": [["Signed"]]},
                {"range": gspread.utils.rowcol_to_a1(row_update_idx, sig_col), "values": [[sig_value]]},
            ])
            return
        except gspread.exceptions.APIError as e:
            if i == retries - 1:
                raise
            time.sleep(2 + i)
