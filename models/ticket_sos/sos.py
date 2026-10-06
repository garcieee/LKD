"""An SOS (the app's hold-to-record video) is someone asking for help, not a hazard, so it skips matching and scoring:
it opens its own ticket at priority 100, band Critical, and the dashboard lists every open SOS above every hazard, the
unsorted ones first. A person at the dashboard watches the clip and sorts it by who must respond (KINDS).

Plain Python, no I/O. tickets/engine.py calls it.
"""

CATEGORY = "sos"
PRIORITY, BAND = 100.0, "Critical"  # 100 is the cap a hazard's score can only reach
# Who must respond, in the order the dashboard shows them, with the hint it shows under each. Mirrored by
# server/app/db/models.py SosKind and dashboard/src/types/api.ts.
KINDS = {
    "police": "Crime, violence or a threat",
    "medical": "Injury, collapse or illness",
    "fire_rescue": "Fire, flood or someone trapped",
}


def is_sos(report: dict) -> bool:
    return report["category"] == CATEGORY


def flags(review: list[str]) -> dict:
    """The SOS ticket's breakdown: no score to explain, and the kind, not an office, says who handles it."""
    return {"sos": True, "review": review}


def check_kind(kind) -> str:
    """The kind, or ValueError when it is not one of KINDS."""
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError(f"Unknown SOS kind: {kind!r}")
    return kind
