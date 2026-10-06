# models/tickets/: the ticketing brain

Everything that decides **what a report is**, **whether it is the same place as another one** and **what to fix first** lives in this one folder. The server only hands requests to `engine.py`. The dashboard and the phone only show what comes back. Nothing else merges, scores or ranks.

| In here | The question it answers |
|---|---|
| `settings.py` | What are all the tunable numbers? (weights, radii, floors, bands) |
| `types.py` | What shape is a Report, a Ticket, a Breakdown? |
| `engine.py` | The only door: submit a report, vote, change status, list ranked tickets, nearby tickets |
| `matching/` | Is this the same place? |
| `ranking/` | What do we fix first, and why? |
| `classification/` | What is it, how urgent, who fixes it? |
| `storage/` | The memory: the JSON inbox and the SQLite database (code). The only folder that touches disk; it reads and writes the top-level `db/` |
| `resources/` | Static inputs: word lists, nearby places, offices |
| `sim/` | The experiments behind the numbers in `settings.py` |
| `tests/` | `server/.venv/bin/pytest models` from the repo root |

## Rules that keep it in one place

1. `matching/`, `ranking/` and `classification/` are pure: numbers in, numbers out. No files, no database, no network. `tests/test_boundaries.py` enforces it.
2. Only `engine.py` uses `storage/`. Only the server uses `engine.py`.
3. Imports go one way: rules, then storage, then engine, then server.
4. Every tunable number is in `settings.py`. Nothing hides in the code.
5. The dashboard and the phone never score, rank or merge. They display what `/tickets` returns.
6. Runtime data (inbox, database, photos) lives in the top-level `db/` folder, which is git-ignored. `db/` is data only; the code that uses it is `storage/`.
7. Additive only: `/reports` keeps its URL and shape and only gains fields, and a ticket reuses its first report's id, so nothing the dashboard, the phone or the routing code reads today breaks.

## Tuning

Edit `settings.py`, run the tests. The weights are judgment calls: show a few people pairs of tickets, ask which comes first, and adjust until the order agrees. `sim/sim_match.py` shows how GPS error decides the match radius. `sim/sim_rank.py` checks the score against ranking cases and rules such as "more reports never lowers the score".

## Status

Stubs, plus `settings.py` (the numbers from `sim/`) and the layout test. No ticketing logic yet.
