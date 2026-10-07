"""Faces are blurred silently before a report photo is saved; any failure keeps the photo as it came."""
import cv2
import numpy as np

from app.services import face_blur


def _encode(image, ext="jpg"):
    return cv2.imencode(f".{ext}", image)[1].tobytes()


def test_a_photo_without_faces_is_saved_untouched():
    noise = np.random.default_rng(0).integers(0, 255, (240, 320, 3), dtype=np.uint8)
    data = _encode(noise)
    assert face_blur.blur_faces(data, "jpg") == data


def test_bytes_that_are_not_an_image_are_kept_as_they_came():
    data = b"\xff\xd8\xff" + b"\x00" * 64
    assert face_blur.blur_faces(data, "jpg") == data


def test_a_detected_face_is_blurred(monkeypatch):
    image = np.random.default_rng(1).integers(0, 255, (300, 400, 3), dtype=np.uint8)

    class Stub:
        def detectMultiScale(self, *a, **k):
            return np.array([[100, 80, 90, 90]])

    monkeypatch.setattr(face_blur, "_cascades", [Stub()])
    out = cv2.imdecode(np.frombuffer(face_blur.blur_faces(_encode(image, "png"), "png"), np.uint8), cv2.IMREAD_COLOR)
    face = (slice(95, 165), slice(115, 185))
    assert out[face].std() < image[face].std() / 2  # the face is smoothed
    assert (out[:60] == image[:60]).all()  # the rest is untouched



def test_a_photo_over_the_pixel_cap_is_kept_as_it_came(monkeypatch):
    monkeypatch.setattr(face_blur, "MAX_PIXELS", 100)
    data = _encode(np.zeros((40, 40, 3), dtype=np.uint8))
    assert face_blur.blur_faces(data, "jpg") == data
