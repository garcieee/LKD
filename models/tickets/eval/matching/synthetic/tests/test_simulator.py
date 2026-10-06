import math

import numpy as np
import pytest
from scipy.optimize import brentq

from models.tickets.eval.matching.synthetic import simulator as sim
from models.tickets.matching import geo

ARRAYS = ["hx", "hy", "hlat", "hlng", "hcat", "hazard", "category", "x", "y", "lat", "lng", "accuracy", "sigma", "gps_x",
          "gps_y", "standoff", "t"]


def big(profile="city", seed=1, **kw) -> sim.World:
    """Plenty of reports in a hurry: a very dense patch."""
    return sim.simulate(sim.Config(profile=profile, density=3000, **kw), seed)


def test_the_same_seed_gives_the_same_data_and_another_seed_does_not():
    a, b, c = (sim.simulate(sim.Config(), seed) for seed in (7, 7, 8))
    assert all(np.array_equal(getattr(a, f), getattr(b, f)) for f in ARRAYS)
    assert not np.array_equal(a.hx, c.hx) and not np.array_equal(a.x, c.x)


def test_the_three_profiles_of_a_seed_share_the_hazards_and_the_reporters():
    worlds = {p: sim.simulate(sim.Config(profile=p, density=150), 3) for p in sim.PROFILES}
    first = worlds["open_sky"]
    for w in worlds.values():
        for f in ("hx", "hy", "hcat", "hazard", "category", "standoff", "t"):
            assert np.array_equal(getattr(w, f), getattr(first, f))
    assert not np.array_equal(first.x, worlds["city"].x)
    # the same standard normals scaled by sigma: the city error is exactly twice the open-sky error
    assert np.allclose(worlds["city"].gps_x, 2 * first.gps_x)


@pytest.mark.parametrize("profile", sim.PROFILES)
def test_the_empirical_gps_error_quantiles_match_the_configured_sigmas(profile):
    r = np.concatenate([np.hypot(w.gps_x, w.gps_y) for w in (big(profile, 1), big(profile, 2))])
    assert len(r) > 80_000
    parts = sim.PROFILES[profile]
    cdf = lambda x: sum(share * (1 - math.exp(-x * x / (2 * sigma * sigma))) for sigma, share in parts)  # a mix of Rayleighs
    for q in (0.5, 0.68, 0.95, 0.99):
        expected = brentq(lambda x: cdf(x) - q, 0.01, 500)
        assert np.quantile(r, q) == pytest.approx(expected, rel=0.04), (profile, q)
    if len(parts) == 1:  # one sigma: the 68% radius is the 1.51 sigma that Android calls "accuracy"
        assert np.quantile(r, 0.68) == pytest.approx(sim.ANDROID_FACTOR * parts[0][0], rel=0.03)


def test_the_canyon_mixture_has_the_configured_shares_and_a_heavy_tail():
    w = big("canyon")
    assert set(np.unique(w.sigma)) == {9.0, 25.0}
    assert np.mean(w.sigma == 25.0) == pytest.approx(0.2, abs=0.01)
    # beyond 60 m only the sigma 25 component reaches: 20% * exp(-60^2 / (2 * 25^2)) = 1.1% of the reports, where sigma 9 alone gives none
    assert np.mean(np.hypot(w.gps_x, w.gps_y) > 60) == pytest.approx(0.2 * math.exp(-3600 / 1250), abs=0.002)


def test_the_reported_accuracy_is_right_on_average_but_noisy_and_the_scale_knob_miscalibrates_it():
    w = big("city")
    ratio = np.log(w.accuracy / (sim.ANDROID_FACTOR * w.sigma))
    assert ratio.mean() == pytest.approx(0, abs=0.01) and ratio.std() == pytest.approx(0.35, abs=0.01)
    over = big("city", accuracy_scale=2.0, accuracy_spread=0.0)
    assert np.allclose(over.accuracy, 2 * sim.ANDROID_FACTOR * over.sigma)


