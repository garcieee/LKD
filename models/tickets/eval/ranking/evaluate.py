"""Evaluate the shipped priority score (ranking/priority.py) against the five raters. What it found: REPORT.md.

    models/.venv/bin/python -m models.tickets.eval.ranking.aggregate    # the labels: data/consensus.json, results/ranking_raters.*
    models/.venv/bin/python -m models.tickets.eval.ranking.fit          # the fitted weights: results/ranking_fit.*
    models/.venv/bin/python -m models.tickets.eval.ranking.evaluate     # this file: results/ranking_score, _baselines, _personas, _disagreements, _sensitivity, _targets

The score is always the real priority.score, recomputed from the answer key's ticket attributes (a stored score is only
cross-checked). A variant (an ablation, other weights, a perturbation) overrides the settings for the length of the call and puts
them back, so it runs the same code as the app. Every number is on one named split of the survey, never mixed: pairs and tickets are
split 60/20/20 by ticket, the pre-registered numbers are the test split, and "all" (train, validation and test together) is only a
larger sample for the shipped score, whose hand-set weights were never fitted to this survey. Every metric comes from
eval/common/metrics.py; every test number has a 1,000-resample bootstrap interval over pairs (or over tickets, for ticket metrics).
"""
import importlib.util
import json
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from models.tickets import settings as S
from models.tickets.eval.common import metrics as M
from models.tickets.eval.common import plots, results
from models.tickets.eval.ranking import aggregate as ag
from models.tickets.eval.ranking import pairs
from models.tickets.ranking import priority
from models.tickets.types import CATEGORIES, TicketFacts

import matplotlib.pyplot as plt  # noqa: E402  (after common.plots, which selects the Agg backend)

BOOT, SEED = ag.BOOT, ag.SEED
PARTS = ("danger", "reports", "foot_traffic", "waiting")
SUBSETS = ("majority", "consensus", "unanimous")
SPLITS = ("train", "validation", "test", "all")
SERVER_PRIORITY = Path(__file__).resolve().parents[4] / "server" / "app" / "services" / "priority.py"  # the dashboard's integer severity 1-3
TARGETS = {"accuracy": 0.80, "ceiling_ratio": 0.90, "tau_b": 0.60, "ndcg_at_10": 0.85}  # EVALUATION.md, "Priority score"
SHIPPED = "shipped score"


# ---- running the real score ------------------------------------------------------------------------------------------
@contextmanager
def override(**values):
    """Set settings for the length of a call (a weight table, a floor) and always put them back."""
    old = {name: getattr(S, name) for name in values}  # an unknown name fails here, loudly
    try:
        for name, value in values.items():
            setattr(S, name, value)
        yield
    finally:
        for name, value in old.items():
            setattr(S, name, value)


def facts_of(t: dict) -> TicketFacts:
    return TicketFacts(t["category"], t["reporters"], t["gone_votes"], t["days_open"], t["foot_traffic"], t["danger"])


def shipped(truth, facts=facts_of, **settings) -> list:
    """The real priority.score of every ticket, under the settings overrides given (none: the settings as they are)."""
    with override(**settings):
        return [priority.score(facts(t)) for t in truth]


def score_array(truth, **settings) -> np.ndarray:
    return np.array([b.score for b in shipped(truth, **settings)])


def parts_array(truth, **settings) -> np.ndarray:
    """(tickets, 4): the danger, reports, foot traffic and waiting parts, each 0..1, as priority.score computes them."""
    return np.array([[b.parts[p] for p in PARTS] for b in shipped(truth, **settings)])


def dashboard_severity():
    """severity() of server/app/services/priority.py, loaded from its file (the server is not on this path): the dashboard's 1-3."""
    spec = importlib.util.spec_from_file_location("lakad_server_priority", SERVER_PRIORITY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.severity


def dashboard_keys(truth) -> np.ndarray:
    """A number per ticket that sorts like the dashboard's queue: unresolved first, then severity 1-3 (high first), then oldest first.
    Every survey ticket is open, so 'unresolved first' separates nothing. Equal numbers are ties: with no arrival order, no preference."""
    severity = dashboard_severity()
    rows = [(severity(t["category"]), t["days_open"]) for t in truth]
    rank = {row: i for i, row in enumerate(sorted(set(rows)))}
    return np.array([rank[row] for row in rows], float)


def comparator_keys(truth) -> dict[str, np.ndarray]:
    """name -> one number per ticket; a pair is called for the ticket with the larger number, equal numbers count half.
    The uncapped rows are diagnostics for two caveats: the score counts at most 8 people and 14 days, the raters saw up to 12 and 30."""
    score, parts = score_array(truth), parts_array(truth)
    return {SHIPPED: score, "severity only": parts[:, 0], "reports only": parts[:, 1], "foot traffic only": parts[:, 2], "waiting only": parts[:, 3],
            "dashboard order": dashboard_keys(truth), "random": np.zeros(len(truth)),
            "reports only (uncapped count)": np.array([t["reporters"] for t in truth], float),
            "waiting only (uncapped days)": np.array([t["days_open"] for t in truth], float)}


# ---- views of the survey ---------------------------------------------------------------------------------------------
def check_split(split: str) -> str:
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}, got {split!r}")
    return split


