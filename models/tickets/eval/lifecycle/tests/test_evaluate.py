import dataclasses
import json

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

from models.tickets import settings as S  # noqa: E402
from models.tickets.eval.common import metrics as M  # noqa: E402
from models.tickets.eval.lifecycle import evaluate as ev  # noqa: E402
from models.tickets.eval.lifecycle import simulator as sm  # noqa: E402
from models.tickets.ranking import lifecycle  # noqa: E402

SMALL = sm.SimConfig(tickets=2000)


# ---- belief and gate get the right counts ---------------------------------------------------------------------------
def test_belief_gate_and_flag_are_called_with_the_right_counts(monkeypatch):
    world = sm.from_timelines([(10.0, [(1, True), (2, False), (3, False), (4, True)])])
    real = {name: getattr(lifecycle, name) for name in ("belief", "gate", "likely_gone")}
    calls = {name: [] for name in real}

    def spy(name):
        def wrapper(*args):
            calls[name].append(args)
            return real[name](*args)
        return wrapper

    for name in real:
        monkeypatch.setattr(lifecycle, name, spy(name))
    ev.score(world)
    # the reporter is one yes before anyone taps; then yes, no, no, yes
    assert calls["belief"] == [(2, 0), (2, 1), (2, 2), (3, 2)]
    beliefs = [real["belief"](*args) for args in calls["belief"]]
    assert calls["gate"] == [(b,) for b in beliefs] and calls["likely_gone"] == [(b,) for b in beliefs]


def test_score_on_a_hand_made_timeline():
    world = sm.from_timelines([(2.5, [(1, True), (2, False), (3, False)]), (5.0, [])])
    sc = ev.score(world)
    assert sc.valid.tolist() == [[True, True, True], [False, False, False]]
    assert sc.yes[0].tolist() == [2, 2, 2] and sc.no[0].tolist() == [0, 1, 2]
    assert sc.belief[0].tolist() == pytest.approx([5 / 6, 5 / 7, 5 / 8])  # (3 + yes) / (4 + yes + no)
    assert sc.gate[0].tolist() == pytest.approx([1.0, (5 / 7 - 0.3) / 0.5, (5 / 8 - 0.3) / 0.5])
    assert sc.flag[0].tolist() == [False, False, False]
    assert sc.truth[0].tolist() == [1.0, 1.0, 0.0]  # the hazard ends at day 2.5
    assert sc.next_truth[0, :2].tolist() == [1.0, 0.0] and np.isnan(sc.next_truth[0, 2])
    assert np.isnan(sc.belief[1]).all() and np.isnan(sc.truth[1]).all() and not sc.flag[1].any()


def test_at_selects_the_tickets_that_got_that_many_votes():
    world = sm.from_timelines([(9.0, [(1, True)]), (9.0, [(1, True), (2, False), (3, False)]), (9.0, [])])
    sc = ev.score(world)
    assert [len(sc.at(k)["belief"]) for k in (1, 2, 3)] == [2, 1, 1]
    assert sc.at(3)["no"].tolist() == [2] and sc.at(3)["yes"].tolist() == [2]
    assert len(sc.at(1, "next_truth")["belief"]) == 1  # only the ticket with a second vote has a "next" moment


def test_a_distinct_flag_threshold_changes_the_flag_but_not_belief():
    world = sm.from_timelines([(0.0, [(1, False), (2, False), (3, False)])])  # belief 4/6, 4/7, 4/8
    sc = ev.score(world)
    assert ev.flagged_at(sc, 0.45).tolist() == [[False, False, False]]
    assert ev.flagged_at(sc, 0.55).tolist() == [[False, False, True]]
    assert ev.flagged_at(sc, 0.60).tolist() == [[False, True, True]]
    assert S.LIKELY_GONE_BELOW == 0.45  # put back


