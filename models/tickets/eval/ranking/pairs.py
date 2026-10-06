"""The blind ticket-ranking survey: synthetic tickets, the pairs raters judge, and the answer key behind them.

Rebuild (from the repo root, rewrites data/):  models/.venv/bin/python -m models.tickets.eval.ranking.pairs

Same seed, same survey. Tickets are split 60/20/20 first and pairs are formed inside one split. ranking/priority.py
decides which pairs are clear, close or trade-offs and is never shown to a rater: raters read data/blind_survey.json
only, data/answer_key.json is the evaluator's. The committed files are the survey the raters answered. Rebuilding
after a change to settings.py would pick other pairs, so do not rebuild once ratings exist.
"""
import json
import re
from collections import Counter, defaultdict
from itertools import zip_longest
from pathlib import Path

import numpy as np

from models.tickets.eval.common import results, splits
from models.tickets.matching.geo import distance_m
from models.tickets.ranking import exposure, priority
from models.tickets.resources.load import load_places
from models.tickets.types import CATEGORIES, TicketFacts

DATA = Path(__file__).resolve().parent / "data"
SEED = 2026
BOX = (14.5296, 120.9987, 14.5796, 121.0501)  # south, west, north, east: the Makati box of resources/places.json
N_TICKETS, N_PAIRS, N_SWAPS = 200, 240, 40
SPLITS, FRACTIONS = ("train", "validation", "test"), (0.6, 0.2, 0.2)
STRATA = ("clear", "close", "trade_off")
CLEAR_GAP, CLOSE_GAP = 15.0, 5.0  # score points: clear is a gap above the first, close a gap below the second
DANGER_GAP, WIN_MARGIN = 0.18, 0.4  # trade-off, on the 0..1 parts of the score: the danger lead of the one ticket, the lead of the other
MAX_USES = 5  # most pairs one ticket may be in
PLACE_M, NEXT_TO_M = 150.0, 50.0  # the nearest named place within PLACE_M is mentioned, "next to" within NEXT_TO_M
DANGER_SHARE = 0.15  # share of tickets with a danger note

LABEL = {"pothole": "Pothole", "open_manhole": "Open manhole", "flooded_drain": "Flooded drain",
         "broken_streetlight": "Broken streetlight", "blocked_sidewalk": "Blocked sidewalk", "other": "Other issue (type not given)"}
BUSY = ("a quiet side street", "a moderately busy street", "a very busy area")  # foot traffic under 0.25, up to 0.65, above
NOTES = {  # danger notes: what a reporter might write (no digits, nothing that hints at a score)
    "pothole": ["A motorcycle skidded here this morning.", "Tricycles swerve into oncoming traffic to dodge it.",
                "An old man tripped and hurt his knee.", "It is deep enough to snap a wheel.",
                "Cyclists keep falling here.", "A jeepney nearly overturned on it."],
    "open_manhole": ["A child almost fell in.", "No cover and no warning sign, someone will fall in.",
                     "A cyclist's front wheel dropped into it.", "It is hidden under the water when it rains.",
                     "A dog fell in yesterday.", "People walk right beside the open hole in the dark."],
    "flooded_drain": ["The water is knee deep and children wade through it.", "Cars stall in the flood every time it rains.",
                      "Water is coming into the houses.", "The flood hides an open drain beside it.",
                      "People slip on the muddy road.", "Electric wires hang over the flooded road."],
    "broken_streetlight": ["It is pitch dark at night and a woman was nearly robbed.", "Students walk home here in the dark.",
                           "A pedestrian was hit by a motorcycle last night.", "Drivers cannot see the crossing.",
                           "There have been muggings here after dark.", "An old woman fell in the dark last week."],
    "blocked_sidewalk": ["Wheelchair users have to go out onto the road.", "Children walk in the traffic lane because of it.",
                         "A mother with a stroller was nearly hit by a bus.", "Old people cannot get past and step into the road.",
                         "A blind man walked into it.", "Pedestrians are pushed into the jeepney lane."],
    "other": ["A live wire is hanging low over the road.", "A big tree branch looks ready to fall on the sidewalk.",
              "Broken glass all over where children play.", "A loose signboard could fall on people.",
              "The railing is gone and the drop is steep."],
}


