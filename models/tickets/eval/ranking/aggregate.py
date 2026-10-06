"""Five raters, one survey: how good the raters are, how far they agree, and the labels the priority score is judged by.

    models/.venv/bin/python -m models.tickets.eval.ranking.aggregate        (from the repo root)

reads the frozen survey files, writes data/consensus.json (the labels and the mean urgencies) and
results/ranking_raters.json and .png. What it found: REPORT.md.

Conventions
  choice codes  0 = the ticket listed first (A) wins, 1 = B wins, 2 = tie. Agreement is measured on the codes as the raters saw
                them. All five saw the same A/B order, so recoding a pair as "lower ticket id wins" leaves the observed agreement
                unchanged and only moves chance agreement (kappa_by_ticket_id in the results shows by how much).
  base pairs    the 240 pairs. The 40 swapped repeats only feed the position-bias numbers (swap tables), never a label or a kappa.
  label         the winner that at least 3 of the 5 raters chose. A tie majority, or a split with no majority, has no label.
  consensus     a label that at least 4 of the 5 raters chose; unanimous: all 5.
  ceiling       leave-one-rater-out (LORO): each rater against the majority of the other four, on the pairs where those four have a
                clear majority (a 2-2 split, or a majority that says "tie", is skipped). The mean over the five raters is the most
                a human can be expected to agree with the panel.
"""
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import stats
from sklearn.metrics import cohen_kappa_score

from models.tickets.eval.common import metrics as M
from models.tickets.eval.common import plots, results
from models.tickets.eval.ranking import pairs, validate_ratings

import matplotlib.pyplot as plt  # noqa: E402  (after common.plots, which selects the Agg backend)

DATA = pairs.DATA
A, B, TIE = 0, 1, 2
CODE = {"A": A, "B": B, "tie": TIE}
SPLITS, STRATA = pairs.SPLITS, pairs.STRATA
CONSENSUS_MIN = 4  # raters out of five that must pick the same winner
SEED, BOOT = 0, 1000  # bootstrap seed and resamples (the project standard)


# ---- loading ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Survey:
    """The survey and the five raters' answers as arrays. Pair rows follow blind_survey.json, ticket rows too."""

    raters: tuple
    pair_ids: tuple
    ticket_ids: tuple
    a: np.ndarray  # (pairs,) row of the ticket listed first
    b: np.ndarray  # (pairs,) row of the ticket listed second
    split: np.ndarray  # (pairs,) the split both tickets are in
    stratum: np.ndarray  # (pairs,) clear, close or trade_off
    repeat_of: np.ndarray  # (pairs,) row of the original for a swap repeat, else -1
    choice: np.ndarray  # (pairs, raters): 0 A, 1 B, 2 tie
    confidence: np.ndarray  # (pairs, raters): 1 to 3
    ticket_split: np.ndarray  # (tickets,)
    urgency: np.ndarray  # (tickets, raters): 1 to 5
    truth: tuple  # (tickets,) the answer key's attributes of each ticket
    description: tuple  # (tickets,) the text the raters read

    @property
    def base(self) -> np.ndarray:
        return self.repeat_of < 0


