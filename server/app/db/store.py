"""Reports live in one JSON file, server/storage/reports.json. Photos sit next to it in photos/.

ponytail: one file and one lock is enough for a demo on one server process. Past a few thousand
reports, or with more than one process, move to SQLite (stdlib sqlite3).
"""
import json
import os
import threading
from pathlib import Path


class ReportStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # FastAPI runs sync routes on a thread pool

    def all(self) -> list[dict]:
        with self._lock:
            return self._read()

    def add(self, report: dict) -> dict:
        with self._lock:
            reports = self._read()
            reports.append(report)
            self._write(reports)
        return report

    def update(self, report_id: str, **fields) -> dict | None:
        with self._lock:
            reports = self._read()
            for report in reports:
                if report["id"] == report_id:
                    report.update(fields)
                    self._write(reports)
                    return report
        return None

    def remove(self, report_ids) -> int:
        """Drops these reports from the file and returns how many went. Their tickets keep them in lakad.db."""
        ids = set(report_ids)
        with self._lock:
            reports = self._read()
            kept = [r for r in reports if r["id"] not in ids]
            if len(kept) < len(reports):
                self._write(kept)
        return len(reports) - len(kept)

    def _read(self) -> list[dict]:
        try:
            reports = json.loads(self.path.read_text())
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            reports = None
        if isinstance(reports, list):
            return reports
        # Not a list (hand-edited, or cut off): every report would fail on it. Keep the file as it was, aside, and start empty.
        self.path.replace(self.path.with_suffix(".json.bad"))
        return []

    def _write(self, reports: list[dict]) -> None:
        # Temp file, then rename: a crash mid-write never leaves half a JSON file behind.
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(reports, indent=2))
        os.replace(tmp, self.path)