# ---- other priors and thresholds go through the real functions -------------------------------------------------------
def test_override_restores_settings_even_after_an_error_and_rejects_unknown_names():
    shipped = S.BELIEF_PRIOR
    with ev.override(BELIEF_PRIOR=(1, 1)):
        assert lifecycle.belief(1, 0) == pytest.approx(2 / 3)
    assert S.BELIEF_PRIOR == shipped and lifecycle.belief(1, 0) == pytest.approx(0.8)
    with pytest.raises(RuntimeError):
        with ev.override(BELIEF_PRIOR=(1, 1)):
            raise RuntimeError("boom")
    assert S.BELIEF_PRIOR == shipped
    with pytest.raises(AttributeError):
        with ev.override(BELIEF_PRIORR=(1, 1)):
            pass


def test_a_prior_is_tried_through_the_real_belief_function():
    world = sm.from_timelines([(10.0, [(1, True), (2, False), (3, False)])])
    b = ev.belief_under(world, (1, 0.5))
    yes, no = np.array([2, 2, 2]), np.array([0, 1, 2])
    assert b[0].tolist() == pytest.approx(((1 + yes) / (1.5 + yes + no)).tolist())  # Beta(1, 0.5) posterior mean
    assert S.BELIEF_PRIOR == (3, 1)


def test_the_fitted_prior_expects_fewer_surviving_hazards_when_more_are_already_gone():
    mean = lambda p: p[0] / (p[0] + p[1])
    mostly_there = ev.fit_prior(ev.score(sm.simulate(dataclasses.replace(SMALL, gone_before_votes=0.0), 31)))
    mostly_gone = ev.fit_prior(ev.score(sm.simulate(dataclasses.replace(SMALL, gone_before_votes=0.6), 31)))
    assert mean(mostly_there) > mean(mostly_gone) and S.BELIEF_PRIOR == (3, 1)


# ---- the metrics plumbing -----------------------------------------------------------------------------------------------
def test_majority_forecast_is_one_zero_or_half_on_a_tie():
    assert ev.majority(np.array([2, 1, 2]), np.array([0, 1, 3])).tolist() == [1.0, 0.5, 0.0]


def test_pooled_ignores_cells_with_no_vote_and_matches_the_flat_metric():
    y = np.array([[1.0, 0.0, np.nan], [0.0, np.nan, np.nan]])
    p = np.array([[0.9, 0.2, np.nan], [0.4, np.nan, np.nan]])
    assert ev.pooled(M.brier)(y, p) == pytest.approx(M.brier([1, 0, 0], [0.9, 0.2, 0.4]))
    interval = M.bootstrap_ci(ev.pooled(M.brier), y, p, n=50)  # resamples whole tickets
    assert interval.lo <= interval.point <= interval.hi


def test_per_ticket_counts_give_the_same_precision_recall_f_as_every_vote():
    sc = ev.score(sm.simulate(SMALL, 3))
    flagged = ev.flagged_at(sc, 0.55)
    got = ev._prf(*ev.flag_counts(sc, flagged))
    gone = (sc.truth == 0)[sc.valid]
    for beta, key in ((1, "f1"), (2, "f2")):
        want = M.prf(gone, flagged[sc.valid], beta=beta)
        assert got["precision"] == pytest.approx(want["precision"]) and got["recall"] == pytest.approx(want["recall"])
        assert got[key] == pytest.approx(want["f"])


def test_rates_carry_the_counts_behind_them():
    shares = ev.share_ci(np.array([True, False, True, False]), np.array([True, True, True, False]))
    assert (shares["events"], shares["of"]) == (2, 3) and shares["point"] == pytest.approx(2 / 3)
    rates = ev.rate_ci(np.array([1, 0, 2]), np.array([2, 1, 2]))
    assert (rates["events"], rates["of"]) == (3, 5) and rates["point"] == pytest.approx(0.6)
    none = ev.share_ci(np.zeros(50, bool), np.ones(50, bool))
    assert (none["events"], none["of"], none["lo"], none["hi"]) == (0, 50, 0.0, 0.0)  # no events: the interval is a point, so report the counts


def test_demotion_levels_on_hand_made_gates():
    gate = np.array([1.0, 0.733, 0.5, 0.4, np.nan])  # the last cell is "no vote"
    flag = np.array([False, False, False, False, False])
    levels = ev.demotion_levels(flag, gate)
    assert [v.tolist() for v in levels.values()] == [
        [False] * 5,  # flag
        [False, False, True, True, False],  # score halved or worse
        [False, True, True, True, False],  # any cut
    ]