def pair_mask(survey, labels, split: str, subset: str = "majority") -> np.ndarray:
    """Boolean over pair rows: base pairs of that split that have a label of that set. 'all' is every split."""
    mask = labels.subset(subset)
    return mask if check_split(split) == "all" else mask & (survey.split == split)


def ticket_mask(survey, split: str) -> np.ndarray:
    return np.ones(len(survey.ticket_ids), bool) if check_split(split) == "all" else survey.ticket_split == split


def acc_of_diff(y, d):
    """Pairwise accuracy of a comparator given its score difference (first minus second) per pair: for paired_bootstrap_diff."""
    d = np.asarray(d, float)
    return M.pairwise_accuracy(d, np.zeros_like(d), y)


def accuracy_ci(key, survey, mask, wins, boot: int = BOOT) -> M.CI:
    return M.bootstrap_ci(M.pairwise_accuracy, key[survey.a[mask]], key[survey.b[mask]], wins, n=boot, seed=SEED)


def difference_ci(key_x, key_y, survey, mask, wins, boot: int = BOOT) -> M.CI:
    """Accuracy of x minus accuracy of y on the same resampled pairs. If the interval excludes 0, the difference is real."""
    dx, dy = key_x[survey.a[mask]] - key_x[survey.b[mask]], key_y[survey.a[mask]] - key_y[survey.b[mask]]
    return M.paired_bootstrap_diff(acc_of_diff, wins, dx, dy, n=boot, seed=SEED)


