import base64
from io import BytesIO
from typing import Optional, Tuple

import numpy as np
from PIL import Image
import requests

from config import SIGNATURE_GAS_PREFIX, GAS_UPLOAD_URL, GAS_API_KEY

def safe_str(val) -> str:
    return str(val).strip()

def safe_int(val, default=999) -> int:
    try:
        return int(float(val))
    except Exception:
        return default

def map_dict_to_row(headers, data_dict):
    row = [''] * len(headers)
    for key, value in data_dict.items():
        if key in headers:
            idx = headers.index(key)
            row[idx] = value
    return row

def base64_to_image(base64_str: str) -> Optional[Image.Image]:
    try:
        if not base64_str: return None
        if "," in base64_str:
            _, encoded = base64_str.split(",", 1)
        else:
            encoded = base64_str
        data = base64.b64decode(encoded)
        return Image.open(BytesIO(data))
    except Exception:
        return None

def is_canvas_blank(image_data) -> bool:
    if image_data is None: return True
    return np.std(image_data) < 1.0

def parse_signature_value(sig_val: str) -> Tuple[str, str]:
    if not sig_val:
        return ("empty", "")
    s = str(sig_val).strip()
    if s.startswith(SIGNATURE_GAS_PREFIX):
        return ("gas", s[len(SIGNATURE_GAS_PREFIX):].strip())
    return ("base64", s)

def _gas_download_file_as_image(file_id: str) -> Optional[Image.Image]:
    if not GAS_UPLOAD_URL or not GAS_API_KEY:
        return None
    try:
        r = requests.get(
            GAS_UPLOAD_URL,
            params={"action": "download", "fileId": file_id, "api_key": GAS_API_KEY},
            timeout=20,
        )
        r.raise_for_status()
        js = r.json()
        if not js.get("ok"):
            return None
        data_b64 = js.get("data_base64", "")
        if not data_b64:
            return None
        data = base64.b64decode(data_b64)
        return Image.open(BytesIO(data))
    except Exception:
        return None

def image_from_signature_value(sig_val: str) -> Optional[Image.Image]:
    kind, payload = parse_signature_value(sig_val)
    if kind == "empty":
        return None
    if kind == "base64":
        return base64_to_image(payload)
    if kind == "gas":
        return _gas_download_file_as_image(payload)
    return None

def make_white_background_transparent(img: Image.Image, threshold: int = 245) -> Image.Image:
    """
    Convert near-white pixels to transparent. Keeps strokes intact.
    threshold: 0-255, higher = only pure whites removed, lower = more aggressive.
    """
    if img is None:
        return img

    rgba = img.convert("RGBA")
    datas = rgba.getdata()

    new_data = []
    for r, g, b, a in datas:
        # Treat near-white as background
        if r >= threshold and g >= threshold and b >= threshold:
            new_data.append((r, g, b, 0))   # transparent
        else:
            new_data.append((r, g, b, 255)) # fully opaque strokes
    rgba.putdata(new_data)
    return rgba
