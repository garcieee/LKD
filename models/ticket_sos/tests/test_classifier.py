from models.ticket_sos.classifier import suggestion


def test_suggestion_abstains_for_weak_or_close_video_evidence():
    assert suggestion({"police": 0.23, "medical": 0.18, "fire_rescue": 0.16}) is None
    assert suggestion({"police": 0.30, "medical": 0.28, "fire_rescue": 0.12}) is None
    assert suggestion({"police": 0.31, "medical": 0.19}) is None


def test_suggestion_only_returns_a_clear_type():
    assert suggestion({"police": 0.11, "medical": 0.29, "fire_rescue": 0.18}) == "medical"


def test_video_frames_reach_the_three_type_comparison(tmp_path):
    import cv2
    import numpy as np
    import torch

    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5, (32, 32))
    assert writer.isOpened()
    for _ in range(5):
        writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
    writer.release()

    from models.ticket_sos.classifier import VideoClassifier

    class FakeModel:
        def encode_image(self, images):
            return images

    classifier = VideoClassifier()
    classifier.model = FakeModel()
    classifier.preprocess = lambda frame: torch.tensor([0.0, 1.0, 0.0])
    classifier.text_features = torch.tensor([
        [1.0, 0.0, 0.0], [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0], [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0], [0.0, 0.0, 1.0],
    ])
    assert classifier.classify(path) == "medical"


def _clip(tmp_path, make):
    import cv2

    path = tmp_path / "c.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 8, (160, 120))
    for i in range(24):
        writer.write(make(i))
    writer.release()
    return path


def test_flickering_flames_nudge_fire_and_rescue(tmp_path):
    import numpy as np

    from models.ticket_sos import cues

    def flames(i):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        frame[40:100, 40:120] = (0, 140 + 40 * (i % 2), 255)  # bright orange, size changes: it flickers
        frame[40 : 40 + 10 * (i % 3), 40:120] = (0, 0, 0)
        return frame

    assert cues.boosts(_clip(tmp_path, flames)).get("fire_rescue")


def test_a_still_dark_clip_has_no_cues(tmp_path):
    import numpy as np

    from models.ticket_sos import cues

    assert cues.boosts(_clip(tmp_path, lambda i: np.zeros((120, 160, 3), dtype=np.uint8))) == {}
    assert cues.boosts(tmp_path / "missing.mp4") == {}


def test_a_clip_with_no_frame_count_is_still_read(monkeypatch, tmp_path):
    """A browser WebM reports no length: the cues fall back to reading the clip in order."""
    import numpy as np

    from models.ticket_sos import cues

    class NoCount:
        def __init__(self, path):
            self.n = 0

        def isOpened(self):
            return True

        def get(self, prop):
            return 0

        def read(self):
            self.n += 1
            return (self.n <= 200), np.zeros((120, 160, 3), dtype=np.uint8)

        def release(self):
            pass

    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", NoCount)
    assert len(cues._frames(tmp_path / "x.webm")) == cues.SAMPLES
