"""Blur faces in a report photo before it is saved. OpenCV's bundled Haar cascade: no weights to download.

Silent by design: the API, the report and the apps show nothing about it. If anything goes wrong the photo is kept
as it came, so a report is never lost to the blur. Photos only: an SOS clip is saved untouched so a person (and the
video model) can see what is happening.
"""
import io
import logging
import threading

log = logging.getLogger(__name__)

MAX_PIXELS = 48_000_000  # a 10 MB file can decode to far more than this: skip those rather than fill memory
DETECT_SIDE = 960  # faces are searched for on a copy shrunk to this long side: a 12 MP photo stays fast

_cascades = None
_lock = threading.Lock()  # a cascade is not safe to share between the server's request threads


def _load():
    global _cascades
    if _cascades is None:
        import cv2

        names = ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")
        _cascades = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in names]
    return _cascades


def _too_big(data: bytes) -> bool:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:  # reads the header only
        return img.width * img.height > MAX_PIXELS


def blur_faces(data: bytes, ext: str) -> bytes:
    """The photo with every detected face blurred, or the same bytes when there is none (or on any error)."""
    try:
        import cv2
        import numpy as np

        if _too_big(data):
            return data
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return data
        height, width = image.shape[:2]
        shrink = min(1.0, DETECT_SIDE / max(height, width))
        small = cv2.resize(image, None, fx=shrink, fy=shrink, interpolation=cv2.INTER_AREA) if shrink < 1 else image
        gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
        floor = max(24, min(gray.shape) // 20)  # ignore specks: a face under ~5% of the short side
        boxes = []
        with _lock:
            for cascade in _load():
                found = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(floor, floor))
                boxes.extend(tuple(int(v / shrink) for v in b) for b in found)
        if not boxes:
            return data
        for x, y, w, h in boxes:
            pad = w // 6
            x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(width, x + w + pad), min(height, y + h + pad)
            kernel = (max(3, (x1 - x0) // 3) | 1, max(3, (y1 - y0) // 3) | 1)  # odd, scaled to the face
            image[y0:y1, x0:x1] = cv2.GaussianBlur(image[y0:y1, x0:x1], kernel, 0)
        ok, out = cv2.imencode(f".{ext}", image, [cv2.IMWRITE_JPEG_QUALITY, 90] if ext == "jpg" else [])
        return out.tobytes() if ok else data
    except Exception:
        log.exception("face blur skipped")
        return data
