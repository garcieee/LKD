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
