"""The 0-100 priority score, its band and the breakdown behind it, so staff can see why a ticket is where it is.

  score = 100 * gate * (w_danger * danger + w_reports * reports + w_foot * foot_traffic + w_wait * waiting)
  then: a safety floor for critical categories (also scaled by the gate), plus the danger bonus, capped at 100.

danger   how bad the kind of hazard is (SEVERITY)           reports  unique people, log scale (8 people = 1)
foot     nearby schools, stations, markets ... (exposure)    waiting  days open / WAITING_FULL_DAYS
gate     belief the hazard is still there (lifecycle.py): 1 for a fresh report, lower when people say it is gone
"""
import math

from .. import settings as s
from ..types import Breakdown, TicketFacts
from . import lifecycle


def band(score: float) -> str:
    for name, threshold in s.BANDS:
        if score >= threshold:
            return name
    return s.BANDS[-1][0]


def score(facts: TicketFacts) -> Breakdown:
    people = max(facts.reporters, 1)
    parts = {
        "danger": s.SEVERITY.get(facts.category, s.SEVERITY["other"]),
        "reports": min(1.0, math.log2(people) / math.log2(s.REPORTS_FULL_AT)),
        "foot_traffic": min(1.0, max(0.0, facts.foot_traffic)),
        "waiting": min(1.0, max(0.0, facts.days_open) / s.WAITING_FULL_DAYS),
    }
    belief = lifecycle.belief(people, facts.gone_votes)  # every reporter counts as a yes
    gate = lifecycle.gate(belief)
    value = 100 * gate * sum(s.WEIGHTS[name] * part for name, part in parts.items())
    floor = gate * s.FLOORS.get(facts.category, 0.0)
    bonus = s.DANGER_BONUS if facts.danger else 0.0
    total = min(100.0, max(value, floor) + bonus)
    return Breakdown(total, band(total), parts, belief, gate, floor > value, bonus)
