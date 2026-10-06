"""Reads the static files in this folder. The one place the rule code's inputs come off disk."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _read(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def load_places() -> list[tuple[float, float, str, str]]:
    """(lat, lng, kind, name) for each nearby place that draws foot traffic."""
    return [tuple(p) for p in _read("places.json")["places"]]


def load_lexicon() -> dict:
    """The word lists: categories, danger and negators (see lexicon.json)."""
    return _read("lexicon.json")


def load_offices() -> dict[str, str]:
    """Which office handles which category. Keys starting with an underscore are notes, not categories."""
    return {k: v for k, v in _read("offices.json").items() if not k.startswith("_")}


def load_districts() -> list[tuple[int, str, tuple[float, float, float, float], list]]:
    """(district_id, barangay, (west, south, east, north), rings) per barangay, rings as closed [lng, lat] lists."""
    out = []
    for b in _read("districts.json")["barangays"]:
        lngs, lats = zip(*(p for ring in b["rings"] for p in ring))
        out.append((b["district_id"], b["name"], (min(lngs), min(lats), max(lngs), max(lats)), b["rings"]))
    return out
