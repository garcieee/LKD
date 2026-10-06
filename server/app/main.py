"""Lakad API: photo reports and place search for now. Routing, traffic and exports come later.

Run from server/: uvicorn app.main:app --host 0.0.0.0 --reload
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import CORS_ORIGINS, STORAGE_DIR
from app.db.store import ReportStore
from app.routers import geocode, reports


def create_app(storage: Path = STORAGE_DIR) -> FastAPI:
    app = FastAPI(title="Lakad API")
    photo_dir = storage / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    app.state.store = ReportStore(storage / "reports.json")
    app.state.photo_dir = photo_dir

    app.add_middleware(
        CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
    )
    app.include_router(reports.router)
    app.include_router(geocode.router)
    app.mount("/photos", StaticFiles(directory=photo_dir), name="photos")

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