def dyadic_ci(correct, a, b, boot: int = BOOT, seed: int = SEED, alpha: float = 0.05) -> M.CI:
    """Interval for a mean over pairs that share tickets: resample the TICKETS, and a pair counts as often as its two tickets are
    drawn together (the product of the two draw counts). The plain pair bootstrap treats pairs as independent, which they are not
    when a ticket sits in several pairs; this one does not."""
    correct = np.asarray(correct, float)
    tickets, index = np.unique(np.concatenate([a, b]), return_inverse=True)
    ia, ib = index[: len(a)], index[len(a):]
    draws = np.random.default_rng(seed).multinomial(len(tickets), np.full(len(tickets), 1 / len(tickets)), size=boot)
    weight = (draws[:, ia] * draws[:, ib]).astype(float)
    kept = weight.sum(1) > 0
    values = weight[kept] @ correct / weight[kept].sum(1)
    lo, hi = np.percentile(values, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return M.CI(float(correct.mean()), float(lo), float(hi))


def ratio_to_ceiling(sa, sb, wins, choice) -> float:
    """Pairwise accuracy over the human ceiling (the leave-one-rater-out agreement) on the same pairs."""
    return M.pairwise_accuracy(sa, sb, wins) / ag.ceiling(choice)


def vs_loro(sa, sb, choice) -> float:
    """The score's mean agreement with each rater's leave-one-rater-out majority, over the mean agreement of the raters themselves,
    on the same (rater, pair) cells: a like-for-like ratio, since each rater faces a majority of four, not five."""
    reference = ag.loro_reference(choice)
    sa, sb = np.asarray(sa), np.asarray(sb)
    own = ag.loro_agreement(choice)
    usable = [r for r in range(choice.shape[1]) if (reference[:, r] >= 0).any()]
    score = [M.pairwise_accuracy(sa[reference[:, r] >= 0], sb[reference[:, r] >= 0], reference[reference[:, r] >= 0, r] == ag.A) for r in usable]
    return float(np.mean(score) / np.mean(own[usable]))


# ---- the shipped score against the panel -----------------------------------------------------------------------------
def headline(survey, labels, key, split: str = "test", boot: int = BOOT, subsets=SUBSETS) -> dict:
    """Pairwise accuracy against the majority, consensus and unanimous labels, the human ceiling on the same pairs, their ratio,
    and the same ratio measured like for like. `key` is the score (or any comparator) per ticket."""
    out = {}
    for subset in subsets:
        mask = pair_mask(survey, labels, split, subset)
        wins, choice = labels.winner[mask] == ag.A, survey.choice[mask]
        sa, sb = key[survey.a[mask]], key[survey.b[mask]]
        correct = [M.pairwise_accuracy([x], [y], [w]) for x, y, w in zip(sa, sb, wins)]
        out[subset] = {"split": split, "n_pairs": int(mask.sum()),
                       "accuracy": M.bootstrap_ci(M.pairwise_accuracy, sa, sb, wins, n=boot, seed=SEED).as_dict(),
                       "accuracy_ticket_resampled": dyadic_ci(correct, survey.a[mask], survey.b[mask], boot).as_dict(),
                       "ceiling": M.bootstrap_ci(ag.ceiling, choice, n=boot, seed=SEED).as_dict(),
                       "ratio_to_ceiling": M.bootstrap_ci(ratio_to_ceiling, sa, sb, wins, choice, n=boot, seed=SEED).as_dict(),
                       "ratio_to_ceiling_like_for_like": M.bootstrap_ci(vs_loro, sa, sb, choice, n=boot, seed=SEED).as_dict()}
    return out


def by_stratum(survey, labels, key, split: str = "test", boot: int = BOOT) -> dict:
    out = {}
    for stratum in ag.STRATA:
        mask = pair_mask(survey, labels, split, "majority") & (survey.stratum == stratum)
        wins, choice = labels.winner[mask] == ag.A, survey.choice[mask]
        out[stratum] = {"split": split, "n_pairs": int(mask.sum()), "accuracy": accuracy_ci(key, survey, mask, wins, boot).as_dict(),
                        "ceiling": M.bootstrap_ci(ag.ceiling, choice, n=boot, seed=SEED).as_dict(),
                        "ratio_to_ceiling": M.bootstrap_ci(ratio_to_ceiling, key[survey.a[mask]], key[survey.b[mask]], wins, choice, n=boot, seed=SEED).as_dict()}
    return out


def by_rater(survey, key, split: str = "test", boot: int = BOOT) -> dict:
    """The score against each rater's own choices (that rater's ties left out) on the base pairs of the split, next to the
    rater's agreement with the other four on the same pairs."""
    base = survey.base if split == "all" else survey.base & (survey.split == check_split(split))
    own = ag.loro_agreement(survey.choice[base])
    out = {}
    for r, name in enumerate(survey.raters):
        mask = base & (survey.choice[:, r] != ag.TIE)
        wins = survey.choice[mask, r] == ag.A
        out[name] = {"split": split, "n_pairs": int(mask.sum()), "accuracy": accuracy_ci(key, survey, mask, wins, boot).as_dict(), "rater_vs_other_four": float(own[r])}
    return out


def ticket_metrics(survey, scores, split: str = "test", boot: int = BOOT) -> dict:
    """Kendall tau-b, Spearman and NDCG@10 between the score and the panel's mean urgency over the tickets of a split."""
    mask = ticket_mask(survey, split)
    relevance, s = ag.mean_urgency(survey)[mask], np.asarray(scores)[mask]
    ci = lambda metric, *arrays: M.bootstrap_ci(metric, *arrays, n=boot, seed=SEED).as_dict()
    return {"split": split, "n_tickets": int(mask.sum()), "kendall_tau_b": ci(M.kendall_tau_b, s, relevance), "spearman": ci(M.spearman, s, relevance),
            "ndcg_at_10": ci(M.ndcg_at_k, relevance, s)}


def accuracy_by_stratum(survey, labels, keys: dict, split: str = "test") -> dict:
    """name -> stratum -> {n, accuracy}: where on the survey's three kinds of pair each comparator is right. Points only: 14 to 48 pairs a cell."""
    out = {}
    for name, key in keys.items():
        out[name] = {}
        for stratum in ag.STRATA:
            mask = pair_mask(survey, labels, split, "majority") & (survey.stratum == stratum)
            out[name][stratum] = {"n": int(mask.sum()), "accuracy": M.pairwise_accuracy(key[survey.a[mask]], key[survey.b[mask]], labels.winner[mask] == ag.A)}
    return out


def stratum_shares(survey, split: str) -> dict:
    """How common each kind of pair is among ALL pairs of the split's tickets, by the build-time score gap that defined the strata:
    clear (more than 15 points apart), close (less than 5) and the pairs in between. The survey draws a third of each of clear, close
    and trade-off pairs and none of the plain in-between ones."""
    score = np.array([t["score"] for t, keep in zip(survey.truth, ticket_mask(survey, split)) if keep])
    gap = np.abs(score[:, None] - score[None, :])[np.triu_indices(len(score), 1)]
    return {"clear": float((gap > pairs.CLEAR_GAP).mean()), "close": float((gap < pairs.CLOSE_GAP).mean()),
            "between": float(((gap >= pairs.CLOSE_GAP) & (gap <= pairs.CLEAR_GAP)).mean())}


def post_stratified(survey, labels, keys: dict, split: str = "test", reference: str = SHIPPED, boot: int = BOOT, seed: int = SEED) -> dict:
    """What the accuracy would be if the pairs had been drawn at random instead of a third each from clear, close and trade-off. The strata
    are reweighted to their share of all pairs of the split's tickets; the in-between pairs, which the survey never drew, are assumed to
    behave like the trade-off pairs (the only mixed pairs there are). Intervals come from resampling pairs inside each stratum. The ceiling
    is reweighted alike, so the ratio is on the same mix. A what-if, not a pre-registered number."""
    shares = stratum_shares(survey, split)
    weight = {"clear": shares["clear"], "close": shares["close"], "trade_off": shares["between"]}
    rows = {s: np.flatnonzero(pair_mask(survey, labels, split) & (survey.stratum == s)) for s in weight}

    def estimate(pick):
        ceiling = sum(weight[s] * ag.ceiling(survey.choice[r]) for s, r in pick.items())
        accuracy = {n: sum(weight[s] * M.pairwise_accuracy(k[survey.a[r]], k[survey.b[r]], labels.winner[r] == ag.A) for s, r in pick.items()) for n, k in keys.items()}
        return ceiling, accuracy

    point_ceiling, point = estimate(rows)
    rng = np.random.default_rng(seed)
    draws = [estimate({s: rng.choice(r, len(r)) for s, r in rows.items()}) for _ in range(boot)]
    interval = lambda values, centre: M.CI(float(centre), *map(float, np.percentile(values, [2.5, 97.5]))).as_dict()
    out = {"split": split, "shares": shares, "assumption": "in-between pairs behave like the trade-off pairs", "pairs_by_stratum": {s: int(len(r)) for s, r in rows.items()},
           "ceiling": interval([c for c, _ in draws], point_ceiling), "rows": {}}
    for name in keys:
        row = {"accuracy": interval([a[name] for _, a in draws], point[name]),
               "ratio_to_ceiling": interval([a[name] / c for c, a in draws], point[name] / point_ceiling)}
        if name != reference:
            row["minus_reference"] = interval([a[name] - a[reference] for _, a in draws], point[name] - point[reference])
        out["rows"][name] = row
    return out


def compare_block(survey, labels, split: str, keys: dict, reference: str = SHIPPED, reference_first: bool = True, boot: int = BOOT) -> dict:
    """Every comparator in `keys` on the same pairs: its accuracy, and its paired difference with the reference.
    reference_first: reference minus comparator (a baseline: above 0 means the score wins); else comparator minus reference (a variant: its change)."""
    out = {}
    for subset in SUBSETS:
        mask = pair_mask(survey, labels, split, subset)
        wins = labels.winner[mask] == ag.A
        rows = {}
        for name, key in keys.items():
            row = {"accuracy": accuracy_ci(key, survey, mask, wins, boot).as_dict()}
            if name != reference:
                diff = difference_ci(keys[reference], key, survey, mask, wins, boot) if reference_first else difference_ci(key, keys[reference], survey, mask, wins, boot)
                row["reference_minus_this" if reference_first else "this_minus_reference"] = diff.as_dict()
            rows[name] = row
        out[subset] = {"split": split, "n_pairs": int(mask.sum()), "rows": rows}
    return out


# ---- ablations -------------------------------------------------------------------------------------------------------
def renormalised(drop: str) -> dict:
    """The weights with one part dropped and the others scaled to sum to 1 again."""
    rest = {k: v for k, v in S.WEIGHTS.items() if k != drop}
    total = sum(rest.values())
    return {**{k: v / total for k, v in rest.items()}, drop: 0.0}


def ablation_settings() -> dict[str, dict]:
    """name -> settings overrides. Each switches off one thing the score does."""
    return {**{f"drop {p.replace('_', ' ')} part": {"WEIGHTS": renormalised(p)} for p in PARTS},
            "drop the gate": {"GATE_MIN": 1.0}, "drop the floors": {"FLOORS": {}}, "drop the danger bonus": {"DANGER_BONUS": 0.0},
            "drop gate, floors and bonus": {"GATE_MIN": 1.0, "FLOORS": {}, "DANGER_BONUS": 0.0}}


def ablation_keys(truth) -> dict[str, np.ndarray]:
    return {SHIPPED: score_array(truth), **{name: score_array(truth, **settings) for name, settings in ablation_settings().items()}}


# ---- sensitivity -----------------------------------------------------------------------------------------------------
def perturbed(rng, weights: dict, spread: float) -> dict:
    """Each weight times a random factor within plus or minus `spread`, scaled to sum to 1 again."""
    w = {k: v * (1 + rng.uniform(-spread, spread)) for k, v in weights.items()}
    total = sum(w.values())
    return {k: v / total for k, v in w.items()}


def sensitivity(survey, labels, split: str = "test", n: int = 500, spread: float = 0.30, seed: int = 2026) -> dict:
    """n random weight sets: the pairwise accuracy of each on the split's pairs and its Kendall tau with the shipped ranking of all 200 tickets."""
    base = score_array(survey.truth)
    mask = pair_mask(survey, labels, split, "majority")
    wins = labels.winner[mask] == ag.A
    rng = np.random.default_rng(seed)
    accuracy, tau = [], []
    for _ in range(n):
        s = score_array(survey.truth, WEIGHTS=perturbed(rng, S.WEIGHTS, spread))
        accuracy.append(M.pairwise_accuracy(s[survey.a[mask]], s[survey.b[mask]], wins))
        tau.append(M.kendall_tau_b(base, s))
    summary = lambda v: {"min": float(np.min(v)), "p5": float(np.percentile(v, 5)), "median": float(np.median(v)), "p95": float(np.percentile(v, 95)), "max": float(np.max(v)), "mean": float(np.mean(v)), "sd": float(np.std(v))}
    shipped_accuracy = M.pairwise_accuracy(base[survey.a[mask]], base[survey.b[mask]], wins)
    return {"split": split, "n_pairs": int(mask.sum()), "n_perturbations": n, "spread": spread, "seed": seed, "shipped_accuracy": shipped_accuracy,
            "accuracy": summary(accuracy), "kendall_tau_vs_shipped_ranking": summary(tau),
            "share_accuracy_at_least_shipped": float(np.mean(np.array(accuracy) >= shipped_accuracy)),
            "share_accuracy_at_least_target": float(np.mean(np.array(accuracy) >= TARGETS["accuracy"])),
            "accuracy_values": [round(float(v), 4) for v in accuracy], "tau_values": [round(float(v), 4) for v in tau]}


# ---- where the score and the panel disagree ---------------------------------------------------------------------------
def describe_side(survey, key, t: int) -> dict:
    truth = survey.truth[t]
    return {"ticket": survey.ticket_ids[t], "description": survey.description[t], "score": float(key[t]), "category": truth["category"],
            "reporters": truth["reporters"], "gone_votes": truth["gone_votes"], "days_open": truth["days_open"], "danger_note": truth["danger"],
            "named_place": truth["place"] is not None, "foot_traffic": truth["foot_traffic"]}


def disagreements(survey, labels, key, split: str = "test", limit: int = 15) -> dict:
    """The labelled pairs of a split where the score picks the other ticket than the rater majority (a score tie counts as a
    disagreement). Strongest rater majority first, then the larger score gap. `pairs` lists at most `limit`; `total` is how many exist
    and `pattern` summarises all of them."""
    mask = pair_mask(survey, labels, split, "majority")
    rows = []
    for k in np.flatnonzero(mask):
        a, b = survey.a[k], survey.b[k]
        raters_pick, other = (a, b) if labels.winner[k] == ag.A else (b, a)
        if key[raters_pick] > key[other]:
            continue
        rows.append({"pair": survey.pair_ids[k], "stratum": str(survey.stratum[k]), "votes_for_raters_pick": int(labels.support[k]),
                     "votes": labels.votes[k].tolist(), "score_gap": float(abs(key[a] - key[b])),
                     "raters_chose": describe_side(survey, key, raters_pick), "score_chose": describe_side(survey, key, other)})
    rows.sort(key=lambda r: (-r["votes_for_raters_pick"], -r["score_gap"]))
    return {"split": split, "labelled_pairs": int(mask.sum()), "total": len(rows), "listed": min(limit, len(rows)), "pairs": rows[:limit], "pattern": pattern_summary(rows),
            "by_stratum": dict(Counter(r["stratum"] for r in rows))}


def pattern_summary(rows: list) -> dict:
    """What the disagreements have in common: the kinds of hazard on each side and how often a side has a note, 'gone' votes, a wait past
    the cap, or no named place."""
    flag = lambda side, f: sum(bool(f(r[side])) for r in rows)
    cats = lambda side: {c: flag(side, lambda s, c=c: s["category"] == c) for c in CATEGORIES}
    out = {"n": len(rows), "raters_chose_category": cats("raters_chose"), "score_chose_category": cats("score_chose")}
    for name, f in {"danger_note": lambda s: s["danger_note"], "gone_votes": lambda s: s["gone_votes"] > 0, "open_past_cap": lambda s: s["days_open"] > S.WAITING_FULL_DAYS,
                    "no_named_place": lambda s: not s["named_place"]}.items():
        out[name] = {"raters_chose": flag("raters_chose", f), "score_chose": flag("score_chose", f)}
    return out


FEATURES = {  # one-sided features of a ticket: what a pair can differ in
    "has a danger note": lambda t: bool(t["danger"]),
    "has 'gone' votes": lambda t: t["gone_votes"] > 0,
    "has a named place nearby": lambda t: t["place"] is not None,
    "open past the waiting cap": lambda t: t["days_open"] > S.WAITING_FULL_DAYS,
    "labelled a very busy area": lambda t: t["foot_traffic"] > 0.65,
    **{f"is a {c}": (lambda t, c=c: t["category"] == c) for c in CATEGORIES},
}


def lean(survey, key, rows: np.ndarray, picked: np.ndarray, feature, boot: int = BOOT) -> dict:
    """Among the pairs in `rows` where exactly one ticket has the feature: how often the labeller (picked: 0 A, 1 B per pair) chooses
    the ticket that has it, how often the score does, and the interval of the gap. A positive gap: the labeller leans on the feature more than the score."""
    has = np.array([bool(feature(t)) for t in survey.truth])
    rows = rows[has[survey.a[rows]] != has[survey.b[rows]]]
    if not len(rows):
        return {"n": 0}
    a_has, picked = has[survey.a[rows]], picked[rows]
    sa, sb = key[survey.a[rows]], key[survey.b[rows]]
    labeller = np.where(picked == ag.A, a_has, ~a_has).astype(float)
    score = np.where(sa == sb, 0.5, np.where(sa > sb, a_has, ~a_has)).astype(float)
    gap = M.bootstrap_ci(lambda x, y: float(np.mean(x) - np.mean(y)), labeller, score, n=boot, seed=SEED)
    return {"n": int(len(rows)), "labeller_picks_it": float(labeller.mean()), "score_picks_it": float(score.mean()), "gap": gap.as_dict()}


def lean_tables(survey, labels, key, splits=("train", "validation"), boot: int = BOOT) -> dict:
    """The lean of the panel's majority for each feature on the labelled pairs of the given splits. The hand-set score was not
    fitted to any pair, so any split is fair; the evidence behind a recommendation uses train and validation, test replicates it."""
    rows = np.flatnonzero((labels.winner >= 0) & np.isin(survey.split, splits))
    return {name: lean(survey, key, rows, labels.winner, f, boot) for name, f in FEATURES.items()}


def cap_check(survey, labels, key, splits=("train", "validation"), boot: int = BOOT) -> dict:
    """Does the 14-day cap hide a difference the raters saw? Among labelled pairs where both tickets are past the cap and differ in
    days: how often the panel picks the ticket open longer, and how often the score does (it sees no waiting difference there)."""
    rows = np.flatnonzero((labels.winner >= 0) & np.isin(survey.split, splits))
    days = np.array([t["days_open"] for t in survey.truth])
    rows = rows[(days[survey.a[rows]] > S.WAITING_FULL_DAYS) & (days[survey.b[rows]] > S.WAITING_FULL_DAYS) & (days[survey.a[rows]] != days[survey.b[rows]])]
    if not len(rows):
        return {"n": 0}
    a_longer = days[survey.a[rows]] > days[survey.b[rows]]
    panel = np.where(labels.winner[rows] == ag.A, a_longer, ~a_longer).astype(float)
    sa, sb = key[survey.a[rows]], key[survey.b[rows]]
    score = np.where(sa == sb, 0.5, np.where(sa > sb, a_longer, ~a_longer)).astype(float)
    return {"n": int(len(rows)), "panel_picks_longer_open": M.bootstrap_ci(np.mean, panel, n=boot, seed=SEED).as_dict(),
            "score_picks_longer_open": M.bootstrap_ci(np.mean, score, n=boot, seed=SEED).as_dict()}


# ---- personas --------------------------------------------------------------------------------------------------------
def persona_block(survey, key, split: str = "test", boot: int = BOOT) -> dict:
    """Does the score agree with each persona differently? Per persona: accuracy against its own choices on the pairs of the split
    where nobody tied, and the same minus the score's accuracy against the other four personas' choices (paired over pairs)."""
    base = survey.base if split == "all" else survey.base & (survey.split == check_split(split))
    rows = np.flatnonzero(base & (survey.choice != ag.TIE).all(axis=1))
    sa, sb = key[survey.a[rows]], key[survey.b[rows]]
    correct = np.array([[M.pairwise_accuracy([x], [y], [survey.choice[k, r] == ag.A]) for x, y, k in zip(sa, sb, rows)] for r in range(len(survey.raters))])  # (raters, pairs)
    out = {"split": split, "n_pairs": int(len(rows))}
    for r, name in enumerate(survey.raters):
        others = np.delete(correct, r, axis=0).mean(0)
        out[name] = {"accuracy": M.bootstrap_ci(np.mean, correct[r], n=boot, seed=SEED).as_dict(),
                     "minus_other_four": M.bootstrap_ci(lambda x, y: float(np.mean(x) - np.mean(y)), correct[r], others, n=boot, seed=SEED).as_dict()}
    return out


def persona_lean(survey, key, splits=("train", "validation"), boot: int = BOOT) -> dict:
    """The lean of each persona (its own choices on the base pairs of the given splits, its ties left out) on every feature: where a
    persona weighs something the score does not. This is the table behind 'the wheelchair user ranks blocked sidewalks higher'."""
    base = np.flatnonzero(survey.base & np.isin(survey.split, splits))
    return {name: {f: lean(survey, key, base[survey.choice[base, r] != ag.TIE], survey.choice[:, r], feature, boot) for f, feature in FEATURES.items()}
            for r, name in enumerate(survey.raters)}


# ---- the targets -----------------------------------------------------------------------------------------------------
def target_row(name: str, ci: dict, threshold: float, **extra) -> dict:
    """met: the point estimate reaches the threshold. interval_clears: even the lower end of the 95% interval does."""
    return {"target": name, "threshold": threshold, "value": ci["point"], "lo": ci["lo"], "hi": ci["hi"], "met": ci["point"] >= threshold,
            "interval_clears": ci["lo"] >= threshold, "shortfall": max(0.0, threshold - ci["point"]), **extra}


def beat_row(name: str, ci: dict, **extra) -> dict:
    """'Beats X': the 95% interval of (score minus X) lies above zero."""
    return {"target": name, "threshold": 0.0, "value": ci["point"], "lo": ci["lo"], "hi": ci["hi"], "met": ci["lo"] > 0, "interval_clears": ci["lo"] > 0, **extra}


def target_rows(head: dict, tickets: dict, baselines: dict, fit: dict | None) -> list[dict]:
    """The pre-registered targets for ranking (EVALUATION.md), on the test split. The accuracy and ceiling targets are checked on the
    three label sets: 'majority' (every pair with a label) is the primary reading of 'pairs where the raters agree'."""
    rows = []
    for subset in SUBSETS:
        h = head[subset]
        rows.append(target_row("pairwise accuracy >= 0.80", h["accuracy"], TARGETS["accuracy"], labels=subset, n=h["n_pairs"]))
        rows.append(target_row("accuracy >= 0.90 x leave-one-rater-out ceiling", h["ratio_to_ceiling"], TARGETS["ceiling_ratio"], labels=subset, n=h["n_pairs"], ceiling=h["ceiling"]["point"]))
        rows.append(target_row("accuracy >= 0.90 x ceiling, like for like", h["ratio_to_ceiling_like_for_like"], TARGETS["ceiling_ratio"], labels=subset, n=h["n_pairs"]))
    rows.append(target_row("Kendall tau-b >= 0.60 (mean urgency)", tickets["kendall_tau_b"], TARGETS["tau_b"], n=tickets["n_tickets"]))
    rows.append(target_row("NDCG@10 >= 0.85 (mean urgency)", tickets["ndcg_at_10"], TARGETS["ndcg_at_10"], n=tickets["n_tickets"]))
    for subset in SUBSETS:
        for name in ("severity only", "dashboard order"):
            rows.append(beat_row(f"beats {name}", baselines[subset]["rows"][name]["reference_minus_this"], labels=subset, n=baselines[subset]["n_pairs"]))
    if fit:
        d = fit["decision"]
        rows.append({"target": "fitted weights replace hand weights only if +3 points on validation and non-negative", "threshold": d["margin"], "value": d["validation_gain"],
                     "met": d["replace"], "replace": d["replace"], "non_negative": d["non_negative"], "note": "met = the rule says replace"})
    return rows


# ---- figures ---------------------------------------------------------------------------------------------------------
def figure_baselines(path: Path, block: dict, ceiling: float) -> None:
    rows = block["majority"]["rows"]
    names = [n for n in rows if "uncapped" not in n]
    plots.save_bars(path, names, [rows[n]["accuracy"]["point"] for n in names], [rows[n]["accuracy"]["lo"] for n in names], [rows[n]["accuracy"]["hi"] for n in names],
                    title=f"Test pairs: accuracy against the panel majority (human ceiling {ceiling:.2f})", ylabel="pairwise accuracy", target=TARGETS["accuracy"])


def figure_ablations(path: Path, block: dict) -> None:
    rows = {n: r for n, r in block["majority"]["rows"].items() if n != SHIPPED}
    fig, ax = plt.subplots(figsize=(7, 0.45 * len(rows) + 1.2))
    y = np.arange(len(rows))[::-1]
    point = np.array([r["this_minus_reference"]["point"] for r in rows.values()])
    lo, hi = np.array([r["this_minus_reference"]["lo"] for r in rows.values()]), np.array([r["this_minus_reference"]["hi"] for r in rows.values()])
    ax.errorbar(point, y, xerr=[point - lo, hi - point], fmt="o", color="#212e4a", capsize=3)
    ax.axvline(0, color=plots.FAINT, lw=1)
    ax.set(yticks=y, yticklabels=list(rows), xlabel="change in pairwise accuracy (test, ablated minus shipped)", title="Ablations: what each part is worth")
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def figure_sensitivity(path: Path, block: dict) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.4))
    ax1.hist(block["accuracy_values"], bins=15, color="#212e4a", alpha=0.85)
    ax1.axvline(block["shipped_accuracy"], color="#a63722", ls="--", label=f"shipped {block['shipped_accuracy']:.3f}")
    ax1.axvline(TARGETS["accuracy"], color=plots.FAINT, ls=":", label="target 0.80")
    ax1.set(xlabel="pairwise accuracy (test pairs)", ylabel="weight sets", title="500 weight sets, each within 30%")
    ax1.legend(fontsize=7)
    ax2.hist(block["tau_values"], bins=15, color="#5b7aa6", alpha=0.9)
    ax2.set(xlabel="Kendall tau with the shipped ranking (200 tickets)", title="How far the ranking moves")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ---- everything --------------------------------------------------------------------------------------------------------
