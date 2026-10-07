"""OpenCV motion and colour cues from an SOS clip, to back up the OpenCLIP comparison. Cheap: small frames, no weights.

Fire: a flickering patch of bright orange/yellow. Violence: sustained, large frame-to-frame motion. A cue only nudges
the similarity of its own type; it never assigns one, and a person still sorts every SOS.
"""
from pathlib import Path

SAMPLES = 16  # frames read, spread across the clip
WIDTH = 160  # frames are shrunk to this width first
SEQUENTIAL_STEP = 6  # for a clip with no frame count: keep one frame in this many

FLAME_MIN_RATIO = 0.02  # share of pixels that look like flame, at the median frame
FLAME_MIN_FLICKER = 0.004  # how much that share changes between frames
MOTION_MIN = 18.0  # mean brightness change (0..255) between sampled frames

FIRE_BOOST = 0.06
MOTION_BOOST = 0.03


def _small(frame):
    import cv2

    scale = WIDTH / frame.shape[1]
    return cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def _frames(path: Path):
    import cv2

    video = cv2.VideoCapture(str(path))
    try:
        if not video.isOpened():
            return []
        count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        frames = []
        if count > 0:
            for offset in dict.fromkeys(round((count - 1) * i / (SAMPLES - 1)) for i in range(SAMPLES)):
                video.set(cv2.CAP_PROP_POS_FRAMES, offset)
                ok, frame = video.read()
                if ok:
                    frames.append(_small(frame))
        else:  # a WebM from a browser reports no length: read on, keeping every few frames
            for i in range(SAMPLES * SEQUENTIAL_STEP):
                ok, frame = video.read()
                if not ok:
                    break
                if i % SEQUENTIAL_STEP == 0:
                    frames.append(_small(frame))
        return frames
    finally:
        video.release()


def measure(frames) -> tuple[float, float, float]:
    """(flame ratio at the median frame, its flicker, mean motion) of already-shrunk BGR frames."""
    import cv2
    import numpy as np

    if len(frames) < 2:
        return 0.0, 0.0, 0.0
    ratios, grays = [], []
    for frame in frames:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        flame = cv2.inRange(hsv, (0, 120, 190), (35, 255, 255))  # orange to yellow, saturated and bright
        ratios.append(float((flame > 0).mean()))
        grays.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32))
    motion = float(np.mean([np.abs(a - b).mean() for a, b in zip(grays, grays[1:])]))
    return float(np.median(ratios)), float(np.std(ratios)), motion


def boosts(path: Path) -> dict[str, float]:
    """Similarity nudges per kind. Empty when the clip cannot be read or shows nothing notable."""
    try:
        ratio, flicker, motion = measure(_frames(path))
    except Exception:
        return {}
    out = {}
    if ratio >= FLAME_MIN_RATIO and flicker >= FLAME_MIN_FLICKER:
        out["fire_rescue"] = FIRE_BOOST
    if motion >= MOTION_MIN:
        out["police"] = MOTION_BOOST
    return out