def load(data: Path = DATA) -> Survey:
    """Read blind_survey.json, answer_key.json and the five ratings files, checking each ratings file against the blind survey."""
    blind = json.loads((data / "blind_survey.json").read_text(encoding="utf-8"))
    key = json.loads((data / "answer_key.json").read_text(encoding="utf-8"))
    raters, ratings = tuple(validate_ratings.PERSONAS), {}
    for name in raters:
        path = data / f"ratings_{name}.json"
        ratings[name] = json.loads(path.read_text(encoding="utf-8"))
        problems = validate_ratings.validate(ratings[name], blind, path.name)
        if problems:
            raise ValueError(f"{path.name}: {problems[0]}")
    tickets, rows = [t["id"] for t in blind["tickets"]], blind["pairs"]
    pair_ids = [p["id"] for p in rows]
    at, row = {t: k for k, t in enumerate(tickets)}, {p: k for k, p in enumerate(pair_ids)}
    pt, tt = key["pair_truth"], key["ticket_truth"]

    def column(name, items, field, ids):
        by = {r["id"]: r[field] for r in ratings[name][items]}
        return np.array([by[i] for i in ids])

    return Survey(
        raters=raters, pair_ids=tuple(pair_ids), ticket_ids=tuple(tickets),
        a=np.array([at[p["a"]] for p in rows]), b=np.array([at[p["b"]] for p in rows]),
        split=np.array([pt[p]["split"] for p in pair_ids]), stratum=np.array([pt[p]["stratum"] for p in pair_ids]),
        repeat_of=np.array([row[pt[p]["swap_of"]] if pt[p]["swap_of"] else -1 for p in pair_ids]),
        choice=np.stack([[CODE[c] for c in column(n, "pairs", "choice", pair_ids)] for n in raters], axis=1),
        confidence=np.stack([column(n, "pairs", "confidence", pair_ids) for n in raters], axis=1),
        ticket_split=np.array([tt[t]["split"] for t in tickets]),
        urgency=np.stack([column(n, "urgency", "urgency", tickets) for n in raters], axis=1),
        truth=tuple(tt[t] for t in tickets), description=tuple(t["description"] for t in blind["tickets"]))


# ---- agreement -------------------------------------------------------------------------------------------------------
def vote_counts(choice, categories: int = 3) -> np.ndarray:
    """(pairs, categories): how many raters chose A, B and tie on each pair."""
    choice = np.asarray(choice)
    return np.stack([(choice == c).sum(1) for c in range(categories)], axis=1)


def fleiss_kappa(counts) -> float:
    """Fleiss' kappa from an (items, categories) table of how many raters picked each category; every row sums to the same n.
    NaN when everyone always picks the same category (chance agreement is 1)."""
    counts = np.asarray(counts, float)
    n = counts[0].sum()
    observed = ((counts**2).sum(1) - n) / (n * (n - 1))
    chance = ((counts.sum(0) / counts.sum()) ** 2).sum()
    return float((observed.mean() - chance) / (1 - chance)) if chance < 1 else float("nan")


def loro_reference(choice) -> np.ndarray:
    """(pairs, raters): for each rater the label (0 or 1) of the clear majority of the OTHER raters, -1 where there is none:
    the other raters split evenly at the top, or the choice with the most votes is a tie."""
    choice = np.asarray(choice)
    reference = np.full(choice.shape, -1)
    for r in range(choice.shape[1]):
        votes = vote_counts(np.delete(choice, r, axis=1))
        clear = (votes == votes.max(1, keepdims=True)).sum(1) == 1
        reference[:, r] = np.where(clear & (votes.argmax(1) != TIE), votes.argmax(1), -1)
    return reference


def loro_agreement(choice) -> np.ndarray:
    """(raters,): each rater's share of agreement with the clear majority of the other raters (NaN if no pair has one)."""
    choice = np.asarray(choice)
    reference = loro_reference(choice)
    defined = reference >= 0
    with np.errstate(invalid="ignore", divide="ignore"):
        return ((choice == reference) & defined).sum(0) / defined.sum(0)


def ceiling(choice) -> float:
    """The human ceiling: the mean over raters of their leave-one-rater-out agreement."""
    return float(np.nanmean(loro_agreement(choice)))


def majority_labels(choice) -> dict:
    """Per pair: the votes (A, B, tie), the winner (0 A, 1 B, -1 none) and its support (votes for the winner). The winner
    needs more than half of the raters; otherwise `reason` says why there is none: a tie majority or a split."""
    votes = vote_counts(choice)
    need = votes[0].sum() // 2 + 1
    winner = np.where(votes[:, A] >= need, A, np.where(votes[:, B] >= need, B, -1))
    support = np.where(winner >= 0, votes[np.arange(len(votes)), np.maximum(winner, 0)], 0)
    reason = np.where(winner >= 0, "", np.where(votes[:, TIE] >= need, "tie majority", "no majority"))
    return {"votes": votes, "winner": winner, "support": support, "reason": reason}


