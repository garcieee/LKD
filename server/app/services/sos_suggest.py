"""Background SOS suggestions. The urgent report is saved before inference starts."""
import logging
import threading
import time
from pathlib import Path

from models.ticket_sos.classifier import VideoClassifier

log = logging.getLogger(__name__)


class SosSuggestionWorker:
    def __init__(self, store, video_dir: Path, classifier=None):
        self.store = store
        self.video_dir = video_dir
        self.classifier = classifier or VideoClassifier()
        self._stop = threading.Event()
        self._thread = None

    def tick(self) -> None:
        for report in self.store.all():
            if report.get("category") != "sos" or report.get("sos_suggestion_checked"):
                continue
            if report.get("sos_suggestion_retry_at", 0) > time.time():
                continue
            if report.get("sos_kind") or report.get("status") in ("fixed", "rejected"):
                self.store.update(report["id"], sos_suggestion_checked=True)
                continue
            video = self.video_dir / Path(report["video_url"]).name
            try:
                kind = self.classifier.classify(video)
            except Exception:
                log.exception("SOS suggestion unavailable for %s", report["id"])
                attempts = report.get("sos_suggestion_attempts", 0) + 1
                self.store.update(
                    report["id"], sos_suggestion_attempts=attempts,
                    sos_suggestion_retry_at=time.time() + min(300 * attempts, 1800),
                )
                continue
            # Staff may have sorted it while the model loaded. Never replace their decision.
            current = next((r for r in self.store.all() if r["id"] == report["id"]), None)
            if current and not current.get("sos_kind"):
                self.store.update(report["id"], suggested_sos_kind=kind, sos_suggestion_checked=True)

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sos-suggestion", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("SOS suggestion pass failed")
            self._stop.wait(5)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
