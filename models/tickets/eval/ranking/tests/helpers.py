"""Hand-made surveys for the ranking tests."""
import numpy as np

from models.tickets.eval.ranking import aggregate as ag


def tiny_survey(choice, a, b, repeat_of, urgency=None, truth=None, split=None, stratum=None):
    """A hand-made Survey: only the fields the code under test reads are meaningful. `choice` is (pairs, raters) of 0 A, 1 B, 2 tie;
    a and b are the ticket rows of each pair; repeat_of is -1 for a base pair or the row of its original."""
    choice = np.asarray(choice)
    n_pairs, n_raters = choice.shape
    n_tickets = max(max(a), max(b)) + 1
    return ag.Survey(
        raters=tuple(f"r{i}" for i in range(n_raters)), pair_ids=tuple(f"p{i}" for i in range(n_pairs)), ticket_ids=tuple(f"t{i}" for i in range(n_tickets)),
        a=np.array(a), b=np.array(b), split=np.array(split or ["test"] * n_pairs), stratum=np.array(stratum or ["clear"] * n_pairs), repeat_of=np.array(repeat_of),
        choice=choice, confidence=np.full(choice.shape, 2), ticket_split=np.array(["test"] * n_tickets),
        urgency=np.full((n_tickets, n_raters), 3) if urgency is None else np.asarray(urgency), truth=tuple(truth or [{} for _ in range(n_tickets)]),
        description=tuple(f"ticket {i}" for i in range(n_tickets)))