@dataclass(frozen=True)
class Labels:
    """The pair labels of the whole survey. Swap repeats and pairs without a majority have winner -1."""

    votes: np.ndarray
    winner: np.ndarray  # (pairs,) 0 A, 1 B, -1 no label
    support: np.ndarray  # (pairs,) raters behind the winner, 0 with no label
    reason: np.ndarray  # (pairs,) "" labelled, "repeat", "tie majority" or "no majority"

    def subset(self, name: str) -> np.ndarray:
        """Boolean mask over pairs: 'majority' (any label), 'consensus' (at least 4 of 5) or 'unanimous' (all 5)."""
        need = {"majority": 1, "consensus": CONSENSUS_MIN, "unanimous": self.votes[0].sum()}[name]
        return (self.winner >= 0) & (self.support >= need)


def label_pairs(survey: Survey) -> Labels:
    """The label of every base pair from the five raters' votes. Repeats are never labelled."""
    m = majority_labels(survey.choice)
    winner = np.where(survey.base, m["winner"], -1)
    return Labels(m["votes"], winner, np.where(winner >= 0, m["support"], 0), np.where(survey.base, m["reason"], "repeat"))


def mean_urgency(survey: Survey) -> np.ndarray:
    """(tickets,): the mean of the five urgency ratings, used as graded relevance."""
    return survey.urgency.mean(1)


# ---- urgency ratings -------------------------------------------------------------------------------------------------
def krippendorff_alpha(ratings, levels: int = 5) -> float:
    """Krippendorff's alpha with the ordinal distance, for an (items, raters) table of whole ratings 1..levels, none missing."""
    r = np.asarray(ratings)
    m = r.shape[1]
    counts = (r[:, :, None] == np.arange(1, levels + 1)[None, None, :]).sum(1)  # (items, levels)
    coincide = (counts.T @ counts - np.diag(counts.sum(0))) / (m - 1)  # pairs of ratings of one item, both orders
    n_c = coincide.sum(1)
    cum = np.concatenate([[0], np.cumsum(n_c)])
    lo, hi = np.minimum.outer(np.arange(levels), np.arange(levels)), np.maximum.outer(np.arange(levels), np.arange(levels))
    delta2 = (cum[hi + 1] - cum[lo] - (n_c[:, None] + n_c[None, :]) / 2) ** 2
    np.fill_diagonal(delta2, 0.0)
    expected = (np.outer(n_c, n_c) * delta2).sum()
    return float(1 - (n_c.sum() - 1) * (coincide * delta2).sum() / expected) if expected else float("nan")


def icc2(ratings) -> tuple[float, float]:
    """Shrout and Fleiss ICC(2,1) and ICC(2,k): two-way random effects, absolute agreement, one rater and the mean of k."""
    x = np.asarray(ratings, float)
    n, k = x.shape
    grand, rows, cols = x.mean(), x.mean(1), x.mean(0)
    msr = k * ((rows - grand) ** 2).sum() / (n - 1)
    msc = n * ((cols - grand) ** 2).sum() / (k - 1)
    mse = ((x - rows[:, None] - cols[None, :] + grand) ** 2).sum() / ((n - 1) * (k - 1))
    return float((msr - mse) / (msr + (k - 1) * mse + k * (msc - mse) / n)), float((msr - mse) / (msr + (msc - mse) / n))


# ---- the raters ------------------------------------------------------------------------------------------------------
def pick_ticket(survey: Survey, rows: np.ndarray, winner: np.ndarray) -> np.ndarray:
    """The ticket row a winner code (0 A, 1 B, anything else a tie) points at in each of `rows`, -1 for a tie.
    `winner` is (rows,) or (rows, raters)."""
    a, b = survey.a[rows], survey.b[rows]
    if winner.ndim == 2:
        a, b = a[:, None], b[:, None]
    return np.where(winner == A, a, np.where(winner == B, b, -1))


