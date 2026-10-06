# Attaching the models to the ticketing and the database

**Status: built, 2026-10-07.** Tickets live in SQLite on the Lakad server, filled by a loop inside it. The analyst sign-in that was built alongside them was removed the same day: the dashboard reads and changes `/reports`, and anyone who can open it can triage.

## Short answers

- **Are the models only for ticketing?** Yes. `models/tickets/` answers three questions about reports: is this the same place as an open ticket (`matching/`), what should be fixed first (`ranking/`), and what does the note say (`classification/`). Nothing else in Lakad uses it, and it uses nothing else but the SOS rules in `models/ticket_sos/`.
- **Are they lightweight?** Yes. The shipped code is about 66 KB, half of it the list of 719 places, and imports only the Python standard library (`tests/test_boundaries.py` enforces that). One report checked against 500 open tickets takes about 0.6 ms (match, foot traffic, danger, score). numpy, scipy and scikit-learn are for the evaluation only, live in `models/.venv`, and never ship.
- **Are they attached today?** Yes: the server's ticket loop runs them on every new report.

## The system

```
phone ─ POST /reports ─▶ Lakad server ─▶ db/reports.json      the cache: written first, the phone gets its 201 at once
                                              │
                                  the loop, every 5 s, inside the server (engine.sync_once)
                                              │  1. attach  models decide: same ticket or new, district, priority
                                              │  2. save    ticket and sighting into SQLite
                                              │  3. mark    ticket_id, district, priority back onto the report
                                              ▼
                                         db/lakad.db (SQLite): tickets, sightings, ticket_events

dashboard ─ GET /reports?include_sos=true&include_rejected=true, PATCH /reports/{id} ─▶ the cache
public map ◀─ GET /reports ◀─ the cache                                       no SOS, no rejected tickets
```

### The loop

| Property | How |
|---|---|
| A report is never lost | It is on disk in `db/reports.json` before anything else happens. If the loop stops, reports keep arriving and it catches up later |
| Running twice changes nothing | Every row is keyed by a report id (a ticket by its first report's id), so a retried turn writes the same rows again |
| A status set at the dashboard survives | `PATCH /reports/{id}` sends it to the report's ticket in SQLite and to every report of it at once. The loop writes `status` only for a new ticket or a reopen |
| The cache stays small | A report whose ticket has been fixed or rejected for more than 30 days leaves `reports.json`. SQLite keeps it |
| A bad report cannot block the queue | After 3 failed tries a report gets `sync_error` and is skipped; `/health` counts them |

Settings in `settings.py`: `SYNC_EVERY_S = 5`, `SYNC_MAX_TRIES = 3`, `CACHE_KEEP_DAYS = 30`.

`engine.set_status` and `engine.set_sos_kind` change a ticket and all its reports together; the server calls them with the scope "all" (there is no sign-in). `engine.tickets_for` takes the same scope and is ready for a ticket view behind a sign-in.

**Gaps to close before real use**
- There are no accounts. `PATCH /reports/{id}` and `GET /reports?include_sos=true` are open to anyone who can reach the server.
- A report that is already fixed or rejected when the loop first sees it (demo data written straight to the file) leaves `reports.json` after 30 days, like any closed ticket. `lakad.db` keeps it.
- Photo and SOS video URLs are long random ids, not signed: anyone who has a URL can open it. Upgrade: short-lived signed URLs from the server.
- The ten EMBO barangays are Taguig now, but the server's city box still accepts reports there. They get no district.

## Districts

| District | Barangays |
|---|---|
| 1, Western Makati (20) | Bangkal, Bel-Air, Carmona, Dasmariñas, Forbes Park, Kasilawan, La Paz, Magallanes, Olympia, Palanan, Pio del Pilar, Poblacion, San Antonio, San Isidro, San Lorenzo, Santa Cruz, Singkamas, Tejeros, Urdaneta, Valenzuela |
| 2, Eastern Makati (3) | Guadalupe Nuevo, Guadalupe Viejo, Pinagkaisahan |

Since the Supreme Court's EMBO ruling, Makati has 23 barangays. The ten EMBO barangays (Cembo, Comembo, East Rembo, Pembo, Pitogo, Post Proper Northside, Post Proper Southside, Rizal, South Cembo, West Rembo) belong to Taguig. Confirm the list with the city before relying on it.

The engine gives each ticket the district of its anchor point (its most accurate sighting), by point-in-polygon on barangay boundaries from OpenStreetMap (ODbL), in plain Python.

## What was built

| File | Change |
|---|---|
| `models/tickets/engine.py` | `attach`, `sync_once`, `tickets_for(scope)`, `set_status(scope)` |
| `models/tickets/storage/db.py` | SQLite: tickets, sightings, ticket_events, migrations by `PRAGMA user_version` |
| `models/tickets/classification/routing.py` | `district_of(lat, lng, districts)`, point-in-polygon |
| `models/tickets/resources/build_districts.py`, `districts.json`, `load.py` | barangay boundaries grouped by district |
| `models/tickets/settings.py`, `README.md` (Status) and tests | the loop settings; status; tests |
| `server/app/services/ticket_sync.py` | the loop: a daemon thread started from the app's lifespan |
| `server/app/config.py`, `server/.env.example` | `TICKETS_SYNC` |
| `server/app/db/models.py`, `store.py` | the loop's fields on `Report`; a remove method for pruning |
| `server/tests/test_ticket_sync.py` | the loop |

## Sources

- [Legislative districts of Makati](https://en.wikipedia.org/wiki/Legislative_districts_of_Makati) and [Things Are About To Get Complicated in Makati](https://halalan.up.edu.ph/things-are-about-to-get-complicated-in-makati/) (UP Halalan), for the districts after the EMBO ruling
