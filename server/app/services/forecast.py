"""Past and future foot traffic for a zone, hour by hour: a simulated history and a seasonal forecast of it.

There is no real foot-traffic history yet, so the "past" is SIMULATED: the model's index for that weekday and
hour (services/footfall.py), times a seeded day factor (rain, payday) and a little hourly jitter. Same inputs,
same series, every run. It stands in for a measured series until cameras exist; the forecaster does not care
which it gets.

The forecast is a seasonal model, the part that carries over to measured data:
    seasonal[hour of week] = mean of the last four weeks at that hour of the week
    level                  = recent actual / seasonal (EWMA), pulled back to 1 with a one-day half-life
    forecast               = seasonal * level, with an 80% band from the spread of actual / seasonal
Its backtest (train on three weeks, forecast the fourth) scores it against the simulated history only.
"""
import hashlib
import math
from datetime import date, datetime, timedelta

from app.services.footfall import MANILA, curve

METHOD = "seasonal_level_v1"
HISTORY_DAYS = 28
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
Z80 = 1.2816  # one-sided z for an 80% band
RAIN_CHANCE, RAIN_FACTOR = 0.18, 0.78
PAYDAY_FACTOR = 1.08


def _unit(*parts: object) -> float:
    """A repeatable pseudo-random number in [0, 1) from the parts."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def day_factor(zone: str, d: date) -> float:
    """What the day did to the zone: rain keeps people in, paydays (15th, month end) bring them out."""
    f = 1 + (_unit(zone, d, "day") - 0.5) * 0.12  # +-6%
    if _unit(zone, d, "rain") < RAIN_CHANCE:
        f *= RAIN_FACTOR
    nxt = d + timedelta(days=1)
    if d.day == 15 or nxt.day == 1:
        f *= PAYDAY_FACTOR
    return f


def zone_name(model: dict, zone: str) -> str | None:
    if zone == "all":
        return "All of Makati"
    return next((d["name"] for d in model["districts"] if d["id"] == zone), None)


def modeled(model: dict, zone: str, t: datetime) -> float:
    """The model's index for the zone at t, before any day-to-day variation (0-100)."""
    day = DAYS[t.weekday()]
    parts = [d for d in model["districts"] if zone in ("all", d["id"])]
    # A district is 100 * its share of the strongest district * its hourly curve; "all" averages them, weighted by share.
    index = {d["id"]: 100 * d["share"] * curve(model["profiles"][d["profile"]], day, t.hour) for d in parts}
    return sum(d["share"] * index[d["id"]] for d in parts) / sum(d["share"] for d in parts)


def simulate(model: dict, zone: str, end: datetime, days: int = HISTORY_DAYS) -> list[tuple[datetime, float]]:
    """Hourly simulated history ending at `end` (inclusive), oldest first."""
    out = []
    for i in range(days * 24):
        t = end - timedelta(hours=days * 24 - 1 - i)
        v = modeled(model, zone, t) * day_factor(zone, t.date()) * (1 + (_unit(zone, t, "h") - 0.5) * 0.10)
        out.append((t, round(min(100.0, max(0.0, v)), 1)))
    return out


def _how(t: datetime) -> int:
    return t.weekday() * 24 + t.hour  # hour of week, 0-167


def forecast(history: list[tuple[datetime, float]], hours: int) -> list[dict]:
    """The next `hours` after the last history point: index with an 80% band."""
    by_how: dict[int, list[float]] = {}
    for t, v in history[-28 * 24 :]:
        by_how.setdefault(_how(t), []).append(v)
    seasonal = {k: sum(v) / len(v) for k, v in by_how.items()}

    ratios = [(v / seasonal[_how(t)]) for t, v in history[-28 * 24 :] if seasonal[_how(t)] > 1.0]
    mean = sum(ratios) / len(ratios) if ratios else 1.0
    sigma = math.sqrt(sum((r - mean) ** 2 for r in ratios) / len(ratios)) if ratios else 0.2

    level = 1.0
    for t, v in history[-72:]:
        s = seasonal[_how(t)]
        if s > 1.0:
            level += 0.15 * (min(1.6, max(0.5, v / s)) - level)

    last = history[-1][0]
    out = []
    for h in range(1, hours + 1):
        t = last + timedelta(hours=h)
        s = seasonal.get(_how(t), 0.0)
        lvl = 1 + (level - 1) * 0.5 ** (h / 24)
        f = min(100.0, max(0.0, s * lvl))
        half = Z80 * sigma * s * math.sqrt(1 + 0.15 * h / 24)
        out.append({"t": t, "index": round(f, 1), "lower": round(max(0.0, f - half), 1), "upper": round(min(100.0, f + half), 1)})
    return out


def backtest_smape(model: dict, zone: str, end: datetime) -> float:
    """sMAPE (%) of forecasting the last week of simulated history from the three weeks before it."""
    hist = simulate(model, zone, end)
    train, actual = hist[: -7 * 24], hist[-7 * 24 :]
    fc = forecast(train, 7 * 24)
    errs = [200 * abs(f["index"] - a[1]) / (f["index"] + a[1]) for f, a in zip(fc, actual) if f["index"] + a[1] > 2]
    return round(sum(errs) / len(errs), 1) if errs else 0.0


def series(model: dict, zone: str, now: datetime, past_days: int, future_days: int) -> dict:
    """The zone's hourly history and forecast around `now` (floored to the hour, Manila time)."""
    now = now.astimezone(MANILA).replace(minute=0, second=0, microsecond=0)
    hist = simulate(model, zone, now)
    fc = forecast(hist, future_days * 24)
    points = [{"t": t.isoformat(), "index": v, "kind": "history"} for t, v in hist[-past_days * 24 :]]
    points += [{**p, "t": p["t"].isoformat(), "kind": "forecast"} for p in fc]
    return {
        "zone": zone,
        "name": zone_name(model, zone),
        "method": METHOD,
        "history_source": "simulated",
        "now": now.isoformat(),
        "backtest_smape_pct": backtest_smape(model, zone, now),
        "points": points,
    }
