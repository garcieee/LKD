"""How urgent a report is: 1 low .. 3 urgent.

Planned: severity × confirmations × foot-traffic weight. Only severity, from the category, exists so far.
"""
SEVERITY = {
    "sos": 3,  # a person asking for help, ahead of every hazard
    "open_manhole": 3,
    "flooded_drain": 3,
    "pothole": 2,
    "broken_streetlight": 2,
    "blocked_sidewalk": 2,
    "missing_ramp": 2,  # missing or broken ramp or curb cut
    "blocked_tactile_paving": 2,
    "broken_elevator": 2,  # elevator or escalator at a station or overpass
    "unsafe_sidewalk": 2,  # too steep or too broken for a wheelchair
    "other": 1,
}


def severity(category: str) -> int:
    return SEVERITY.get(category, 1)
