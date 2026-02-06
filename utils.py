import pandas as pd
import base64
from io import BytesIO
from PIL import Image
import numpy as np

def safe_str(val):
    return str(val).strip()

def safe_int(val, default=999):
    try:
        return int(float(val))
    except:
        return default

def map_dict_to_row(headers, data_dict):
    row = [''] * len(headers) 
    for key, value in data_dict.items():
        if key in headers:
            idx = headers.index(key)
            row[idx] = value
    return row

def base64_to_image(base64_str):
    try:
        if not base64_str: return None
        if "," in base64_str: header, encoded = base64_str.split(",", 1)
        else: encoded = base64_str
        data = base64.b64decode(encoded)
        return Image.open(BytesIO(data))
    except:
        return None

def is_canvas_blank(image_data):
    if image_data is None: return True
    return np.std(image_data) < 1.0
