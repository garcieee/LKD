from pathlib import Path

from app.db.store import ReportStore
from app.services.sos_suggest import SosSuggestionWorker


class Classifier:
    def __init__(self):
        self.calls = []

    def classify(self, path):
        self.calls.append(path)
        return "medical"


def test_suggestion_does_not_sort_an_sos(tmp_path):
    store = ReportStore(tmp_path / "reports.json")
    store.add({"id": "one", "category": "sos", "video_url": "/videos/one.mp4", "status": "open"})
    classifier = Classifier()
    worker = SosSuggestionWorker(store, tmp_path / "videos", classifier)
    worker.tick()
    report = store.all()[0]
    assert report["suggested_sos_kind"] == "medical"
    assert "sos_kind" not in report
    assert classifier.calls == [Path(tmp_path / "videos/one.mp4")]
    worker.tick()
    assert len(classifier.calls) == 1


def test_human_choice_is_never_replaced(tmp_path):
    store = ReportStore(tmp_path / "reports.json")
    store.add({"id": "one", "category": "sos", "video_url": "/videos/one.mp4", "status": "open"})

    class SlowChoice:
        def classify(self, path):
            store.update("one", sos_kind="police")
            return "medical"

    SosSuggestionWorker(store, tmp_path / "videos", SlowChoice()).tick()
    assert store.all()[0]["sos_kind"] == "police"
    assert "suggested_sos_kind" not in store.all()[0]