def test_the_prf_metric_picks_the_named_number():
    y, f = np.array([1, 1, 0, 0, 1]), np.array([1, 0, 0, 1, 1])
    assert [ev.prf_metric(m)(y, f) for m in ("precision", "recall", "f1", "f2")] == pytest.approx(
        [2 / 3, 2 / 3, 2 / 3, 2 / 3])


def test_the_prior_is_chosen_on_validation_by_brier(monkeypatch):
    monkeypatch.setattr(ev, "BOOT", 10)
    cfg = dataclasses.replace(SMALL, tickets=1500)
    train, validation, report = (sm.simulate(cfg, seed) for seed in (61, 62, 63))
    out = ev.priors_eval(train, validation, report)
    sc = ev.score(validation)
    ok = sc.valid
    brier = {name: M.brier(sc.truth[ok], (a + sc.yes[ok]) / (a + b + sc.yes[ok] + sc.no[ok])) for name, (a, b) in ev.PRIORS.items()}  # Beta mean by hand
    assert out["chosen_on_validation"] == min(brier, key=brier.get)
    assert all(out["rows"][name]["validation_brier"] == pytest.approx(v) for name, v in brier.items())
    assert out["decision"] in (out["chosen_on_validation"], "(3,1) shipped")


def test_the_flag_threshold_is_chosen_on_validation_only(monkeypatch):
    monkeypatch.setattr(ev, "BOOT", 10)
    cfg = dataclasses.replace(SMALL, tickets=1500)
    validation = ev.score(sm.simulate(cfg, 71))
    one = ev.flag_eval(validation, ev.score(sm.simulate(cfg, 72)))
    other = ev.flag_eval(validation, ev.score(sm.simulate(dataclasses.replace(cfg, gone_before_votes=0.05), 73)))
    assert one["validation_best_f2_threshold"] == other["validation_best_f2_threshold"]  # the report split never enters the choice
    gone = (validation.truth == 0)[validation.valid]
    f2 = {t: M.prf(gone, ev.flagged_at(validation, t)[validation.valid], beta=2)["f"] for t in ev.THRESHOLDS}  # by hand, on every vote
    plateau = [t for t in ev.THRESHOLDS if f2[t] >= max(f2.values()) - 1e-12]
    assert one["validation_best_f2_threshold"] == plateau[len(plateau) // 2]
    assert one["validation_best_f2_threshold"] in ev.THRESHOLDS  # only the range asked for competes


def test_a_snapshot_counts_the_votes_up_to_the_day_and_judges_the_hazard_on_that_day(monkeypatch):
    monkeypatch.setattr(ev, "BOOT", 10)
    still = [(100.0, [(2.0, True)])] * 20  # a hazard that stays, one "still there" tap on day 2
    gone = [(1.0, [(2.0, False)])] * 20  # a hazard gone on day 1, one "gone" tap on day 2
    world = sm.from_timelines(still + gone)
    day7 = ev.snapshot_eval(world, days=(7,))[7]
    assert day7["share_gone"]["point"] == 0.5 and day7["no_vote_at_all"]["point"] == 0.0
    assert day7["belief_roc_auc"]["point"] == 1.0  # belief 5/6 for the hazards that stay, 4/6 for the gone ones
    assert day7["flag_recall_of_gone"]["point"] == 0.0 and day7["gone_with_belief_at_least_0.8"]["point"] == 0.0
    day1_5 = ev.snapshot_eval(world, days=(1.5,))[1.5]  # nobody has voted yet on day 1.5, and the hazards that end on day 1 are gone
    assert day1_5["no_vote_at_all"]["point"] == 1.0 and day1_5["belief_roc_auc"]["point"] == 0.5
    assert day1_5["gone_with_belief_at_least_0.8"]["point"] == 1.0


def test_a_verdict_needs_the_whole_interval_on_the_passing_side():
    row = {"belief": {"ece": {"hi": 0.049}, "roc_auc": {"lo": 0.76}}, "brier_belief_minus_always_0.8": {"hi": -0.01}}
    assert ev.verdict(row, 3) == {"ece_at_most_0.05": True, "brier_below_always_0.8": True, "roc_auc_at_least_0.75": True}
    row = {"belief": {"ece": {"hi": 0.06}, "roc_auc": {"lo": 0.74}}, "brier_belief_minus_always_0.8": {"hi": 0.001}}
    assert ev.verdict(row, 5) == {"ece_at_most_0.05": False, "brier_below_always_0.8": False, "roc_auc_at_least_0.75": False}
    assert "roc_auc_at_least_0.75" not in ev.verdict(row, 2)  # the AUC target starts at 3 votes


# ---- the whole pipeline is wired to the right labels ---------------------------------------------------------------------
def test_perfect_voters_rank_perfectly_and_coin_flip_voters_are_chance():
    perfect = ev.score(sm.simulate(sm.SimConfig(tickets=6000, sensitivity=1.0, specificity=1.0, noise=0.0), 21))
    for k in (1, 2, 3, 5):
        col = perfect.at(k)
        assert M.roc_auc(col["truth"], col["belief"]) == 1.0
    coin = ev.score(sm.simulate(sm.SimConfig(tickets=6000, sensitivity=0.5, specificity=0.5, noise=0.0), 21)).at(1)
    assert M.roc_auc(coin["truth"], coin["belief"]) == pytest.approx(0.5, abs=0.02)


def test_brier_and_ece_match_hand_math_when_no_hazard_ever_ends():
    # every hazard stays: one honest voter says "still there" with probability 0.85, so belief is 5/6 (yes) or 4/6 (no)
    world = sm.simulate(sm.SimConfig(tickets=60_000, gone_before_votes=0.0, staff_share=0.0, lifetime_means=(1e12,), noise=0.0, sensitivity=0.85), 41)
    col = ev.score(world).at(1)
    assert (col["truth"] == 1).all() and set(np.round(col["belief"], 4)) == {0.8333, 0.6667}
    assert M.brier(col["truth"], col["belief"]) == pytest.approx(0.85 * (1 / 6) ** 2 + 0.15 * (1 / 3) ** 2, abs=0.002)
    assert M.ece(col["truth"], col["belief"]) == pytest.approx(0.85 * (1 - 5 / 6) + 0.15 * (1 - 4 / 6), abs=0.005)


def test_belief_with_no_vote_is_the_always_0_8_forecast_so_it_cannot_beat_it_on_a_ticket_without_a_vote():
    assert lifecycle.belief(1, 0) == ev.FRESH


def test_a_tiny_run_writes_results_and_figures(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "BOOT", ev.BOOT)  # run() sets it; this puts it back afterwards
    monkeypatch.setattr(ev, "SWEEPS", {"noise": [("0.00", dict(noise=0.0)), ("0.10", dict(noise=0.1))]})
    payload = ev.run("validation", write=True, out=tmp_path, tickets=700, boot=12)
    written = {p.name for p in tmp_path.iterdir()}
    for stem in ("targets", "priors", "flag", "gate", "information", "sweeps"):
        assert f"lifecycle_{stem}.json" in written
        data = json.loads((tmp_path / f"lifecycle_{stem}.json").read_text())
        assert {"git_commit", "written"} <= set(data["meta"]) and data["seeds"] == list(ev.VALIDATION_SEEDS) and stem in data
    for figure in ("reliability", "priors", "flag", "information", "sweeps"):
        assert (tmp_path / f"lifecycle_{figure}.png").stat().st_size > 2000
    targets = payload["targets"]
    assert set(targets["by_votes"]) == set(ev.KS) and targets["overall"]["roc_auc_at_least_0.75"] in (True, False)
    assert payload["priors"]["decision"] in ev.PRIORS and payload["flag"]["validation_best_f2_threshold"] in ev.THRESHOLDS
    assert len(payload["flag"]["table"]) == len(ev.THRESHOLDS) + len(ev.EXTRA_THRESHOLDS)
    assert S.BELIEF_PRIOR == (3, 1) and S.LIKELY_GONE_BELOW == 0.45  # nothing was left overridden
