# models/tickets/: the ticketing brain

Everything that decides **what a report is**, **whether it is the same place as another one** and **what to fix first** lives in this one folder. The server only hands requests to `engine.py`. The dashboard and the phone only show what comes back. Nothing else merges, scores or ranks.

| In here | The question it answers |
|---|---|
| `settings.py` | What are all the tunable numbers? (weights, radii, floors, bands) |
| `types.py` | What shape is a Report, a Ticket, a Breakdown? |
| `engine.py` | The only door: `attach` one report, `sync_once` for the server's loop, and the tickets of one district scope (see `ATTACH.md`) |
| `matching/` | Is this the same place? |
| `ranking/` | What do we fix first, and why? |
| `classification/` | What is it, how urgent, who fixes it? |
| `storage/` | The memory: SQLite (`db/lakad.db`) with tickets, sightings and status history. The only folder that touches a database |
| `resources/` | Static inputs: word lists, nearby places, offices |
| `sim/` | The experiments behind the numbers in `settings.py` |
| `eval/` | Datasets, metrics, splits and the evaluations of every model here. See `EVALUATION.md` |
| `tests/` | `server/.venv/bin/pytest models/tickets/tests` from the repo root (standard library only) |

## Rules that keep it in one place

1. `matching/`, `ranking/` and `classification/` are pure: numbers in, numbers out. No files, no database, no network. `tests/test_boundaries.py` enforces it.
2. Only `engine.py` uses `storage/`. Only the server uses `engine.py`.
3. Imports go one way: rules, then storage, then engine, then server.
4. Every tunable number is in `settings.py`. Nothing hides in the code.
5. The dashboard and the phone never score, rank or merge. They display what the server returns: `/reports`, with each report's ticket, district and priority.
6. Runtime data lives in the top-level `db/` folder, which is git-ignored: the cache (`reports.json`) and the photos, written by the server, and the database (`lakad.db`), written by `storage/`.
7. Additive only: `/reports` keeps its URL and shape and only gains fields, and a ticket reuses its first report's id, so nothing the dashboard, the phone or the routing code reads today breaks.

## Tuning

Edit `settings.py`, run the tests. The weights are judgment calls: show a few people pairs of tickets, ask which comes first, and adjust until the order agrees. `sim/sim_match.py` shows how GPS error decides the match radius. `sim/sim_rank.py` checks the score against ranking cases and rules such as "more reports never lowers the score".

## Status

**Built and tested:** `matching/`, `ranking/`, `classification/`, `resources/`, `engine.py` and `storage/` (standard library only), with every number in `settings.py`. `resources/districts.json` holds the boundaries of Makati's 23 barangays after the EMBO ruling (OpenStreetMap, ODbL; rebuilt by `resources/build_districts.py`), and `district_of` puts a point in District 1, District 2 or neither.

**Attached:** a loop inside the server (`server/app/services/ticket_sync.py`, every `SYNC_EVERY_S`) calls `engine.sync_once`: each new report joins or opens a ticket, the ticket gets its district and priority, tickets, sightings and every status change are kept in SQLite (`db/lakad.db`), and `/reports` gains `ticket_id`, `district_id`, `priority` and `band`. The dashboard reads and changes `/reports`; `engine.tickets_for` and `engine.set_status` (with a district scope) are ready for a ticket view behind a sign-in, which Lakad does not have.

**Evaluated:** see the Results section of `EVALUATION.md` for what met its targets, what missed, and the decisions waiting for the team. Nothing in the rules or `settings.py` was changed because of it.

**Known limits:** a ticket is scored when a report joins it, so its waiting time is not re-scored in between; `reporters` counts reports, not people, until the app sends a device id.
