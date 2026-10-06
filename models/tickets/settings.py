"""Every tunable number for ticketing, in one file. Change a value here, run the tests, done.

The values come from the experiments in models/tickets/sim/ and are starting points: the weights are
judgment calls, to be tuned against the team's pairwise ranking survey (see README.md).
"""

# ---- matching: is this the same place? ---------------------------------------------------------
# A report joins an open ticket of the SAME category when the two spots are closer than
#   MATCH_Z * sqrt(sigma_a**2 + sigma_b**2 + 2 * STAND_OFF_SIGMA_M**2), kept within MATCH_MIN_M..MATCH_MAX_M,
# where sigma = phone-reported accuracy / ACCURACY_TO_SIGMA. sim/sim_match.py: with 5 people at one
# pothole, a 95% radius splits one of them off 16% of the time, a 99% radius only 3.5%.
ACCURACY_TO_SIGMA = 1.51  # Android reports accuracy as a 68% radius: sigma = accuracy / 1.51
STAND_OFF_SIGMA_M = 3.0  # people stand a few metres from the hazard (assumption: field-test it)
MATCH_Z = 3.03  # the 99% radius
MATCH_MIN_M = 15.0
MATCH_MAX_M = 60.0
DEFAULT_ACCURACY_M = 15.0  # when the phone sends no accuracy
SUGGEST_RADIUS_M = 80.0  # the "already reported nearby?" list shown on the phone before sending
REOPEN_WINDOW_DAYS = 30  # a report this soon after a ticket was fixed reopens it

# ---- ranking: what do we fix first? ------------------------------------------------------------
# score = 100 * gate * (danger*w + reports*w + foot_traffic*w + waiting*w); then the floors and the
# bonus below. sim/sim_rank.py checks 9 ranking cases and 20,000 random tickets against this.
SEVERITY = {  # "danger": how bad this kind of hazard is, 0..1
    "open_manhole": 1.0,
    "flooded_drain": 0.85,
    "pothole": 0.65,
    "broken_streetlight": 0.55,
    "blocked_sidewalk": 0.5,
    "other": 0.25,
}
WEIGHTS = {"danger": 0.50, "reports": 0.20, "foot_traffic": 0.18, "waiting": 0.12}  # sums to 1
FLOORS = {"open_manhole": 62.0, "flooded_drain": 48.0}  # safety-critical: never lower while believed real
DANGER_BONUS = 10.0  # points added for a danger flag, or when URGENT_MIN_PEOPLE people tap "urgent"
BANDS = (("Critical", 70.0), ("High", 55.0), ("Medium", 40.0), ("Low", 0.0))  # score at or above

REPORTS_FULL_AT = 8  # unique people at which the "reports" part reaches 1 (log scale)
WAITING_FULL_DAYS = 14  # days open at which the "waiting" part reaches 1
BELIEF_PRIOR = (3, 1)  # Beta(yes, no): a fresh single report is 80% sure it is still there
GATE_LOW = 0.30  # at or below this belief the score is cut to GATE_MIN
GATE_SPAN = 0.50  # the gate reaches 1 at GATE_LOW + GATE_SPAN
GATE_MIN = 0.25
LIKELY_GONE_BELOW = 0.45  # belief under this flags "likely gone: verify"
STALE_DAYS = 21  # a low-danger ticket with no sighting or vote for this long: "verify?"
STALE_BELOW_DANGER = 0.6  # "low-danger" means a SEVERITY value under this (blocked sidewalk, other)

# ---- foot traffic: who walks past? -------------------------------------------------------------
EXPOSURE_WEIGHTS = {  # per kind of nearby place (OpenStreetMap, see resources/)
    "school": 1.0,  # schools, kindergartens, colleges, universities
    "health": 1.0,  # hospitals, clinics
    "doctor": 0.5,
    "rail": 0.9,  # MRT / LRT / train stops
    "market": 0.8,
    "mall": 0.7,  # malls, supermarkets
    "bus": 0.4,
}
EXPOSURE_REACH_M = 300.0  # ignore places farther than this
EXPOSURE_FADE_M = 100.0  # a place's pull fades like exp(-distance / this)
EXPOSURE_SCALE = 1.0  # foot_traffic = 1 - exp(-sum / scale); calibrated on 719 places: median 0.41, p90 0.83
EXPOSURE_FLOOR = 0.1  # nowhere is zero
EXPOSURE_DEFAULT = 0.5  # used when the places file is missing

# ---- classification ----------------------------------------------------------------------------
URGENT_MIN_PEOPLE = 2  # one "urgent" tap is noise, two independent ones count
QUALITY_MAX_ACCURACY_M = 50.0  # a worse GPS fix marks the report "needs review" (never rejected)
