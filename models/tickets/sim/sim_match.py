"""Same-place matching: how big must the merge radius be, given phone GPS error?

Model: a reporter stands ~3 m (Rayleigh) from the hazard and the phone's GPS adds error.
Android's `accuracy` is the 68% radius, so per-axis sigma = accuracy / 1.51 (2D Gaussian).
"""
import math
import random

random.seed(7)
N = 100_000
SIGMA_VIEW = 3.0  # per-axis metres: where people stand relative to the hazard


def g2(s):
    return random.gauss(0, s), random.gauss(0, s)


def reading(true, acc):
    ex, ey = g2(acc / 1.51)
    vx, vy = g2(SIGMA_VIEW)
    return true[0] + ex + vx, true[1] + ey + vy


def d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def aware_radius(acc1, acc2, p):
    # difference of two readings is Gaussian per axis with variance s2; distance is Rayleigh
    s2 = (acc1 / 1.51) ** 2 + (acc2 / 1.51) ** 2 + 2 * SIGMA_VIEW**2
    z = math.sqrt(2 * math.log(1 / (1 - p)))
    return min(60.0, max(12.0, z * math.sqrt(s2)))


def rates(acc, radius):
    split = sum(d(reading((0, 0), acc), reading((0, 0), acc)) > radius for _ in range(N)) / N
    merge = {}
    for D in (20, 40, 80):
        merge[D] = sum(d(reading((0, 0), acc), reading((D, 0), acc)) <= radius for _ in range(N)) / N
    return split, merge


print("reported GPS accuracy -> chance ONE hazard is split into two tickets (S) / TWO hazards D metres apart are merged (M@D)")
print(f"{'acc':>5} {'rule':>14} {'radius':>7} {'split':>7} {'M@20':>7} {'M@40':>7} {'M@80':>7}")
for acc in (5, 10, 20):
    rules = [(f"fixed {r} m", r) for r in (15, 25, 40, 60)]
    rules += [(f"aware {int(p*100)}%", aware_radius(acc, acc, p)) for p in (0.90, 0.95, 0.99)]
    for name, r in rules:
        s, m = rates(acc, r)
        print(f"{acc:>4}m {name:>14} {r:7.1f} {s:7.1%} {m[20]:7.1%} {m[40]:7.1%} {m[80]:7.1%}")
    print()

# Five people report the same hazard; each new report is matched against the FIRST one (the anchor).
print("5 reporters, same hazard, matched against the first report's spot: chance at least one is split off")
for acc in (5, 10, 20):
    out = []
    for p in (0.95, 0.99):
        r = aware_radius(acc, acc, p)
        bad = 0
        for _ in range(N // 2):
            a = reading((0, 0), acc)
            bad += any(d(a, reading((0, 0), acc)) > r for _ in range(4))
        out.append(f"aware {int(p*100)}% (r={r:.0f} m): {bad/(N//2):.1%}")
    print(f"  acc {acc:>2} m  " + "   ".join(out))
