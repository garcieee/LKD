import json
import math
import re
from collections import Counter, defaultdict

import pytest

from models.tickets.eval.ranking import pairs
from models.tickets.matching.geo import EARTH_RADIUS_M
from models.tickets.ranking import exposure, priority
from models.tickets.resources.load import load_places
from models.tickets.types import HAZARDS as CATEGORIES
from models.tickets.types import TicketFacts


@pytest.fixture(scope="module")
def fresh():
    return pairs.build()


@pytest.fixture(scope="module", params=["fresh", "other seed", "committed"])
def survey(request, fresh):
    """(blind, key). What must hold for the survey built with the default seed, with another seed, and for the committed files."""
    if request.param == "fresh":
        return fresh
    if request.param == "other seed":
        return pairs.build(pairs.SEED + 1)
    return tuple(json.loads((pairs.DATA / name).read_text(encoding="utf-8")) for name in ("blind_survey.json", "answer_key.json"))


def keys_of(node):
    """Every dict key at any depth."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from keys_of(v)
    elif isinstance(node, list):
        for v in node:
            yield from keys_of(v)


def leaves_of(node):
    if isinstance(node, dict):
        node = list(node.values())
    if isinstance(node, list):
        for v in node:
            yield from leaves_of(v)
    else:
        yield node


# ---- the same seed gives the same survey ----------------------------------------------------------------------------
def test_same_seed_same_survey_another_seed_another_survey(fresh):
    assert pairs.build() == fresh
    assert pairs.dumps(pairs.build()[1]) == pairs.dumps(fresh[1])
    assert pairs.build(pairs.SEED + 1) != fresh


def test_two_writes_of_one_seed_are_byte_identical_and_small(tmp_path):
    for folder in ("a", "b"):
        pairs.write(tmp_path / folder)
    for name in ("blind_survey.json", "answer_key.json", "SURVEY.md"):
        first = (tmp_path / "a" / name).read_bytes()
        assert first == (tmp_path / "b" / name).read_bytes() and len(first) < 150_000


def test_dumps_is_json_with_one_record_per_line(fresh):
    for doc in fresh:
        text = pairs.dumps(doc)
        assert json.loads(text) == doc and len(text.splitlines()) < 600


# ---- size, splits, strata ------------------------------------------------------------------------------------------
def test_the_pool_and_the_pairs_have_the_planned_size(survey):
    blind, key = survey
    truth, pair = key["ticket_truth"], key["pair_truth"]
    assert len(blind["tickets"]) == len(truth) == pairs.N_TICKETS
    assert Counter(t["split"] for t in truth.values()) == {"train": 120, "validation": 40, "test": 40}
    base = [p for p in pair.values() if p["swap_of"] is None]
    assert len(blind["pairs"]) == len(pair) == pairs.N_PAIRS + pairs.N_SWAPS and len(base) == pairs.N_PAIRS
    cells = Counter((p["split"], p["stratum"]) for p in base)
    assert cells == {(s, k): n for s, n in (("train", 48), ("validation", 16), ("test", 16)) for k in pairs.STRATA}
    assert sum(n for (s, _), n in cells.items() if s == "test") >= 48


def test_the_blind_file_and_the_key_describe_the_same_tickets_and_pairs(survey):
    blind, key = survey
    assert [t["id"] for t in blind["tickets"]] == list(key["ticket_truth"])
    assert [p["id"] for p in blind["pairs"]] == list(key["pair_truth"])
    for p in blind["pairs"]:
        assert (p["a"], p["b"]) == (key["pair_truth"][p["id"]]["a_ticket"], key["pair_truth"][p["id"]]["b_ticket"])


def test_pairs_stay_inside_one_split(survey):
    _, key = survey
    split = {tid: t["split"] for tid, t in key["ticket_truth"].items()}
    for pid, p in key["pair_truth"].items():
        assert p["a_ticket"] != p["b_ticket"] and split[p["a_ticket"]] == split[p["b_ticket"]] == p["split"], pid


def test_a_pair_of_tickets_is_asked_once_and_no_ticket_is_in_too_many_pairs(survey):
    _, key = survey
    base = [p for p in key["pair_truth"].values() if p["swap_of"] is None]
    assert max(Counter(frozenset((p["a_ticket"], p["b_ticket"])) for p in base).values()) == 1
    uses = Counter(t for p in base for t in (p["a_ticket"], p["b_ticket"]))
    assert max(uses.values()) <= pairs.MAX_USES and len(uses) > 0.85 * pairs.N_TICKETS


def test_clear_and_close_pairs_have_the_score_gaps_they_are_named_for(survey):
    _, key = survey
    score = {tid: t["score"] for tid, t in key["ticket_truth"].items()}
    for pid, p in key["pair_truth"].items():
        gap = abs(score[p["a_ticket"]] - score[p["b_ticket"]])
        assert gap == pytest.approx(p["gap"])
        if p["stratum"] == "clear":
            assert gap > key["meta"]["clear_gap"], pid
        if p["stratum"] == "close":
            assert gap < key["meta"]["close_gap"], pid


def test_trade_off_pairs_set_a_more_dangerous_kind_against_a_clear_lead(fresh):
    _, key = fresh
    parts = {tid: priority.score(TicketFacts(t["category"], t["reporters"], t["gone_votes"], t["days_open"], t["foot_traffic"], t["danger"])).parts
             for tid, t in key["ticket_truth"].items()}
    score = {tid: t["score"] for tid, t in key["ticket_truth"].items()}
    flips = []
    for pid, p in key["pair_truth"].items():
        if p["stratum"] != "trade_off":
            continue
        hi, lo = sorted((p["a_ticket"], p["b_ticket"]), key=lambda tid: -parts[tid]["danger"])
        assert parts[hi]["danger"] - parts[lo]["danger"] >= pairs.DANGER_GAP, pid
        assert max(parts[lo][k] - parts[hi][k] for k in ("reports", "foot_traffic", "waiting")) >= pairs.WIN_MARGIN, pid
        if p["swap_of"] is None:
            flips.append(score[lo] > score[hi])  # the score puts the less dangerous kind first
    assert 0.4 <= sum(flips) / len(flips) <= 0.6


def test_trade_offs_are_spread_over_kinds_of_hazard(survey):
    _, key = survey
    truth = key["ticket_truth"]
    trade = [p for p in key["pair_truth"].values() if p["stratum"] == "trade_off" and p["swap_of"] is None]
    kinds = Counter(tuple(sorted((truth[p["a_ticket"]]["category"], truth[p["b_ticket"]]["category"]))) for p in trade)
    assert len(kinds) >= 8
    assert sum(n for k, n in kinds.items() if "other" in k) <= 0.4 * len(trade)  # "other" is the least dangerous kind: left alone it would be most of them


def test_a_and_b_order_is_balanced_in_every_split_and_stratum(survey):
    _, key = survey
    score = {tid: t["score"] for tid, t in key["ticket_truth"].items()}
    cells = defaultdict(list)
    for p in key["pair_truth"].values():
        if p["swap_of"] is None:
            cells[p["split"], p["stratum"]].append(score[p["a_ticket"]] - score[p["b_ticket"]])
    for cell, diffs in cells.items():
        ties = sum(d == 0 for d in diffs)
        assert abs(sum(d > 0 for d in diffs) - sum(d < 0 for d in diffs)) <= ties, cell


# ---- swap repeats ---------------------------------------------------------------------------------------------------
def test_swap_repeats_are_exact_mirrors_of_their_originals_and_far_from_them(survey):
    blind, key = survey
    position = {p["id"]: n for n, p in enumerate(blind["pairs"])}
    shown = {p["id"]: (p["a"], p["b"]) for p in blind["pairs"]}
    repeats = {pid: p["swap_of"] for pid, p in key["pair_truth"].items() if p["swap_of"]}
    assert len(repeats) == pairs.N_SWAPS and len(set(repeats.values())) == pairs.N_SWAPS  # each original comes back once
    for new, old in repeats.items():
        mine, theirs = key["pair_truth"][new], key["pair_truth"][old]
        assert theirs["swap_of"] is None  # no repeat of a repeat
        assert shown[new] == shown[old][::-1] and shown[new] != shown[old]
        assert (mine["a_ticket"], mine["b_ticket"]) == (theirs["b_ticket"], theirs["a_ticket"])
        assert (mine["split"], mine["stratum"], mine["gap"]) == (theirs["split"], theirs["stratum"], theirs["gap"])
        assert abs(position[new] - position[old]) >= 30


def test_repeats_are_spread_over_splits_and_strata(fresh):
    _, key = fresh
    cells = Counter((p["split"], p["stratum"]) for p in key["pair_truth"].values() if p["swap_of"])
    assert len(cells) == 9 and min(cells.values()) >= 2
    assert Counter({s: sum(n for (split, _), n in cells.items() if split == s) for s in pairs.SPLITS}) == {"train": 24, "validation": 8, "test": 8}


# ---- the blind file leaks nothing -----------------------------------------------------------------------------------
def test_blind_file_has_no_key_from_the_answer_key_and_no_code_words(survey):
    blind, key = survey
    assert not set(keys_of(blind)) & set(keys_of(key))
    text = json.dumps(blind, ensure_ascii=False)
    for word in [*(c for c in CATEGORIES if "_" in c), "score", "split", "train", "validation", "test", "stratum", "swap", "foot_traffic", "gap", "band", "lat", "lng"]:
        assert not re.search(rf"\b{word}\b", text, re.I), word  # category codes, not the words of a label such as Pothole


def test_blind_file_has_no_priority_score_number(survey):
    blind, key = survey
    assert all(isinstance(v, str) for v in leaves_of(blind))  # no JSON number at all
    for t in blind["tickets"]:
        place = key["ticket_truth"][t["id"]]["place"] or ""
        for number in re.findall(r"\d+(?:\.\d+)?", t["description"].replace(place, "")):  # a place name may hold digits: Glorietta 4
            assert number.isdigit() and int(number) <= 30, (t["id"], number)  # reporters, gone votes, days: never a decimal score
    text = json.dumps(blind, ensure_ascii=False)
    for t in key["ticket_truth"].values():
        assert not any(shown in text for shown in (repr(t["score"]), f"{t['score']:.1f}", f"{t['score']:.2f}"))


def test_descriptions_and_ids_never_leak_the_split(survey):
    blind, key = survey
    for t in blind["tickets"]:
        assert not re.search(r"\b(train|training|validation|test|split)\b", t["description"], re.I), t["id"]
    assert all(re.fullmatch(r"t\d{3}", t["id"]) for t in blind["tickets"]) and all(re.fullmatch(r"p\d{3}", p["id"]) for p in blind["pairs"])
    for split in ([key["ticket_truth"][t["id"]]["split"] for t in blind["tickets"]], [key["pair_truth"][p["id"]]["split"] for p in blind["pairs"]]):
        assert sum(a != b for a, b in zip(split, split[1:])) > 0.4 * (len(split) - 1)  # ids run through the splits at random, not in blocks


def test_each_description_says_what_the_key_says(survey):
    blind, key = survey
    for t in blind["tickets"]:
        assert t["description"] == pairs.describe(key["ticket_truth"][t["id"]])


# ---- the tickets ---------------------------------------------------------------------------------------------------
def test_ticket_attributes_stay_in_their_ranges(survey):
    _, key = survey
    south, west, north, east = pairs.BOX
    for tid, t in key["ticket_truth"].items():
        assert t["category"] in CATEGORIES
        assert 1 <= t["reporters"] <= 12 and 0 <= t["gone_votes"] <= 5 and 0 <= t["days_open"] <= 30, tid
        assert south <= t["lat"] <= north and west <= t["lng"] <= east and 0 < t["foot_traffic"] < 1, tid
        assert t["danger"] == (t["note"] is not None), tid
        assert (t["place"] is None) == (t["place_kind"] is None) == (t["place_m"] is None), tid
        assert t["place"] is None or 0 <= t["place_m"] <= pairs.PLACE_M


def test_the_pool_is_mostly_what_the_brief_says(survey):
    tickets = list(survey[1]["ticket_truth"].values())
    n = len(tickets)
    assert sum(t["reporters"] <= 3 for t in tickets) / n >= 0.7 and max(t["reporters"] for t in tickets) >= 8
    assert sum(t["gone_votes"] == 0 for t in tickets) / n >= 0.7 and max(t["gone_votes"] for t in tickets) >= 3
    assert 0.08 <= sum(t["danger"] for t in tickets) / n <= 0.22
    assert min(Counter(t["category"] for t in tickets).values()) >= 15 and len({t["category"] for t in tickets}) == len(CATEGORIES)
    assert {0, 30} <= {t["days_open"] for t in tickets} or max(t["days_open"] for t in tickets) >= 28


def test_foot_traffic_and_score_are_what_the_rules_say(fresh):
    places = load_places()
    for tid, t in fresh[1]["ticket_truth"].items():
        assert t["foot_traffic"] == exposure.foot_traffic(t["lat"], t["lng"], places), tid
        assert t["score"] == priority.score(TicketFacts(t["category"], t["reporters"], t["gone_votes"], t["days_open"], t["foot_traffic"], t["danger"])).score


def test_the_card_counts_the_files(fresh):
    card = pairs.card(*fresh)
    assert "| train | 120 | 48 | 48 | 48 | 144 | 24 |" in card and "| test | 40 | 16 | 16 | 16 | 48 | 8 |" in card and "| all | 200 | 80 | 80 | 80 | 240 | 40 |" in card


# ---- the rows raters read -------------------------------------------------------------------------------------------
TICKET = {"category": "open_manhole", "place": "Robinsons Supermarket", "place_kind": "mall", "place_m": 30.0, "foot_traffic": 0.8,
          "reporters": 3, "days_open": 1, "gone_votes": 0, "note": None}


def test_the_example_row_from_the_brief():
    assert pairs.describe(TICKET) == ("Open manhole. Next to Robinsons Supermarket, a very busy area. 3 people reported it. "
                                      "Open for 1 day. Everyone agrees it is still there.")


@pytest.mark.parametrize("traffic, label", [(0.1, "a quiet side street"), (0.2499, "a quiet side street"), (0.25, "a moderately busy street"),
                                            (0.65, "a moderately busy street"), (0.6501, "a very busy area"), (0.99, "a very busy area")])
def test_busy_label_thresholds(traffic, label):
    assert f", {label}." in pairs.describe({**TICKET, "foot_traffic": traffic})


@pytest.mark.parametrize("metres, words", [(0, "Next to"), (50, "Next to"), (50.1, "Near"), (150, "Near")])
def test_next_to_within_fifty_metres_else_near(metres, words):
    assert f". {words} Robinsons Supermarket," in pairs.describe({**TICKET, "place_m": metres})


@pytest.mark.parametrize("traffic, row", [(0.1, "On a quiet side street."), (0.4, "On a moderately busy street."), (0.9, "In a very busy area.")])
def test_without_a_named_place_only_the_busy_label_remains(traffic, row):
    none = {**TICKET, "place": None, "place_kind": None, "place_m": None, "foot_traffic": traffic}
    assert pairs.describe(none).startswith(f"Open manhole. {row} 3 people reported it.")


@pytest.mark.parametrize("change, phrase", [({"reporters": 1}, " 1 person reported it. "), ({"reporters": 12}, " 12 people reported it. "),
                                            ({"days_open": 0}, " Reported today. "), ({"days_open": 12}, " Open for 12 days. "),
                                            ({"gone_votes": 1}, " 1 person says it is gone."), ({"gone_votes": 2}, " 2 people say it is gone.")])
def test_counts_read_as_words(change, phrase):
    assert phrase in pairs.describe({**TICKET, **change})


def test_a_danger_note_is_quoted_at_the_end():
    row = pairs.describe({**TICKET, "note": "A child almost fell in."})
    assert row.endswith(' Everyone agrees it is still there. A reporter wrote: "A child almost fell in."')


@pytest.mark.parametrize("kind, name, shown", [("bus", "Jade", "Jade bus stop"), ("bus", "Ayala Terminal", "Ayala Terminal"),
                                               ("bus", "Across from Tengco Street", "the bus stop across from Tengco Street"),
                                               ("rail", "Buendia", "Buendia station"), ("rail", "LRT EDSA Station", "LRT EDSA Station"),
                                               ("school", "Ateneo de Manila University", "Ateneo de Manila University")])
def test_a_bare_stop_or_station_name_gets_its_noun(kind, name, shown):
    assert pairs.place_phrase(name, kind) == shown


LAT, LNG = 14.5547, 121.0244


def place(metres, kind="school", name=""):
    return (LAT + math.degrees(metres / EARTH_RADIUS_M), LNG, kind, name)  # this many metres north of the test point


def test_the_nearest_named_place_wins_and_unnamed_or_far_places_do_not_count():
    got = pairs.nearest_place(LAT, LNG, [place(10), place(120, name="Far"), place(60, "mall", "Mid"), place(200, name="Too far")])
    assert got[:2] == ("Mid", "mall") and got[2] == pytest.approx(60, abs=0.5)
    assert pairs.nearest_place(LAT, LNG, [place(10), place(151, name="Far")]) is None
    assert pairs.nearest_place(LAT, LNG, [place(149, name="Edge")])[0] == "Edge"
    assert pairs.nearest_place(LAT, LNG, []) is None


def test_every_category_has_a_label_and_danger_notes_without_digits():
    assert set(pairs.LABEL) == set(pairs.NOTES) == set(CATEGORIES)
    for notes in pairs.NOTES.values():
        assert len(notes) >= 5 and all(n[0].isupper() and n.endswith(".") and not re.search(r"\d", n) for n in notes)