def swap_table(survey: Survey) -> dict:
    """The 40 swapped repeats: did a rater (and the panel's majority) pick the same ticket when A and B changed places?
    same_ticket: yes. both_tie: tie both times. one_tie: tie once. position_flip: the other ticket, which means the same letter
    twice. Position bias shows up as flips."""
    repeats = np.flatnonzero(~survey.base)
    originals = survey.repeat_of[repeats]
    first, second = pick_ticket(survey, originals, survey.choice[originals]), pick_ticket(survey, repeats, survey.choice[repeats])
    count = lambda f, s: {"n": len(repeats), "same_ticket": int(((f == s) & (f >= 0)).sum()), "both_tie": int(((f == s) & (f < 0)).sum()),
                          "one_tie": int(((f != s) & ((f < 0) | (s < 0))).sum()), "position_flip": int(((f != s) & (f >= 0) & (s >= 0)).sum())}
    out = {}
    for r, name in enumerate(survey.raters):
        out[name] = count(first[:, r], second[:, r])
        out[name]["consistency"] = (out[name]["same_ticket"] + out[name]["both_tie"]) / len(repeats)
    panel = lambda rows: pick_ticket(survey, rows, majority_labels(survey.choice[rows])["winner"])
    out["panel_majority"] = count(panel(originals), panel(repeats))
    return out


def rater_quality(survey: Survey) -> dict:
    """Per rater: share of A, tie rate, how confidence and urgency were used, swap consistency, how often the pair choice
    follows the rater's own urgency ratings of the two tickets (when those differ), and how often the rater agrees with the
    others at each confidence level."""
    base, swaps = survey.base, swap_table(survey)
    reference = loro_reference(survey.choice[base])
    out = {}
    for r, name in enumerate(survey.raters):
        c, conf = survey.choice[:, r], survey.confidence[:, r]
        decided = base & (c != TIE)
        a_wins = int((c[decided] == A).sum())
        ua, ub = survey.urgency[survey.a, r], survey.urgency[survey.b, r]
        counted = decided & (ua != ub)
        by_conf = {}
        for v in (1, 2, 3):
            rows = (conf[base] == v) & (reference[:, r] >= 0)
            by_conf[str(v)] = {"n": int(rows.sum()), "agree_with_others": float((c[base] == reference[:, r])[rows].mean()) if rows.any() else None}
        out[name] = {
            "share_A_base": float((c[base] == A).mean()), "share_A_all_280": float((c == A).mean()), "share_B_base": float((c[base] == B).mean()),
            "share_A_among_decided": a_wins / int(decided.sum()), "p_value_A_share_is_half": float(stats.binomtest(a_wins, int(decided.sum())).pvalue),
            "tie_rate_base": float((c[base] == TIE).mean()), "ties_base": int((c[base] == TIE).sum()),
            "confidence": {**{str(v): int((conf == v).sum()) for v in (1, 2, 3)}, "mean": float(conf.mean())},
            "urgency": {**{str(v): int((survey.urgency[:, r] == v).sum()) for v in range(1, 6)}, "mean": float(survey.urgency[:, r].mean())},
            "swap": swaps[name], "agree_with_others_by_confidence": by_conf,
            "pair_choice_follows_own_urgency": {"n": int(counted.sum()), "share": float(((c == A) == (ua > ub))[counted].mean())}}
    return out


def raw_agreement(choice) -> np.ndarray:
    """(raters, raters): the share of pairs on which two raters gave the same answer."""
    c = np.asarray(choice)
    return np.array([[float((c[:, i] == c[:, j]).mean()) for j in range(c.shape[1])] for i in range(c.shape[1])])


def agreement_block(survey: Survey, mask: np.ndarray, boot: int = BOOT) -> dict:
    """Kappa, observed and chance agreement, and the LORO ceiling (with intervals) on the pairs of `mask`."""
    choice = survey.choice[mask]
    counts = vote_counts(choice)
    n = counts[0].sum()
    flip = survey.a[mask] > survey.b[mask]  # recode as "lower ticket id wins": A and B swap where the first listed has the higher id
    by_id = np.where(flip[:, None] & (choice < TIE), 1 - choice, choice)
    return {"n_pairs": int(mask.sum()), "fleiss_kappa": M.bootstrap_ci(fleiss_kappa, counts, n=boot, seed=SEED).as_dict(),
            "kappa_by_ticket_id": fleiss_kappa(vote_counts(by_id)),
            "observed_agreement": float((((counts**2).sum(1) - n) / (n * (n - 1))).mean()), "chance_agreement": float(((counts.sum(0) / counts.sum()) ** 2).sum()),
            "loro_per_rater": dict(zip(survey.raters, map(float, loro_agreement(choice)))),
            "ceiling": M.bootstrap_ci(ceiling, choice, n=boot, seed=SEED).as_dict()}


