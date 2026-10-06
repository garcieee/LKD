"""GET and PATCH /tickets: the analyst dashboard's queue, one ticket per hazard however many reports it has.

Analysts only (services/auth.py), and only the tickets of their districts. The engine checks the scope, and a ticket
outside it answers exactly like a missing one: 404.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db.models import StatusUpdate, Ticket
from app.services import auth
from app.services.priority import severity
from app.services.ticket_sync import engine

router = APIRouter()


def _out(tickets: list[dict], store) -> list[Ticket]:
    """A ticket's heading is its first report's, like its photo."""
    headings = {r["id"]: r.get("heading") for r in store.all()}
    return [Ticket(**t, severity=severity(t["category"]), heading=headings.get(t["id"])) for t in tickets]


@router.get("/tickets", response_model=list[Ticket])
def list_tickets(request: Request, analyst: auth.Analyst = Depends(auth.analyst)):
    """Newest first: the tickets of the caller's districts, or of the whole city for a citywide analyst."""
    state = request.app.state
    return _out(engine.tickets_for(state.sync.db, analyst.scope), state.store)


@router.patch("/tickets/{ticket_id}", response_model=Ticket)
def update_ticket(ticket_id: str, body: StatusUpdate, request: Request, analyst: auth.Analyst = Depends(auth.analyst)):
    """Sets the status, logs who set it, and moves the ticket's reports on the public map with it."""
    state = request.app.state
    ticket = engine.set_status(state.sync.db, state.store, ticket_id, body.status, analyst.scope, analyst.user_id)
    if ticket is None:
        raise HTTPException(404, "No such ticket.")
    return _out([ticket], state.store)[0]