# ---- what a rater reads --------------------------------------------------------------------------------------------
def nearest_place(lat: float, lng: float, places) -> tuple[str, str, float] | None:
    """(name, kind, metres) of the closest NAMED place within PLACE_M, or None."""
    near = min(((distance_m(lat, lng, p[0], p[1]), p[3], p[2]) for p in places if p[3]), default=None)  # (metres, name, kind)
    return (near[1], near[2], near[0]) if near and near[0] <= PLACE_M else None


def place_phrase(name: str, kind: str) -> str:
    """The place as a person says it: a bare stop or station name gets its noun."""
    if kind == "bus" and name.startswith("Across from"):
        return f"the bus stop {name[0].lower()}{name[1:]}"
    if kind == "bus" and not re.search(r"stop|terminal|station", name, re.I):
        return f"{name} bus stop"
    if kind == "rail" and not re.search(r"station|stop", name, re.I):
        return f"{name} station"
    return name


def describe(t: dict) -> str:
    """One dashboard row in plain words. Counts and days are shown as they are; no score, no foot-traffic number."""
    level = 0 if t["foot_traffic"] < 0.25 else 1 if t["foot_traffic"] <= 0.65 else 2
    if t["place"]:
        near = "Next to" if t["place_m"] <= NEXT_TO_M else "Near"
        where = f"{near} {place_phrase(t['place'], t['place_kind'])}, {BUSY[level]}."
    else:
        where = f"{'In' if level == 2 else 'On'} {BUSY[level]}."
    n, days, gone = t["reporters"], t["days_open"], t["gone_votes"]
    parts = [f"{LABEL[t['category']]}.", where, f"{n} {'person' if n == 1 else 'people'} reported it.",
             "Reported today." if days == 0 else f"Open for {days} {'day' if days == 1 else 'days'}.",
             f"{gone} {'person says' if gone == 1 else 'people say'} it is gone." if gone else "Everyone agrees it is still there."]
    if t["note"]:
        parts.append(f'A reporter wrote: "{t["note"]}"')
    return " ".join(parts)


# ---- the ticket pool -----------------------------------------------------------------------------------------------
def make_tickets(rng, places) -> tuple[list[dict], list[dict]]:
    """N_TICKETS tickets (true attributes, priority score, description) and the 0..1 parts of each score."""
    n = N_TICKETS
    lat = np.round(rng.uniform(BOX[0], BOX[2], n), 5)
    lng = np.round(rng.uniform(BOX[1], BOX[3], n), 5)
    category = rng.choice(CATEGORIES, n)
    reporters = np.where(rng.random(n) < 0.85, rng.choice([1, 2, 3], n, p=[0.5, 0.3, 0.2]), rng.integers(4, 13, n))
    gone = rng.choice(6, n, p=[0.76, 0.10, 0.06, 0.04, 0.02, 0.02])
    days = rng.integers(0, 31, n)
    danger, which_note = rng.random(n) < DANGER_SHARE, rng.random(n)
    tickets, parts = [], []
    for k in range(n):
        la, ln, c = float(lat[k]), float(lng[k]), str(category[k])
        place = nearest_place(la, ln, places)
        t = {"category": c, "reporters": int(reporters[k]), "gone_votes": int(gone[k]), "days_open": int(days[k]),
             "foot_traffic": exposure.foot_traffic(la, ln, places), "danger": bool(danger[k]),
             "note": NOTES[c][int(which_note[k] * len(NOTES[c]))] if danger[k] else None, "lat": la, "lng": ln,
             "place": place[0] if place else None, "place_kind": place[1] if place else None,
             "place_m": round(place[2], 1) if place else None}
        scored = priority.score(TicketFacts(c, t["reporters"], t["gone_votes"], t["days_open"], t["foot_traffic"], t["danger"]))
        tickets.append({**t, "score": scored.score, "description": describe(t)})
        parts.append(scored.parts)
    return tickets, parts


