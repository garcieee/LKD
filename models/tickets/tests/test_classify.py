import math

import pytest

from models.tickets import settings as s
from models.tickets.classification import classify as c
from models.tickets.resources.load import load_lexicon

# A tiny lexicon for the mechanics. The shipped one is smoke-tested at the bottom.
LEX = c.Lexicon(
    {
        "categories": {"pothole": ["lubak", "butas sa kalsada"], "flooded_drain": ["baha", "barado"], "other": ["puno"]},
        "danger": ["bata", "delikado", "muntik na"],
        "negators": ["walang", "hindi", "don't"],
        "boundaries": ["pero"],
    }
)


def test_tokens_lowercase_and_drop_accents_punctuation_and_apostrophes():
    assert c.tokens("Dasmariñas, BAHA!! don't ’ok’") == ["dasmarinas", "baha", "dont", "ok"]
    assert c.tokens("") == [] and c.tokens("🙂 ...") == []


def test_matching_is_whole_word_so_house_is_not_flood():
    assert c.category_scores("bahay namin ito", LEX)["flooded_drain"] == 0
    assert c.category_scores("may baha dito", LEX)["flooded_drain"] == 1.0
    assert c.category_scores("BAHA!", LEX)["flooded_drain"] == 1.0


def test_a_phrase_counts_more_than_a_word_and_each_term_counts_once():
    assert c.category_scores("butas sa kalsada", LEX)["pothole"] == s.PHRASE_WEIGHT
    assert c.category_scores("lubak lubak lubak", LEX)["pothole"] == 1.0
    assert c.category_scores("lubak at butas sa kalsada", LEX)["pothole"] == 1.0 + s.PHRASE_WEIGHT


def test_hint_names_the_category_and_what_matched():
    hint = c.category_hint("grabe ang lubak dito sa harap", LEX)
    assert hint.category == "pothole" and hint.terms == ("lubak",) and hint.score == 1.0 and hint.margin == 1.0


def test_no_hint_when_the_note_does_not_say_or_is_torn():
    assert c.category_hint("", LEX) is None
    assert c.category_hint("please fix asap", LEX) is None
    assert c.category_hint("lubak at baha", LEX) is None  # tie: margin 0
    assert c.category_hint("lubak, butas sa kalsada at baha", LEX).category == "pothole"  # clear winner


def test_a_negator_just_before_a_danger_word_cancels_it():
    assert c.danger_terms("walang bata dito", LEX) == []
    assert c.danger_terms("hindi delikado", LEX) == []
    assert c.danger_terms("walang bata pero delikado pa rin", LEX) == ["delikado"]
    assert c.danger_terms("may bata na muntik na mahulog", LEX) == ["bata", "muntik na"]


def test_a_comma_or_a_but_word_ends_a_negators_reach():
    assert c.danger_terms("walang bata, delikado pa rin", LEX) == ["delikado"]
    assert c.danger_terms("hindi delikado, may bata na muntik na mahulog", LEX) == ["bata", "muntik na"]
    assert c.danger_terms("walang bata. delikado pa rin!", LEX) == ["delikado"]
    assert c.danger_terms("pero delikado", LEX) == ["delikado"]  # a leading boundary word is harmless


def test_the_negation_window_is_three_words():
    assert c.danger_terms("walang po sana bata", LEX) == []  # negator 3 words before
    assert c.danger_terms("walang po sana kayo bata", LEX) == ["bata"]  # 4 words before


def test_danger_score_counts_distinct_terms_once():
    assert c.danger_score("bata bata bata", LEX) == 1.0
    assert c.danger_score("bata delikado muntik na", LEX) == 1.0 + 1.0 + s.PHRASE_WEIGHT
    assert c.danger_score("", LEX) == 0.0


def test_urgent_taps_need_enough_independent_people():
    assert c.has_danger("", s.URGENT_MIN_PEOPLE, LEX) and not c.has_danger("", s.URGENT_MIN_PEOPLE - 1, LEX)
    assert c.has_danger("delikado", 0, LEX) and not c.has_danger("walang bata", 1, LEX)


def test_review_reasons():
    assert c.review_reasons() == [] and c.review_reasons(accuracy_m=s.QUALITY_MAX_ACCURACY_M) == []
    assert c.review_reasons(accuracy_m=s.QUALITY_MAX_ACCURACY_M + 1) == ["gps_accuracy_poor"]
    assert c.review_reasons(accuracy_m=float("nan")) == c.review_reasons(accuracy_m=0) == ["gps_accuracy_poor"]
    assert c.review_reasons(device_reports_last_hour=s.FLOOD_MAX_PER_HOUR) == []
    assert c.review_reasons(device_reports_last_hour=s.FLOOD_MAX_PER_HOUR + 1) == ["device_flooding"]
    assert c.review_reasons(photo_px=(200, 900)) == ["photo_tiny"] and c.review_reasons(photo_px=(640, 480)) == []
    assert c.review_reasons(80, 99, (10, 10)) == ["gps_accuracy_poor", "device_flooding", "photo_tiny"]


# ---- the shipped word list, on notes anyone would label the same way -------------------------------------------
SHIPPED = c.Lexicon(load_lexicon())


@pytest.mark.parametrize(
    "note, category",
    [
        ("may malaking lubak sa harap ng school", "pothole"),
        ("big pothole near the corner of Buendia", "pothole"),
        ("walang takip ang manhole dito", "open_manhole"),
        ("open manhole beside the bus stop", "open_manhole"),
        ("baha sa kanto, barado ang kanal", "flooded_drain"),
        ("clogged drain, street flooded again", "flooded_drain"),
        ("patay ang ilaw sa poste simula kahapon", "broken_streetlight"),
        ("the street light is out and the road is dark", "broken_streetlight"),
        ("nakaharang ang mga vendor sa bangketa", "blocked_sidewalk"),
        ("cars parked on the sidewalk, no way to walk", "blocked_sidewalk"),
    ],
)
def test_the_shipped_lexicon_gets_the_obvious_notes_right(note, category):
    assert c.category_hint(note, SHIPPED).category == category


@pytest.mark.parametrize(
    "note, danger",
    [
        ("walang takip ang manhole, may bata na muntik nahulog", True),
        ("delikado dito lalo na sa gabi", True),
        ("someone got hurt here last week", True),
        ("walang bata pero delikado pa rin", True),
        ("no kids around, but it is dangerous", True),
        ("walang bata na dumadaan dito", False),
        ("hindi naman delikado pero sira", False),
        ("bahay namin malapit dito, sira ang kalsada", False),
        ("please fix asap", False),
    ],
)
def test_the_shipped_lexicon_flags_the_obvious_danger_notes(note, danger):
    assert c.has_danger(note, 0, SHIPPED) is danger


def test_the_shipped_lexicon_does_not_hint_at_a_house():
    assert c.category_hint("bahay namin ito", SHIPPED) is None
    assert math.isclose(c.danger_score("", SHIPPED), 0.0)