def run(survey, labels, fit: dict | None = None, boot: int = BOOT, perturbations: int = 500) -> dict[str, dict]:
    """Every payload of this module, by results file name. `fit` is results/ranking_fit.json, if it has been written."""
    truth = survey.truth
    keys = comparator_keys(truth)
    key = keys[SHIPPED]
    stored = np.array([t["score"] for t in truth])
    head = headline(survey, labels, key, "test", boot)
    base_block = {"test": compare_block(survey, labels, "test", keys, boot=boot),
                  "all": compare_block(survey, labels, "all", keys, boot=boot)}
    abl_keys = ablation_keys(truth)
    ablations = {"test": compare_block(survey, labels, "test", abl_keys, reference_first=False, boot=boot),
                 "all": compare_block(survey, labels, "all", abl_keys, reference_first=False, boot=boot)}
    tickets = {"test": ticket_metrics(survey, key, "test", boot), "all": ticket_metrics(survey, key, "all", boot)}
    dis = {"test": disagreements(survey, labels, key, "test"), **{s: disagreements(survey, labels, key, s, limit=0) for s in ("validation", "train")}}
    config = {"bootstrap": boot, "seed": SEED, "targets": TARGETS}
    files = {
        "ranking_score": {"config": config, "recomputed_vs_stored_max_abs_difference": float(np.abs(key - stored).max()), "headline": head,
                          "strata": by_stratum(survey, labels, key, "test", boot), "raters": by_rater(survey, key, "test", boot), "tickets": tickets,
                          "post_stratified": {s: post_stratified(survey, labels, {SHIPPED: key}, s, boot=boot) for s in ("test", "all")},
                          "other_splits": {s: headline(survey, labels, key, s, boot, ("majority",))["majority"] for s in ("train", "validation", "all")}},
        "ranking_baselines": {"config": config, "baselines": base_block, "ablations": ablations,
                              "post_stratified": {s: post_stratified(survey, labels, keys, s, boot=boot) for s in ("test", "all")},
                              "by_stratum": {s: accuracy_by_stratum(survey, labels, keys, s) for s in ("test", "all")}},
        "ranking_personas": {"config": config, "test": persona_block(survey, key, "test", boot), "all": persona_block(survey, key, "all", boot),
                             "by_rater_all_pairs": by_rater(survey, key, "all", boot),
                             "lean": {"train_validation": persona_lean(survey, key, ("train", "validation"), boot), "test": persona_lean(survey, key, ("test",), boot)}},
        "ranking_disagreements": {"config": config, "splits": dis,
                                  "lean_panel": {"train_validation": lean_tables(survey, labels, key, ("train", "validation"), boot), "test": lean_tables(survey, labels, key, ("test",), boot)},
                                  "cap_check": {"train_validation": cap_check(survey, labels, key, ("train", "validation"), boot), "test": cap_check(survey, labels, key, ("test",), boot)}},
        "ranking_sensitivity": {"config": config, **sensitivity(survey, labels, "test", perturbations)},
    }
    files["ranking_targets"] = {"config": config, "split": "test", "primary_label_set": "majority",
                                "rows": target_rows(head, tickets["test"], base_block["test"], fit)}
    fitted = ((fit or {}).get("bradley_terry") or {}).get("fitted_weights")
    if fitted:  # the same targets for the Bradley-Terry weights, which the pre-registered rule may promote: read the selection caveats in REPORT.md
        fitted_key = score_array(truth, WEIGHTS=fitted)
        files["ranking_targets"]["rows_if_fitted_weights_adopted"] = target_rows(
            headline(survey, labels, fitted_key, "test", boot), ticket_metrics(survey, fitted_key, "test", boot),
            compare_block(survey, labels, "test", {**keys, SHIPPED: fitted_key}, boot=boot), None)
    return files


