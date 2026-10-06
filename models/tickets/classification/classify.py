"""Danger flags, category hints and report quality, from the note and what the phone sent. Word lists, no model.

The lists live in resources/lexicon.json. The caller loads them and passes a Lexicon in, so nothing here touches
disk. Matching is on whole words after lowercasing and removing accents and punctuation, so "bahay" (house) never
matches "baha" (flood). A negator just before a danger word cancels it ("walang bata", "hindi delikado") but only
inside its own clause: a comma, or a word like "pero" (but), ends its reach. Category words are not negated because
"walang ilaw" means the light is out.
"""
import math
import re
import unicodedata
from dataclasses import dataclass

from .. import settings as s


def tokens(text: str) -> list[str]:
    """Lowercase words with accents, punctuation and apostrophes removed: "Dasmariñas, don't!" -> dasmarinas dont."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c)).replace("'", "").replace("’", "")
    return re.findall(r"[a-z0-9]+", text)


def _find(words: list[str], term: tuple[str, ...]) -> list[int]:
    n = len(term)
    return [i for i in range(len(words) - n + 1) if tuple(words[i : i + n]) == term] if n else []


def _weight(term: tuple[str, ...]) -> float:
    return s.PHRASE_WEIGHT if len(term) > 1 else 1.0


@dataclass(frozen=True)
class Hint:
    category: str
    score: float  # matched evidence for this category
    margin: float  # how far ahead of the runner-up
    terms: tuple[str, ...]  # what matched, so staff can see why


class Lexicon:
    """The word lists from lexicon.json, tokenised once."""

    def __init__(self, data: dict):
        split = lambda terms: [t for t in (tuple(tokens(x)) for x in terms) if t]
        self.categories = {category: split(terms) for category, terms in data["categories"].items()}
        self.danger = split(data["danger"])
        self.negators = {w for x in data["negators"] for w in tokens(x)}
        self.boundaries = {w for x in data.get("boundaries", []) for w in tokens(x)}


def category_scores(note: str, lex: Lexicon) -> dict[str, float]:
    """Matched evidence for every category: the continuous score the evaluation draws its curves from."""
    words = tokens(note)
    return {c: sum(_weight(t) for t in terms if _find(words, t)) for c, terms in lex.categories.items()}


def category_hint(note: str, lex: Lexicon) -> Hint | None:
    """The category the note describes, or None when it does not say or is torn between two. Only ever a hint for staff."""
    words = tokens(note)
    scored = []
    for category, terms in lex.categories.items():
        hits = [t for t in terms if _find(words, t)]
        scored.append((sum(_weight(t) for t in hits), category, hits))
    scored.sort(key=lambda row: -row[0])  # stable: a tie keeps the lexicon's order
    top, category, hits = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if top < s.HINT_MIN_SCORE or top - second < s.HINT_MIN_MARGIN:
        return None
    return Hint(category, top, top - second, tuple(" ".join(t) for t in hits))


def _clauses(note: str, lex: Lexicon) -> list[list[str]]:
    """The note's words split at punctuation and at words like "pero", so a negator cannot reach across them."""
    clauses = []
    for part in re.split(r"[,.;:!?\n]+", note):
        current: list[str] = []
        for word in tokens(part):
            if word in lex.boundaries:
                if current:
                    clauses.append(current)
                current = []
            else:
                current.append(word)
        if current:
            clauses.append(current)
    return clauses


def _danger_hits(note: str, lex: Lexicon) -> list[tuple[str, ...]]:
    hits = []
    clauses = _clauses(note, lex)
    for term in lex.danger:
        for words in clauses:
            if any(not any(w in lex.negators for w in words[max(0, i - s.NEGATION_WINDOW) : i]) for i in _find(words, term)):
                hits.append(term)
                break
    return hits


def danger_terms(note: str, lex: Lexicon) -> list[str]:
    """The danger words in the note that are not negated."""
    return [" ".join(t) for t in _danger_hits(note, lex)]


def danger_score(note: str, lex: Lexicon) -> float:
    """Un-negated danger evidence: the continuous score the evaluation draws its curves from."""
    return sum(_weight(t) for t in _danger_hits(note, lex))


def has_danger(note: str, urgent_taps: int, lex: Lexicon) -> bool:
    """A danger flag in the note, or enough independent people tapping "urgent"."""
    return danger_score(note, lex) >= s.DANGER_MIN_SCORE or urgent_taps >= s.URGENT_MIN_PEOPLE


def review_reasons(
    accuracy_m: float | None = None, device_reports_last_hour: int = 0, photo_px: tuple[int, int] | None = None
) -> list[str]:
    """Why staff should look at this report first. Never a reason to reject it."""
    reasons = []
    if accuracy_m is not None and (not math.isfinite(accuracy_m) or accuracy_m <= 0 or accuracy_m > s.QUALITY_MAX_ACCURACY_M):
        reasons.append("gps_accuracy_poor")
    if device_reports_last_hour > s.FLOOD_MAX_PER_HOUR:
        reasons.append("device_flooding")
    if photo_px is not None and min(photo_px) < s.PHOTO_MIN_PX:
        reasons.append("photo_tiny")
    return reasons
