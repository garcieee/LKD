"""How urgent a report is: 1 low .. 3 urgent.

Planned: severity × confirmations × foot-traffic weight. Only severity, from the category, exists so far.
"""
SEVERITY = {
    "open_manhole": 3,
    "flooded_drain": 3,
    "pothole": 2,
    "broken_streetlight": 2,
    "blocked_sidewalk": 2,
    "other": 1,
}


def severity(category: str) -> int:
    return SEVERITY.get(category, 1)
