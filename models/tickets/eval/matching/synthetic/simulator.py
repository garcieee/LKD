"""Simulated Makati: hazards, the people who report them and their phones' GPS error, with exact ground truth.

Everything is drawn in local metres (x east, y north, origin at Ayala) and converted to lat/lng only for the
matcher. A world is deterministic from (Config, seed). The three GPS profiles of one seed share the same hazards,
reporters and random numbers (common random numbers), so a difference between profiles is GPS error alone, and so
is a difference between two stand-off or miscalibration settings.

What the simulator believes, deliberately NOT what the matcher believes (matching/geo.py assumes a Gaussian
stand-off of 3 m per axis and a phone that reports accuracy / 1.51 as its per-axis sigma):
  * a reporter stands 1 to 10 m from the hazard, uniform distance, random bearing (about 4.3 m per axis);
  * the phone reports 1.51 * true sigma * lognormal(0, 0.35), so its accuracy is right on average but noisy.
"""
import math
from dataclasses import dataclass

import numpy as np

from models.tickets.matching.geo import EARTH_RADIUS_M
from models.tickets.types import HAZARDS as CATEGORIES  # built on these six: no data yet for the PWD barriers

AYALA = (14.5547, 121.0244)
REAL_CATEGORIES = tuple(c for c in CATEGORIES if c != "other")  # the five a reporter can really see
ANDROID_FACTOR = 1.51  # Android's accuracy is a 68% radius: for a 2D Gaussian that is 1.51 sigma
EPOCH = 1_800_000_000.0  # arrival times are seconds after this
DAY = 86_400.0

# per-axis GPS sigma in metres as (sigma, share of the reports) components
PROFILES = {"open_sky": ((3.3, 1.0),), "city": ((6.6, 1.0),), "canyon": ((9.0, 0.8), (25.0, 0.2))}


@dataclass(frozen=True)
class Config:
    profile: str = "city"
    density: float = 60.0  # hazards per km2
    patch_m: float = 3000.0  # a square patch around Ayala
    # hazards: a Thomas cluster process (cluster_share of the hazards) plus a uniform background
    cluster_share: float = 0.5
    cluster_mean: float = 3.0  # hazards per parent
    cluster_sd_m: float = 25.0  # per-axis spread of the hazards around their parent
    # real categories in the order of REAL_CATEGORIES: pothole, open_manhole, flooded_drain, broken_streetlight, blocked_sidewalk
    category_weights: tuple = (0.35, 0.10, 0.15, 0.25, 0.15)
    # reporters: 1 + a geometric count (mean_reports overall), or a Zipf tail of popular hazards
    heavy_tail: bool = False
    mean_reports: float = 1.6
    heavy_alpha: float = 1.95  # P(k reports) ~ k**-alpha up to heavy_max: mean about 3
    heavy_max: int = 50
    wrong_category: float = 0.06
    standoff_m: tuple = (1.0, 10.0)  # uniform distance of the reporter from the hazard
    accuracy_scale: float = 1.0  # miscalibration: reported = scale * 1.51 * sigma * lognormal; 1 is right on average
    accuracy_spread: float = 0.35  # sigma of that lognormal
    days: float = 30.0  # hazards appear uniformly over this many days
    mean_delay_days: float = 2.0  # a reporter notices this long after the hazard appears, on average


@dataclass
class World:
    config: Config
    seed: int
    # hazards (the truth)
    hx: np.ndarray
    hy: np.ndarray
    hlat: np.ndarray
    hlng: np.ndarray
    hcat: np.ndarray  # index into REAL_CATEGORIES
    # reports in arrival order (index = arrival rank)
    hazard: np.ndarray  # which hazard the report is about: the ground-truth cluster
    category: np.ndarray  # index into REAL_CATEGORIES that the reporter picked (6% wrong)
    x: np.ndarray
    y: np.ndarray
    lat: np.ndarray
    lng: np.ndarray
    accuracy: np.ndarray  # what the phone reports: the only accuracy the matcher ever sees
    sigma: np.ndarray  # the true per-axis GPS sigma (hidden from the matcher)
    gps_x: np.ndarray  # the GPS error actually drawn (hidden)
    gps_y: np.ndarray
    standoff: np.ndarray  # how far the reporter stood from the hazard (hidden)
    t: np.ndarray  # arrival time, seconds

    @property
    def n_hazards(self) -> int:
        return len(self.hx)

    @property
    def n_reports(self) -> int:
        return len(self.hazard)


def to_latlng(x, y, origin=AYALA):
    """Local metres east and north of the origin to degrees. The matcher's haversine agrees to better than 1e-4."""
    lat0, lng0 = origin
    lat = lat0 + np.degrees(np.asarray(y, float) / EARTH_RADIUS_M)
    lng = lng0 + np.degrees(np.asarray(x, float) / (EARTH_RADIUS_M * math.cos(math.radians(lat0))))
    return lat, lng


