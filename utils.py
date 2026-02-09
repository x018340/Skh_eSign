import base64
from io import BytesIO
from typing import Optional, Tuple

import numpy as np
from PIL import Image

from config import SIGNATURE_DRIVE_PREFIX

def safe_str(val) -> str:
    return str(val).strip()

def safe_int(val, default=999) -> int:
    try:
        return int(float(val))
    except Exception:
        return default

def map_dict_to_row(headers, data_dict):
    row = [""] * len(headers)
    for key, value in data_dict.items():
        if key in headers:
            idx = headers.index(key)
            row[idx] = value
    return row

def base64_to_image(base64_str: str) -> Optional[Image.Image]:
    try:
        if not base64_str:
            return None
        if "," in base64_str:
            _, encoded = base64_str.split(",", 1)
        else:
            encoded = base64_str
        data = base64.b64decode(encoded)
        return Image.open(BytesIO(data))
    except Exception:
        return None

def is_canvas_blank(image_data) -> bool:
    if image_data is None:
        return True
    return np.std(image_data) < 1.0

def parse_signature_value(sig_val: str) -> Tuple[str, str]:
    """Return ('drive', file_id) or ('base64', raw_string) or ('empty','')."""
    if not sig_val:
        return ("empty", "")
    s = str(sig_val).strip()
    if s.startswith(SIGNATURE_DRIVE_PREFIX):
        return ("drive", s[len(SIGNATURE_DRIVE_PREFIX):].strip())
    return ("base64", s)

def image_from_signature_value(sig_val: str, drive_service=None) -> Optional[Image.Image]:
    """Load signature image from either base64 or Drive file id."""
    kind, payload = parse_signature_value(sig_val)
    if kind == "empty":
        return None
    if kind == "base64":
        return base64_to_image(payload)
    if kind == "drive":
        if drive_service is None:
            return None
        try:
            # Drive v3: files().get_media(fileId=...).execute() returns bytes
            data = drive_service.files().get_media(fileId=payload).execute()
            return Image.open(BytesIO(data))
        except Exception:
            return None
    return None