def vote_splits(survey: Survey, mask: np.ndarray) -> dict:
    """How many pairs were decided 5-0, 4-1, 3-2 (the winner's votes first) or had no label."""
    m = majority_labels(survey.choice[mask])
    c = Counter(int(s) if w >= 0 else "none" for s, w in zip(m["support"], m["winner"]))
    return {"5-0": c[5], "4-1": c[4], "3-2": c[3], "none": c["none"]}


def urgency_block(survey: Survey, boot: int = BOOT) -> dict:
    """Agreement on the 1-5 urgency of the 200 tickets: Krippendorff alpha (ordinal), ICC, Spearman between raters."""
    u, names = survey.urgency, survey.raters
    icc1, icck = icc2(u)
    rho = np.array([[M.spearman(u[:, i], u[:, j]) if i != j else 1.0 for j in range(len(names))] for i in range(len(names))])
    off = rho[~np.eye(len(names), dtype=bool)]
    return {"krippendorff_alpha_ordinal": M.bootstrap_ci(krippendorff_alpha, u, n=boot, seed=SEED).as_dict(), "icc2_1": icc1, "icc2_k": icck,
            "spearman_matrix": {"raters": list(names), "matrix": rho.tolist()},
            "spearman_between_raters": {"mean": float(off.mean()), "min": float(off.min()), "max": float(off.max())},
            "spearman_vs_mean_of_other_four": {n: M.spearman(u[:, i], np.delete(u, i, axis=1).mean(1)) for i, n in enumerate(names)},
            "mean_urgency": {"mean": float(mean_urgency(survey).mean()), "sd": float(mean_urgency(survey).std())}}


def labels_block(survey: Survey, labels: Labels) -> dict:
    """How many pairs each label set holds, overall and per split, and why the others were left out."""
    out = {}
    for name, rows in {"all": survey.base, **{s: survey.base & (survey.split == s) for s in SPLITS}}.items():
        out[name] = {"pairs": int(rows.sum()), **{k: int((labels.subset(k) & rows).sum()) for k in ("majority", "consensus", "unanimous")},
                     "excluded": dict(Counter(map(str, labels.reason[rows & (labels.winner < 0)])))}
    return out


# ---- the files -------------------------------------------------------------------------------------------------------
def consensus_doc(survey: Survey, labels: Labels) -> dict:
    """data/consensus.json: per base pair the votes (A, B, tie) and label, per ticket the mean urgency. Small on purpose."""
    meta = {"raters": list(survey.raters), "votes_order": ["A", "B", "tie"], "urgency": "mean of the five 1-5 ratings",
            "rule": "label = the winner at least 3 of 5 raters chose, null for a tie majority or no majority; consensus = 4 or 5 of 5, unanimous = 5 of 5"}
    return {"meta": meta,
            "pairs": {survey.pair_ids[k]: {"split": str(survey.split[k]), "stratum": str(survey.stratum[k]), "votes": labels.votes[k].tolist(),
                                           "label": "AB"[labels.winner[k]] if labels.winner[k] >= 0 else None} for k in np.flatnonzero(survey.base)},
            "tickets": {t: {"split": str(survey.ticket_split[i]), "urgency": round(float(u), 1)} for i, (t, u) in enumerate(zip(survey.ticket_ids, mean_urgency(survey)))}}


