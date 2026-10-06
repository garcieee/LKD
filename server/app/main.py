"""Lakad API: photo reports, SOS videos, place search, walking and commute routes, transit hubs and modeled foot traffic for now. Traffic and exports come later.

Run from server/: uvicorn app.main:app --host 0.0.0.0 --reload
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import CORS_ORIGINS, FOOTFALL_DIR, STORAGE_DIR, TRANSIT_DIR
from app.db.store import ReportStore
from app.routers import commute as commute_routes, footfall as footfall_routes, geocode, reports, routes, transit as transit_routes
from app.services import commute, footfall, ticket_sync, transit


def create_app(storage: Path = STORAGE_DIR) -> FastAPI:
    app = FastAPI(title="Lakad API", lifespan=ticket_sync.lifespan)
    photo_dir = storage / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    video_dir = storage / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    app.state.store = ReportStore(storage / "reports.json")
    app.state.sync = ticket_sync.TicketSync(app.state.store, storage / "lakad.db")
    app.state.photo_dir = photo_dir
    app.state.video_dir = video_dir
    app.state.hubs = transit.load_hubs(TRANSIT_DIR)
    app.state.rides = commute.load_ride_modes(TRANSIT_DIR)
    app.state.links = commute.load_links(TRANSIT_DIR, app.state.hubs)
    app.state.footfall = footfall.load_model(FOOTFALL_DIR, TRANSIT_DIR, app.state.hubs)

    app.add_middleware(
        CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
    )
    app.include_router(reports.router)
    app.include_router(geocode.router)
    app.include_router(routes.router)
    app.include_router(commute_routes.router)
    app.include_router(transit_routes.router)
    app.include_router(footfall_routes.router)
    app.mount("/photos", StaticFiles(directory=photo_dir), name="photos")
    app.mount("/videos", StaticFiles(directory=video_dir), name="videos")  # SOS clips; serves Range, so they seek

    @app.get("/health")
    def health():
        return {"ok": True, "tickets": app.state.sync.counters()}

    return app


app = create_app()