# ---- the pairs -----------------------------------------------------------------------------------------------------
def take_pairs(pool: list, want: int, uses: Counter, taken: set) -> list:
    """The first `want` pairs of the pool that no ticket is too busy for and that were not chosen before."""
    chosen = []
    for i, j in pool:
        if (i, j) in taken or uses[i] >= MAX_USES or uses[j] >= MAX_USES:
            continue
        chosen.append((i, j))
        taken.add((i, j))
        uses.update((i, j))
        if len(chosen) == want:
            return chosen
    raise ValueError(f"only {len(chosen)} of {want} pairs found")


def shuffled(rng, pool: list) -> list:
    return [pool[k] for k in rng.permutation(len(pool))]


def by_turns(rng, groups: dict) -> list:
    """Every group's pairs, shuffled, taken one group at a time in turn (groups in random order), so no group dominates."""
    lists = [shuffled(rng, groups[key]) for key in sorted(groups)]
    return [p for row in zip_longest(*(lists[k] for k in rng.permutation(len(lists)))) for p in row if p]


def make_pairs(rng, tickets: list[dict], parts: list[dict], split_idx) -> list[dict]:
    """N_PAIRS pairs, an equal share per stratum in each split, all inside one split. In each split and stratum exactly
    half show the higher score as A. Strata (the score is used here and nowhere a rater can see):
      clear      the scores differ by more than CLEAR_GAP
      close      the scores differ by less than CLOSE_GAP
      trade_off  one ticket is a clearly more dangerous kind of hazard, the other leads by WIN_MARGIN on reports,
                 foot traffic or waiting. Half are pairs where the score puts the less dangerous kind first (the pairs
                 that tell the score from a severity-only order). Within each half the kinds of the less dangerous
                 ticket take turns, so "other", the least dangerous kind of all, is not most of them."""
    score = [t["score"] for t in tickets]
    out = []
    for name, idx in zip(SPLITS, split_idx):
        idx = idx.tolist()
        want = round(N_PAIRS * len(idx) / N_TICKETS / len(STRATA))  # pairs per stratum in this split
        clear, close = [], []
        trade = {True: defaultdict(list), False: defaultdict(list)}  # does the score put the less dangerous ticket first -> its kind -> pairs
        for n, i in enumerate(idx):
            for j in idx[n + 1:]:
                if tickets[i]["description"] == tickets[j]["description"]:
                    continue  # nothing to tell them apart by
                gap = abs(score[i] - score[j])
                if gap > CLEAR_GAP:
                    clear.append((i, j))
                elif gap < CLOSE_GAP:
                    close.append((i, j))
                risky, other = (i, j) if parts[i]["danger"] > parts[j]["danger"] else (j, i)  # the more dangerous kind of hazard
                lead = max(parts[other][k] - parts[risky][k] for k in ("reports", "foot_traffic", "waiting"))
                if parts[risky]["danger"] - parts[other]["danger"] >= DANGER_GAP and lead >= WIN_MARGIN:
                    trade[score[other] > score[risky]][tickets[other]["category"]].append((i, j))
        pools = {"clear": shuffled(rng, clear), "close": shuffled(rng, close),
                 "trade_off": [p for two in zip_longest(by_turns(rng, trade[True]), by_turns(rng, trade[False])) for p in two if p]}
        uses, taken = Counter(), set()
        for stratum in STRATA:
            chosen = take_pairs(pools[stratum], want, uses, taken)
            for (i, j), lower_first in zip(chosen, rng.permutation(len(chosen)) % 2):
                top, bottom = (i, j) if score[i] >= score[j] else (j, i)  # higher score, lower score
                out.append({"a": bottom if lower_first else top, "b": top if lower_first else bottom, "split": name, "stratum": stratum})
    return out