def test_the_reporter_stands_one_to_ten_metres_away_in_every_direction():
    w = big("open_sky")
    assert w.standoff.min() >= 1.0 and w.standoff.max() <= 10.0
    assert w.standoff.mean() == pytest.approx(5.5, abs=0.05)
    assert np.sqrt(np.mean(w.standoff**2)) == pytest.approx(math.sqrt(37), abs=0.05)  # about 4.3 m per axis, not the matcher's 3
    away = np.hypot(w.x - w.hx[w.hazard] - w.gps_x, w.y - w.hy[w.hazard] - w.gps_y)  # what is left once the GPS error is removed
    assert np.allclose(away, w.standoff)
    bearing = np.arctan2(w.y - w.hy[w.hazard] - w.gps_y, w.x - w.hx[w.hazard] - w.gps_x)
    assert np.histogram(bearing, bins=8, range=(-math.pi, math.pi))[0].min() > 0.9 * len(bearing) / 8


def test_reports_per_hazard_follow_the_geometric_and_the_heavy_tail_variants():
    w = sim.simulate(sim.Config(density=3000), 1)
    counts = np.bincount(w.hazard)
    assert counts.min() == 1
    assert counts.mean() == pytest.approx(1.6, abs=0.02)
    assert np.mean(counts == 1) == pytest.approx(1 / 1.6, abs=0.01)  # P(no extra reporter) = 1 - keep = 0.625
    assert 1 - np.mean(counts == 1) == pytest.approx(0.375, abs=0.01) and 1 - 1 / counts.mean() == pytest.approx(0.375, abs=0.01)  # the 37% duplicates of Chicago
    heavy = np.bincount(sim.simulate(sim.Config(density=3000, heavy_tail=True), 1).hazard)
    assert heavy.mean() == pytest.approx(3.0, abs=0.2) and heavy.max() >= 30 and counts.max() < 15


def test_six_percent_of_reporters_pick_a_wrong_category_never_other():
    w = big("city")
    wrong = w.category != w.hcat[w.hazard]
    assert wrong.mean() == pytest.approx(0.06, abs=0.004)
    assert w.category.max() < len(sim.REAL_CATEGORIES) and "other" not in sim.REAL_CATEGORIES
    assert len(sim.REAL_CATEGORIES) == 5 and set(w.hcat) == set(range(5))


def test_hazards_hit_the_density_and_bunch_up():
    for density in (20, 60, 150):
        mean = np.mean([sim.simulate(sim.Config(density=density), seed).n_hazards for seed in range(40)])
        assert mean == pytest.approx(density * 9, rel=0.05)
    from scipy.spatial import cKDTree

    def share_with_a_neighbour_within(cfg, metres=25.0):
        pts = np.column_stack([*(lambda w: (w.hx, w.hy))(sim.simulate(cfg, 1))])
        return np.mean(cKDTree(pts).query(pts, k=2)[0][:, 1] < metres)

    clustered, uniform = (share_with_a_neighbour_within(sim.Config(density=60, cluster_share=c)) for c in (0.5, 0.0))
    assert clustered > 2 * uniform  # a Poisson patch at 60 per km2 has about 8% of hazards that close
    assert np.abs(sim.simulate(sim.Config(), 1).hx).max() <= 1500


def test_reports_are_in_arrival_order_and_within_gps_reach_of_their_hazard():
    w = sim.simulate(sim.Config(profile="canyon"), 5)
    assert np.all(np.diff(w.t) >= 0)
    assert w.hazard.min() == 0 and w.hazard.max() == w.n_hazards - 1 and len(np.unique(w.hazard)) == w.n_hazards
    assert np.all(np.hypot(w.x - w.hx[w.hazard], w.y - w.hy[w.hazard]) < 250)


def test_local_metres_and_degrees_agree_with_the_matchers_haversine():
    x, y = np.array([0.0, 120.0, -900.0, 1400.0]), np.array([0.0, -300.0, 1100.0, 1450.0])
    lat, lng = sim.to_latlng(x, y)
    assert (lat[0], lng[0]) == pytest.approx(sim.AYALA)
    assert np.allclose(sim.to_xy(lat, lng), (x, y))
    for a, b in ((0, 1), (1, 2), (2, 3), (0, 3)):
        planar = math.hypot(x[a] - x[b], y[a] - y[b])
        assert geo.distance_m(lat[a], lng[a], lat[b], lng[b]) == pytest.approx(planar, rel=2e-4)
