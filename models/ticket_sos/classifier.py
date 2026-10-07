"""Conservative zero-shot SOS video suggestion. A person always chooses the actual kind.

OpenCLIP compares a few silent video frames with descriptions of the three response
types. These similarities are not probabilities, so close or weak results abstain.
"""
from pathlib import Path

PROMPTS = {
    "police": (
        "A video of a violent attack or a physical fight between people.",
        "A video of a robbery, weapon, or threatening person.",
    ),
    "medical": (
        "A video of an injured person needing medical help.",
        "A video of a person collapsed or unconscious on the ground.",
    ),
    "fire_rescue": (
        "A video of a building or vehicle on fire with visible flames and smoke.",
        "A video of flooding or a person trapped and needing rescue.",
    ),
}

MIN_SIMILARITY = 0.25
MIN_MARGIN = 0.04


def suggestion(scores: dict[str, float]) -> str | None:
    """Only suggest a clear winner; never assign a response type from these scores."""
    if set(scores) != set(PROMPTS):
        return None
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if ranked[0][1] < MIN_SIMILARITY or ranked[0][1] - ranked[1][1] < MIN_MARGIN:
        return None
    return ranked[0][0]


class VideoClassifier:
    """Load model weights lazily, then reuse them for SOS clips in one server process."""

    def __init__(self):
        self.model = None
        self.preprocess = None
        self.text_features = None

    def _load(self):
        if self.model is not None:
            return
        import open_clip
        import torch

        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k", device="cpu"
        )
        model.eval()
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        labels = [prompt for prompts in PROMPTS.values() for prompt in prompts]
        with torch.inference_mode():
            features = model.encode_text(tokenizer(labels))
            features = features / features.norm(dim=-1, keepdim=True)
        self.model, self.preprocess, self.text_features = model, preprocess, features

    def classify(self, path: Path) -> str | None:
        import cv2
        import torch
        from PIL import Image

        video = cv2.VideoCapture(str(path))
        try:
            if not video.isOpened():
                return None
            count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
            # At most five frames, spread across the clip. Never upload the video to a model provider.
            offsets = [round((count - 1) * i / 4) for i in range(5)] if count > 0 else [0]
            frames = []
            for offset in dict.fromkeys(offsets):
                video.set(cv2.CAP_PROP_POS_FRAMES, offset)
                ok, frame = video.read()
                if ok:
                    frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        finally:
            video.release()
        if not frames:
            return None
        self._load()
        with torch.inference_mode():
            images = torch.stack([self.preprocess(frame) for frame in frames])
            features = self.model.encode_image(images)
            features = features / features.norm(dim=-1, keepdim=True)
            similarities = features @ self.text_features.T
        scores = {}
        for i, kind in enumerate(PROMPTS):
            scores[kind] = float(similarities[:, i * 2 : i * 2 + 2].max())
        return suggestion(scores)
