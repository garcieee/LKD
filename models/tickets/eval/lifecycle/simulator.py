"""A vote simulator with exact ground truth, to evaluate belief (ranking/lifecycle.py).

Every ticket is one hazard. It is reported once while it exists (the first report, always a yes), then passers-by
tap "still there" or "gone" over the following days, in time order. Because we generate the hazard, we know
exactly whether it was there at the moment of each tap. Deterministic from a seed: same seed, same data.

Time is in days after the first report. `end` is when the hazard stops existing; it is gone from that moment on.
  - gone_before_votes of hazards end at 0: gone before anyone else votes (the case belief must catch).
  - of the rest, staff_share are fixed by staff at a random time (uniform in staff_days), the others fade by
    themselves after an exponential time whose mean is one of lifetime_means, picked uniformly.

Votes: no_votes of tickets get no vote at all; the others get 1 + a geometric number (so most get few), with
exponential delays after the first report, in time order. A passer-by taps at random with probability `noise`
(a bad actor or a mis-tap); otherwise says "still there" with probability sensitivity when the hazard is there,
and "gone" with probability specificity when it is gone. `gone_tap_rate` < 1 models people who walk past a
fixed hazard and do not bother to say so: a "gone" tap is only cast with that probability.

Random draws have a fixed size and order, so changing a rate or an accuracy moves the thresholds applied to the
same random numbers: sweeps compare the same hazards and the same vote times (common random numbers).
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SimConfig:
    tickets: int = 10_000
    max_votes: int = 16  # extra votes beyond the first report, cut off here (a geometric tail past 16 is under 0.4%)
    # hazards
    gone_before_votes: float = 0.30
    lifetime_means: tuple[float, ...] = (5.0, 15.0, 60.0)  # days
    staff_share: float = 0.25
    staff_days: tuple[float, float] = (2.0, 45.0)
    # votes
    no_votes: float = 0.35
    votes_geometric_p: float = 0.30  # votes for a ticket that gets any = geometric, mean 1 / p = 3.3
    vote_delay_days: float = 10.0  # each vote comes this long (mean, exponential) after the first report
    # voters
    sensitivity: float = 0.85  # P(tap "still there" | it is there), before noise
    specificity: float = 0.90  # P(tap "gone" | it is gone), before noise
    noise: float = 0.10  # share of voters who tap at random
    gone_tap_rate: float = 1.0


@dataclass(frozen=True)
class Sim:
    """One row per ticket, one column per extra vote (time order). Unused cells have time = inf."""

    end: np.ndarray  # (n,) days after the first report when the hazard stops existing
    time: np.ndarray  # (n, K) days after the first report of each vote
    yes: np.ndarray  # (n, K) bool: the tap was "still there"
    there: np.ndarray  # (n, K) bool: the hazard truly existed at that moment

    @property
    def valid(self) -> np.ndarray:
        return np.isfinite(self.time)


def still_there(time, end) -> np.ndarray:
    """Ground truth at each vote: the hazard is there until `end`, and gone from that moment on."""
    return np.asarray(time) < np.asarray(end)[:, None]


def from_timelines(timelines: list[tuple[float, list[tuple[float, bool]]]]) -> Sim:
    """Build a Sim by hand: each timeline is (hazard end, [(vote time, tapped "still there"), ...]) in time order."""
    width = max(1, max(len(votes) for _, votes in timelines))
    time = np.full((len(timelines), width), np.inf)
    yes = np.zeros((len(timelines), width), bool)
    for i, (_, votes) in enumerate(timelines):
        for j, (t, tapped_yes) in enumerate(votes):
            time[i, j], yes[i, j] = t, tapped_yes
    end = np.array([e for e, _ in timelines], float)
    return Sim(end, time, yes, still_there(time, end))


def simulate(cfg: SimConfig = SimConfig(), seed: int = 0) -> Sim:
    rng = np.random.default_rng(seed)
    n, width = cfg.tickets, cfg.max_votes
    means = np.asarray(cfg.lifetime_means, float)

    # when does each hazard stop existing?
    early = rng.random(n) < cfg.gone_before_votes
    fades_after = rng.exponential(1.0, n) * means[(rng.random(n) * len(means)).astype(int)]
    fixed_by_staff = rng.random(n) < cfg.staff_share
    staff_at = rng.uniform(cfg.staff_days[0], cfg.staff_days[1], n)
    end = np.where(early, 0.0, np.where(fixed_by_staff, staff_at, fades_after))

    # how many extra votes, and when (sorted, unused cells at the end)
    nobody = rng.random(n) < cfg.no_votes
    votes = np.where(nobody, 0, np.minimum(rng.geometric(cfg.votes_geometric_p, n), width))
    delay = rng.exponential(cfg.vote_delay_days, (n, width))
    time = np.sort(np.where(np.arange(width) < votes[:, None], delay, np.inf), axis=1)
    there = still_there(time, end)

    # what each passer-by taps
    u_noise, u_coin, u_accuracy, u_bother = (rng.random((n, width)) for _ in range(4))
    honest_yes = np.where(there, u_accuracy < cfg.sensitivity, u_accuracy >= cfg.specificity)
    yes = np.where(u_noise < cfg.noise, u_coin < 0.5, honest_yes)

    # people who see nothing do not always say so: drop some "gone" taps, keep time order
    time = np.where(np.isfinite(time) & (yes | (u_bother < cfg.gone_tap_rate)), time, np.inf)
    order = np.argsort(time, axis=1, kind="stable")
    time, yes, there = (np.take_along_axis(a, order, 1) for a in (time, yes, there))
    return Sim(end, time, yes, there)


def concat(sims: list[Sim]) -> Sim:
    """Stack several seeds (same width) into one Sim."""
    return Sim(*(np.concatenate([getattr(s, f) for s in sims]) for f in ("end", "time", "yes", "there")))
