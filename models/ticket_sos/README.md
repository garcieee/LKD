# models/ticket_sos/: the SOS rules

An SOS is the phone's hold-to-record video (`POST /sos`, category `sos`): someone asking for help, not a hazard. So it skips the hazard rules in `tickets/`. It never joins another ticket and is never scored: it opens its own ticket at priority 100, band Critical (100 is the most a hazard's score can reach), and the dashboard lists every open SOS above every hazard, the unsorted ones first.

## Who must respond

A person at the dashboard watches the silent clip and sorts the SOS into one of three kinds, in this order:

| Kind | Label | Covers |
|---|---|---|
| `police` | Police | Crime, violence or a threat |
| `medical` | Medical | Injury, collapse or illness |
| `fire_rescue` | Fire and rescue | Fire, flood or someone trapped |

Until then its `sos_kind` is null, shown as "Unsorted". The phone never asks. Sorting changes neither the status (Confirm and Reject stay separate) nor the history in `ticket_events`. It goes through `PATCH /reports/{id}`: once the loop has given the SOS its ticket (within about 5 s), onto the ticket in `lakad.db` and its report together (`engine.set_sos_kind`); before that onto the report, and the loop carries it into the ticket. Only an SOS can have a kind: the server, the engine and a check in `lakad.db` all refuse one on a hazard.

`sos.py` is plain Python with no I/O, called by `tickets/engine.py`. The kinds are mirrored by `server/app/db/models.py` (`SosKind`, tested equal) and `dashboard/src/types/api.ts`.

## Tests

`server/.venv/bin/pytest models/ticket_sos/tests` from the repo root (standard library only).

## Limits

- A person sorts every SOS; nothing reads the clip. One kind per SOS: a fire with someone hurt goes to whoever must come first.
- Sorting tells the dashboard who must respond. Lakad does not call the police, an ambulance or the fire service.
- A sorted SOS can change kind but not go back to unsorted.
