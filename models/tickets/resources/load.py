"""Reads the static files in this folder. The one place the rule code's inputs come off disk."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _read(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def load_places() -> list[tuple[float, float, str, str]]:
    """(lat, lng, kind, name) for each nearby place that draws foot traffic."""
    return [tuple(p) for p in _read("places.json")["places"]]
