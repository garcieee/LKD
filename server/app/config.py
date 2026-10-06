"""Reads server/.env. Relative paths are relative to server/."""
import os
from pathlib import Path

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parent.parent
load_dotenv(SERVER_DIR / ".env")

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174").split(",")
    if o.strip()
]

# reports.json and photos/, created at runtime (git-ignored).
STORAGE_DIR = SERVER_DIR / os.getenv("STORAGE_DIR", "storage")

# west,south,east,north of the city reports are accepted for. Mirrors dashboard/src/config/makati.ts.
CITY_BOUNDS = tuple(
    float(v) for v in os.getenv("CITY_BOUNDS", "120.9987,14.5296,121.0501,14.5796").split(",")
)
