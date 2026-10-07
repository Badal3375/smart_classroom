import base64
import cv2
import numpy as np


def decode_b64(data_url):
    """'data:image/jpeg;base64,...' -> BGR ndarray (or None). Images exist only in memory."""
    if not data_url:
        return None
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    try:
        buf = np.frombuffer(base64.b64decode(data_url), np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        return None


def decode_file(f):
    try:
        return cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def limit_size(img, max_side=960):
    if img is None:
        return None
    h, w = img.shape[:2]
    s = max_side / max(h, w)
    return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img
