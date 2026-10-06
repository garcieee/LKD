"""Belief and the states a ticket drifts into without staff touching it: likely gone, stale.

Belief is how sure we are the hazard is still there. It starts from a Beta prior (a fresh single report is 80%
sure) and moves with each person: reporters and "still there" taps count as yes, "gone" taps as no. One "gone"
never closes anything (Waze works the same way), it only cools the ticket down and flags it for a look.
"""
from .. import settings as s


def belief(yes: int, no: int) -> float:
    """Probability the hazard is still there, from the people who said yes and no."""
    a, b = s.BELIEF_PRIOR
    yes, no = max(yes, 0), max(no, 0)
    return (a + yes) / (a + b + yes + no)


def gate(b: float) -> float:
    """The multiplier belief puts on the priority score: 1 at the belief of a fresh report, down to GATE_MIN."""
    return min(1.0, max(s.GATE_MIN, (b - s.GATE_LOW) / s.GATE_SPAN))


def likely_gone(b: float) -> bool:
    return b < s.LIKELY_GONE_BELOW


def is_stale(category: str, days_since_activity: float) -> bool:
    """A low-danger ticket nobody has reported or voted on for STALE_DAYS: worth asking staff to verify."""
    low_danger = s.SEVERITY.get(category, s.SEVERITY["other"]) < s.STALE_BELOW_DANGER
    return low_danger and days_since_activity >= s.STALE_DAYS
