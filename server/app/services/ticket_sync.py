"""The ticket loop: every SYNC_EVERY_S, engine.sync_once gives new reports their ticket, district and priority, saves
them to db/lakad.db and writes the outcome back onto reports.json. Plan: models/tickets/ATTACH.md.

The app's lifespan starts and stops it (TICKETS_SYNC=1). A plain TestClient(app), not used as a context manager,
never runs the lifespan, so tests drive the loop with tick().
"""
import logging
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from app import config

# ponytail: models/ sits at the repo root beside server/, so the root goes on the import path. Make models/ an
# installable package if the server ever ships without the rest of the repo.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from models.tickets import engine, settings  # noqa: E402

log = logging.getLogger(__name__)


class TicketSync:
    def __init__(self, store, db_path: Path):
        self.store = store
        self.db = engine.database(db_path)
        self.world: engine.World | None = None  # read on the first turn
        self.last_run: str | None = None
        self._stop = threading.Event()

    def tick(self, now: float | None = None) -> engine.SyncStats:
        """One turn of the loop."""
        self.world = self.world or engine.load_world()
        stats = engine.sync_once(self.store, self.world, self.db, now)
        self.last_run = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return stats

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # a bad turn is logged and the next one tries again: the loop never dies
                log.exception("ticket sync turn failed")
            self._stop.wait(settings.SYNC_EVERY_S)

    def start(self) -> None:
        self._stop.clear()
        threading.Thread(target=self._run, name="ticket-sync", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def counters(self) -> dict:
        """For /health: reports waiting for a ticket, those that gave up, and when the last turn finished."""
        return {**engine.backlog(self.store), "last_run": self.last_run}


@asynccontextmanager
async def lifespan(app):
    if config.TICKETS_SYNC:
        app.state.sync.start()
    yield
    app.state.sync.stop()