def finish(rng, pairs: list[dict]) -> list[dict]:
    """Add N_SWAPS repeats with A and B swapped (every few pairs, in split and stratum order), put all pairs in a
    random order, a repeat at least a quarter of the way from its original, and number them p001, p002, ..."""
    cells = sorted(range(len(pairs)), key=lambda k: (SPLITS.index(pairs[k]["split"]), STRATA.index(pairs[k]["stratum"])))
    repeated = cells[:: len(pairs) // N_SWAPS][:N_SWAPS]
    rows = [{**p, "swap_of": None} for p in pairs]
    rows += [{**pairs[k], "a": pairs[k]["b"], "b": pairs[k]["a"], "swap_of": k} for k in repeated]
    when = rng.random(len(rows))
    when[len(pairs):] = (when[repeated] + rng.uniform(0.25, 0.75, len(repeated))) % 1  # circular distance from the original: 0.25 to 0.5
    order = [int(k) for k in np.argsort(when)]
    name = {k: f"p{r + 1:03d}" for r, k in enumerate(order)}
    return [{**rows[k], "id": name[k], "swap_of": name.get(rows[k]["swap_of"])} for k in order]


# ---- the files -----------------------------------------------------------------------------------------------------
def build(seed: int = SEED) -> tuple[dict, dict]:
    """(blind survey, answer key) as plain dicts. Same seed, same survey."""
    rng = np.random.default_rng(seed)
    tickets, parts = make_tickets(rng, load_places())
    split_idx = splits.group_split(np.arange(N_TICKETS), FRACTIONS, seed=int(rng.integers(2**31)))
    pairs = finish(rng, make_pairs(rng, tickets, parts, split_idx))
    # Tickets are drawn independently, so their order is already random: an id is just a position and says nothing about the split.
    tid = [f"t{k + 1:03d}" for k in range(N_TICKETS)]
    split_of = {k: SPLITS[s] for s, idx in enumerate(split_idx) for k in idx.tolist()}
    blind = {"tickets": [{"id": tid[k], "description": t["description"]} for k, t in enumerate(tickets)],
             "pairs": [{"id": p["id"], "a": tid[p["a"]], "b": tid[p["b"]]} for p in pairs]}
    key = {"meta": {"seed": seed, "box": list(BOX), "clear_gap": CLEAR_GAP, "close_gap": CLOSE_GAP, "danger_gap": DANGER_GAP,
                    "win_margin": WIN_MARGIN, "scores": "ranking/priority.score at build time; recompute from the attributes if settings.py changed"},
           "ticket_truth": {tid[k]: {"split": split_of[k], **{f: v for f, v in t.items() if f != "description"}} for k, t in enumerate(tickets)},
           "pair_truth": {p["id"]: {"a_ticket": tid[p["a"]], "b_ticket": tid[p["b"]], "split": p["split"], "stratum": p["stratum"],
                                    "gap": abs(tickets[p["a"]]["score"] - tickets[p["b"]]["score"]), "swap_of": p["swap_of"]} for p in pairs}}
    return blind, key


def dumps(doc: dict) -> str:
    """JSON with one record per line, so the files stay small and a diff shows whole records."""
    one = lambda v: json.dumps(v, ensure_ascii=False)
    blocks = []
    for name, value in doc.items():
        if isinstance(value, list):
            rows, (opening, closing) = [one(v) for v in value], "[]"
        elif isinstance(value, dict) and all(isinstance(v, dict) for v in value.values()):
            rows, (opening, closing) = [f"{one(k)}: {one(v)}" for k, v in value.items()], "{}"
        else:
            blocks.append(f"  {one(name)}: {one(value)}")
            continue
        blocks.append(f"  {one(name)}: {opening}\n    " + ",\n    ".join(rows) + f"\n  {closing}")
    return "{\n" + ",\n".join(blocks) + "\n}\n"


def card(blind: dict, key: dict) -> str:
    """data/SURVEY.md, written from the two files so its counts are the files' counts."""
    truth, pair = key["ticket_truth"], key["pair_truth"]
    rows = []
    for name in SPLITS:
        mine = [p for p in pair.values() if p["split"] == name]
        row = {"split": name, "tickets": sum(t["split"] == name for t in truth.values())}
        row |= {s: sum(p["stratum"] == s and p["swap_of"] is None for p in mine) for s in STRATA}
        rows.append(row | {"pairs": sum(row[s] for s in STRATA), "swap repeats": sum(p["swap_of"] is not None for p in mine)})
    rows.append({"split": "all", **{c: sum(r[c] for r in rows) for c in rows[0] if c != "split"}})
    table = results.md_table(rows, ["split", "tickets", *STRATA, "pairs", "swap repeats"])
    kinds, danger = Counter(t["category"] for t in truth.values()), sum(t["danger"] for t in truth.values())
    placed = Counter(t["place_kind"] for t in truth.values() if t["place"])
    example = next((t["description"] for t in blind["tickets"] if "Next to" in t["description"] and "wrote" in t["description"]), blind["tickets"][0]["description"])
    return f"""# Ticket-ranking survey

What five raters answer, and what the evaluator compares `ranking/priority.py` with. Built by `pairs.py` (seed {key["meta"]["seed"]}).
Frozen once raters have answered: rebuilding after a change to `settings.py` would pick other pairs.
Raters get `blind_survey.json` and the text of `RATER_INSTRUCTIONS.md`, never this card or `answer_key.json`.

## How it was built

- **Tickets:** {len(truth)} synthetic ones at random points in the Makati box. Kind ({", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))}),
  people reporting 1 to 12 (mostly 1 to 3), people saying it is gone 0 to 5 (mostly 0), days open 0 to 30, foot traffic from
  `exposure.foot_traffic` on the real OpenStreetMap places, and a danger note (a short quote) on {danger}.
- **Splits first:** tickets 60/20/20 with `common.splits.group_split`, then pairs only inside one split. Each ticket's split is in the key.
- **Pairs, stratified with `priority.score`** (used to choose, never shown). `clear`: more than {CLEAR_GAP:g} points apart. `close`: less than {CLOSE_GAP:g} apart.
  `trade_off`: one ticket is a clearly more dangerous kind of hazard (danger part {DANGER_GAP:g} or more higher), the other leads by {WIN_MARGIN:g} or more
  (0 to 1 scale) on people reporting, foot traffic or waiting. Half the trade-offs are pairs where the score puts the less dangerous kind first,
  and the less dangerous kinds take turns, so "other" is not most of them. No ticket is in more than {MAX_USES} pairs; no pair shows two identical descriptions.
- **Swap repeats:** {N_SWAPS} pairs return once with A and B swapped, under a new id, at least a quarter of the file from the original, spread over
  splits and strata. They measure position bias; `swap_of` in the key maps each repeat to its original.
- **A and B order** is random, exactly balanced in each split and stratum (half the pairs show the higher score as A).
- **Ids** (`t001`, `p001`) are positions in a random order: they say nothing about split, stratum or repeats.

## Counts (pairs exclude the repeats)

{table}

## What raters see

One dashboard row per ticket, for example:

> {example}

- the kind of hazard in words;
- the nearest named place within {PLACE_M:g} m ("Next to" within {NEXT_TO_M:g} m, else "Near"; a bare bus stop or station name gets its noun) and a busy label from
  foot traffic ("a quiet side street" under 0.25, "a moderately busy street" up to 0.65, "a very busy area" above); with no named place that close, the busy label alone;
- how many people reported it, how long it has been open, and "N people say it is gone" or "Everyone agrees it is still there";
- the danger note as a quote, when there is one.

No priority score, band, foot-traffic number, coordinates, category code, split or stratum. Two tasks: A, B or tie with a confidence of 1 to 3 on every pair,
and an urgency of 1 to 5 on every ticket.

## Caveats

- Synthetic tickets and English-only notes written to show danger, so a note is a strong cue.
- {sum(placed.values())} tickets have a named place within {PLACE_M:g} m ({", ".join(f"{k} {v}" for k, v in placed.most_common())}); the rest show only the busy label.
- The busy label has three levels, so two tickets with the same label can differ a lot in foot traffic, which the score uses as a number. The named place is the nearest one,
  while foot traffic counts every place within 300 m: a spot next to a quiet bus stop can still be labelled a very busy area.
- "Other issue" has no hazard type; the score treats it as the least dangerous kind. The score stops counting waiting after 14 days, but raters see up to 30.
"""


def write(out: Path = DATA, seed: int = SEED) -> list[Path]:
    """Build the survey and write blind_survey.json, answer_key.json and SURVEY.md into `out`."""
    blind, key = build(seed)
    out.mkdir(parents=True, exist_ok=True)
    files = {"blind_survey.json": dumps(blind), "answer_key.json": dumps(key), "SURVEY.md": card(blind, key)}
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")
    return [out / name for name in files]


if __name__ == "__main__":
    for path in write():
        print(f"wrote {path} ({path.stat().st_size:,} bytes)")