def to_xy(lat, lng, origin=AYALA):
    """The inverse of to_latlng."""
    lat0, lng0 = origin
    y = np.radians(np.asarray(lat, float) - lat0) * EARTH_RADIUS_M
    x = np.radians(np.asarray(lng, float) - lng0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    return x, y


def _hazard_points(rng: np.random.Generator, cfg: Config) -> np.ndarray:
    """(n, 2) metres. Parents live on a patch widened by 4 spreads, so the density holds right up to the edge."""
    half, km2, share = cfg.patch_m / 2, (cfg.patch_m / 1000) ** 2, cfg.cluster_share
    background = rng.uniform(-half, half, (rng.poisson((1 - share) * cfg.density * km2), 2))
    if share <= 0:
        return background
    margin = 4 * cfg.cluster_sd_m
    wide_km2 = ((cfg.patch_m + 2 * margin) / 1000) ** 2
    parents = rng.uniform(-half - margin, half + margin, (rng.poisson(share * cfg.density * wide_km2 / cfg.cluster_mean), 2))
    kids = rng.poisson(cfg.cluster_mean, len(parents))
    points = np.repeat(parents, kids, axis=0) + rng.normal(0, cfg.cluster_sd_m, (int(kids.sum()), 2))
    return np.vstack([background, points[(np.abs(points) <= half).all(axis=1)]])


def _report_counts(cfg: Config, u: np.ndarray) -> np.ndarray:
    """Reports per hazard, at least 1, by inverting the cdf at the uniforms u (so every profile gets the same counts)."""
    if cfg.heavy_tail:
        weights = np.arange(1, cfg.heavy_max + 1, dtype=float) ** -cfg.heavy_alpha
        return 1 + np.minimum(np.searchsorted(np.cumsum(weights) / weights.sum(), u), cfg.heavy_max - 1)
    keep = (cfg.mean_reports - 1) / cfg.mean_reports  # P(at least g extra reporters) = keep ** g
    return 1 + np.floor(np.log1p(-u) / math.log(keep)).astype(int)


def _sigma(profile: str, u: np.ndarray) -> np.ndarray:
    components = PROFILES[profile]
    edges = np.cumsum([share for _, share in components])
    pick = np.minimum(np.searchsorted(edges, u, side="right"), len(components) - 1)
    return np.array([sigma for sigma, _ in components])[pick]


def simulate(cfg: Config, seed: int) -> World:
    layout, people, phones = (np.random.default_rng(c) for c in np.random.SeedSequence(seed).spawn(3))
    xy = _hazard_points(layout, cfg)
    n = len(xy)
    weights = np.asarray(cfg.category_weights, float)
    hcat = layout.choice(len(REAL_CATEGORIES), size=n, p=weights / weights.sum())

    counts = _report_counts(cfg, people.random(n))
    birth = people.random(n) * cfg.days * DAY
    h = np.repeat(np.arange(n), counts)
    N = len(h)
    u_wrong, u_pick, u_dist, u_bearing, u_delay = (people.random(N) for _ in range(5))
    category = np.where(u_wrong < cfg.wrong_category, (hcat[h] + 1 + (u_pick * 4).astype(int)) % len(REAL_CATEGORIES), hcat[h])
    lo, hi = cfg.standoff_m
    standoff = lo + (hi - lo) * u_dist
    bearing = 2 * math.pi * u_bearing
    t = EPOCH + birth[h] - cfg.mean_delay_days * DAY * np.log1p(-u_delay)

    zx, zy, u_mix, z_acc = phones.standard_normal(N), phones.standard_normal(N), phones.random(N), phones.standard_normal(N)
    sigma = _sigma(cfg.profile, u_mix)
    accuracy = cfg.accuracy_scale * ANDROID_FACTOR * sigma * np.exp(cfg.accuracy_spread * z_acc)
    gps_x, gps_y = sigma * zx, sigma * zy
    x = xy[h, 0] + standoff * np.cos(bearing) + gps_x
    y = xy[h, 1] + standoff * np.sin(bearing) + gps_y

    order = np.argsort(t, kind="stable")  # arrival order is the report index from here on
    lat, lng = to_latlng(x[order], y[order])
    hlat, hlng = to_latlng(xy[:, 0], xy[:, 1])
    return World(cfg, seed, xy[:, 0], xy[:, 1], hlat, hlng, hcat, h[order], category[order], x[order], y[order], lat, lng,
                 accuracy[order], sigma[order], gps_x[order], gps_y[order], standoff[order], t[order])