def figure(path: Path, payload: dict, survey: Survey) -> None:
    """Three small panels: who agrees with whom, how split the votes were, and how each rater used the 1-5 urgency scale."""
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(13, 3.8))
    raw = np.array(payload["agreement"]["raw_agreement_matrix"]["matrix"])
    image = ax1.imshow(raw, vmin=0.7, vmax=1.0, cmap="Blues")
    ax1.set(xticks=range(5), yticks=range(5), xticklabels=survey.raters, yticklabels=survey.raters, title="Pairs where two raters agree")
    ax1.tick_params(axis="x", labelrotation=30, labelsize=7)
    ax1.tick_params(axis="y", labelsize=7)
    for i in range(5):
        for j in range(5):
            ax1.text(j, i, f"{raw[i, j]:.2f}", ha="center", va="center", fontsize=7, color="white" if raw[i, j] > 0.9 else plots.INK)
    fig.colorbar(image, ax=ax1, fraction=0.046)
    splits, bottom = payload["agreement"]["vote_splits"]["by_stratum"], np.zeros(len(STRATA))
    for kind, color in zip(("5-0", "4-1", "3-2", "none"), ("#212e4a", "#5b7aa6", "#b8c4d6", "#a63722")):
        values = np.array([splits[s][kind] for s in STRATA], float)
        ax2.bar(STRATA, values, bottom=bottom, label=kind, color=color)
        bottom += values
    ax2.set(title="How the five votes split", ylabel="pairs")
    ax2.legend(fontsize=7)
    for r, name in enumerate(survey.raters):
        ax3.bar(np.arange(1, 6) + (r - 2) * 0.16, [payload["raters"][name]["urgency"][str(v)] for v in range(1, 6)], 0.16, label=name)
    ax3.set(title="Urgency ratings of the 200 tickets", xlabel="urgency", ylabel="tickets")
    ax3.legend(fontsize=6)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def run(data: Path = DATA) -> dict:
    """Everything this module reports: the survey, the labels and the payload of results/ranking_raters.json."""
    survey = load(data)
    labels = label_pairs(survey)
    base = survey.base
    every = {"all": base, **{s: base & (survey.split == s) for s in SPLITS}}
    choice = survey.choice[base]
    payload = {
        "config": {"bootstrap": BOOT, "seed": SEED, "consensus_min": CONSENSUS_MIN, "orientation": "first listed wins / second wins / tie"},
        "counts": {"pairs_total": len(survey.pair_ids), "base_pairs": int(base.sum()), "swap_repeats": int((~base).sum()), "tickets": len(survey.ticket_ids), "raters": list(survey.raters)},
        "raters": rater_quality(survey),
        "labels": labels_block(survey, labels),
        "agreement": {
            "overall": agreement_block(survey, base),
            "by_split": {s: agreement_block(survey, every[s]) for s in SPLITS},
            "by_stratum": {k: agreement_block(survey, base & (survey.stratum == k)) for k in STRATA},
            "raw_agreement_matrix": {"raters": list(survey.raters), "matrix": raw_agreement(choice).tolist()},
            "cohen_kappa_matrix": {"raters": list(survey.raters),
                                   "matrix": [[float(cohen_kappa_score(choice[:, i], choice[:, j])) for j in range(choice.shape[1])] for i in range(choice.shape[1])]},
            "vote_splits": {"overall": vote_splits(survey, base), "by_split": {s: vote_splits(survey, every[s]) for s in SPLITS},
                            "by_stratum": {k: vote_splits(survey, base & (survey.stratum == k)) for k in STRATA}},
            "swap_repeats": swap_table(survey)},
        "urgency": urgency_block(survey),
    }
    return {"survey": survey, "labels": labels, "payload": payload}


def main() -> None:
    done = run()
    survey, labels, payload = done["survey"], done["labels"], done["payload"]
    (DATA / "consensus.json").write_text(pairs.dumps(consensus_doc(survey, labels)), encoding="utf-8")
    path = results.write_result("ranking_raters", payload)
    figure(path.with_suffix(".png"), payload, survey)
    a = payload["agreement"]["overall"]
    print(f"wrote {path} and {DATA / 'consensus.json'}")
    print(f"Fleiss kappa {a['fleiss_kappa']['point']:.3f} [{a['fleiss_kappa']['lo']:.3f}, {a['fleiss_kappa']['hi']:.3f}]  ceiling {a['ceiling']['point']:.3f}  labels {payload['labels']['all']}")


if __name__ == "__main__":
    main()