def main() -> None:
    done = ag.run()
    survey, labels = done["survey"], done["labels"]
    fit_path = results.RESULTS / "ranking_fit.json"
    fit = json.loads(fit_path.read_text()) if fit_path.exists() else None
    if fit is None:
        print("no results/ranking_fit.json yet: run models.tickets.eval.ranking.fit first for the weights row of the targets")
    files = run(survey, labels, fit)
    for name, payload in files.items():
        print("wrote", results.write_result(name, payload))
    figure_baselines(results.RESULTS / "ranking_baselines.png", files["ranking_baselines"]["baselines"]["test"], files["ranking_score"]["headline"]["majority"]["ceiling"]["point"])
    figure_ablations(results.RESULTS / "ranking_ablations.png", files["ranking_baselines"]["ablations"]["test"])
    figure_sensitivity(results.RESULTS / "ranking_sensitivity.png", files["ranking_sensitivity"])
    for group in ("rows", "rows_if_fitted_weights_adopted"):
        print("targets, hand weights as shipped:" if group == "rows" else "targets, if the fitted weights are adopted:")
        for row in files["ranking_targets"].get(group, []):
            if row.get("labels", "majority") == "majority":
                print(f"  {'MET   ' if row['met'] else 'MISSED'} {row['target']}: {row['value']:.3f}" + (f" [{row['lo']:.3f}, {row['hi']:.3f}]" if "lo" in row else ""))


if __name__ == "__main__":
    main()
