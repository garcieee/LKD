import dataclasses

import pytest

np = pytest.importorskip("numpy")

from models.tickets.eval.lifecycle import evaluate as ev  # noqa: E402
from models.tickets.eval.lifecycle import simulator as sm  # noqa: E402

SMALL = sm.SimConfig(tickets=500)
FIELDS = ("end", "time", "yes", "there")


def same(a: sm.Sim, b: sm.Sim) -> bool:
    return all(np.array_equal(getattr(a, f), getattr(b, f)) for f in FIELDS)


def z(rate: float, expected: float, n: int) -> float:
    """How many standard errors a rate measured on n independent draws is from what theory says."""
    return abs(rate - expected) / np.sqrt(expected * (1 - expected) / n)


# ---- deterministic ------------------------------------------------------------------------------------------------
def test_same_seed_same_data_and_another_seed_differs():
    assert same(sm.simulate(SMALL, 7), sm.simulate(SMALL, 7))
    assert not same(sm.simulate(SMALL, 7), sm.simulate(SMALL, 8))


def test_sweeping_accuracy_keeps_the_same_hazards_and_vote_times():
    base = sm.simulate(SMALL, 7)
    worse = sm.simulate(dataclasses.replace(SMALL, sensitivity=0.6, specificity=0.6, noise=0.3), 7)
    assert all(np.array_equal(getattr(base, f), getattr(worse, f)) for f in ("end", "time", "there"))
    assert not np.array_equal(base.yes, worse.yes)


def test_the_three_splits_use_different_seeds():
    train, validation, test = (set(ev.SEEDS[s]) for s in ("train", "validation", "test"))
    assert not (train & validation) and not (train & test) and not (validation & test)
    assert min(len(train), len(validation), len(test)) >= 3


# ---- votes follow the configured accuracy -------------------------------------------------------------------------
@pytest.mark.parametrize("sensitivity, specificity, noise", [(0.85, 0.90, 0.0), (0.70, 0.60, 0.0), (0.85, 0.90, 0.10), (0.95, 0.95, 0.30), (0.60, 0.60, 0.15)])
def test_taps_match_the_configured_sensitivity_specificity_and_noise(sensitivity, specificity, noise):
    world = sm.simulate(sm.SimConfig(tickets=40_000, sensitivity=sensitivity, specificity=specificity, noise=noise), 11)
    ok = world.valid
    when_there, when_gone = world.yes[ok & world.there], world.yes[ok & ~world.there]
    assert min(when_there.size, when_gone.size) > 10_000  # both states are plentiful, so the test has power
    # a random tapper says "still there" half the time whatever is true
    assert z(when_there.mean(), (1 - noise) * sensitivity + noise / 2, when_there.size) < 4
    assert z(when_gone.mean(), (1 - noise) * (1 - specificity) + noise / 2, when_gone.size) < 4


def test_zero_noise_voters_say_gone_exactly_as_often_as_the_specificity():
    world = sm.simulate(sm.SimConfig(tickets=40_000, noise=0.0, specificity=0.9), 12)
    said_gone = ~world.yes[world.valid & ~world.there]
    assert z(said_gone.mean(), 0.9, said_gone.size) < 4


# ---- the hazards and the votes ------------------------------------------------------------------------------------
def test_hazard_and_vote_shares_match_the_configuration():
    cfg = sm.SimConfig(tickets=60_000)
    world = sm.simulate(cfg, 13)
    n = cfg.tickets
    assert z((world.end == 0).mean(), cfg.gone_before_votes, n) < 4  # gone before anyone votes
    votes = world.valid.sum(1)
    assert z((votes == 0).mean(), cfg.no_votes, n) < 4
    assert votes.max() <= cfg.max_votes
    assert votes[votes > 0].mean() == pytest.approx(1 / cfg.votes_geometric_p, rel=0.03)  # 1 + geometric tail, mean 1 / p
    assert np.median(votes[votes > 0]) < votes[votes > 0].mean()  # most tickets get few, a few get many
    staff_ends = world.end[(world.end > 0) & (world.end >= cfg.staff_days[0]) & (world.end <= cfg.staff_days[1])]
    assert len(staff_ends) > 0.2 * n  # the staff fixes (uniform 2..45 days) are there


def test_hazard_lifetime_means_are_what_the_config_says():
    cfg = sm.SimConfig(tickets=60_000, gone_before_votes=0.0, staff_share=0.0, lifetime_means=(15.0,))
    assert sm.simulate(cfg, 14).end.mean() == pytest.approx(15.0, rel=0.03)
    cfg = dataclasses.replace(cfg, lifetime_means=(5.0, 15.0, 60.0))
    assert sm.simulate(cfg, 14).end.mean() == pytest.approx(80 / 3, rel=0.03)


def test_votes_are_in_time_order_and_a_gone_hazard_never_comes_back():
    world = sm.simulate(sm.SimConfig(tickets=3000, gone_tap_rate=0.3), 15)
    valid = world.valid
    assert (valid[:, :-1] | ~valid[:, 1:]).all()  # real votes come first, padding after
    both = valid[:, :-1] & valid[:, 1:]
    assert both.sum() > 1000
    assert (world.time[:, 1:] >= world.time[:, :-1])[both].all()
    assert not (both & ~world.there[:, :-1] & world.there[:, 1:]).any()


def test_people_who_see_nothing_often_do_not_say_so():
    full = sm.simulate(sm.SimConfig(tickets=20_000), 16)
    quiet = sm.simulate(sm.SimConfig(tickets=20_000, gone_tap_rate=0.2), 16)
    gone_taps = lambda w: int((~w.yes & w.valid).sum())
    yes_taps = lambda w: int((w.yes & w.valid).sum())
    assert yes_taps(quiet) == yes_taps(full)  # "still there" taps are never dropped
    assert z(gone_taps(quiet) / gone_taps(full), 0.2, gone_taps(full)) < 4


# ---- ground truth on a hand-made timeline ---------------------------------------------------------------------------
def test_truth_on_a_hand_made_timeline():
    world = sm.from_timelines([
        (10.0, [(2, True), (8, True), (12, False), (20, False)]),  # fixed on day 10: there at 2 and 8, gone at 12 and 20
        (0.0, [(1, True), (3, False)]),  # gone right after the first report: a tap of "still there" at day 1 is a mistake
        (5.0, [(4.9, True), (5.0, False), (6.0, False)]),  # gone from the moment it ends, so at exactly day 5 it is gone
        (3.0, []),  # nobody ever voted
    ])
    assert world.valid.tolist() == [[True] * 4, [True, True, False, False], [True, True, True, False], [False] * 4]
    assert world.there[0].tolist() == [True, True, False, False]
    assert world.there[1, :2].tolist() == [False, False]
    assert world.there[2, :3].tolist() == [True, False, False]
    assert world.yes[0].tolist() == [True, True, False, False]


def test_still_there_is_a_strict_comparison_with_the_end_time():
    assert sm.still_there(np.array([[1.0, 2.0, 2.0000001]]), np.array([2.0])).tolist() == [[True, False, False]]


def test_concat_stacks_seeds():
    a, b = sm.simulate(SMALL, 1), sm.simulate(SMALL, 2)
    both = sm.concat([a, b])
    assert both.time.shape == (1000, SMALL.max_votes) and np.array_equal(both.end[500:], b.end)
