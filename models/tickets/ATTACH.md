# Attaching the models to the ticketing, the database and district logins

**Status: built, 2026-10-07.** Tickets live in SQLite on the Lakad server, and Supabase holds only sign-in and district roles. The Supabase part was written and tested first (`supabase/`); then the two branches at the end were built at the same time against it and the API contract, and merged into `main` together. An end-to-end run against a local stand-in for Supabase passed 19 of 19 checks across every role.

## Short answers

- **Are the models only for ticketing?** Yes. `models/tickets/` answers three questions about reports: is this the same place as an open ticket (`matching/`), what should be fixed first (`ranking/`), and what does the note say (`classification/`). Nothing else in Lakad uses it, and it uses nothing else.
- **Are they lightweight?** Yes. The shipped code is about 66 KB, half of it the list of 719 places, and imports only the Python standard library (`tests/test_boundaries.py` enforces that). One report checked against 500 open tickets takes about 0.6 ms (match, foot traffic, danger, score). numpy, scipy and scikit-learn are for the evaluation only, live in `models/.venv`, and never ship.
- **Are they attached today?** No. `engine.py` and `storage/` are scaffolds, and the server does not import `models/`.

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

analyst ─ signs in ─▶ Supabase Auth ─▶ an access token
dashboard ─ GET /tickets, PATCH /tickets/{id}, with the token ─▶ Lakad server
                                              ├─ who is this? the caller's row in Supabase's analysts table (RLS: own row)
                                              └─ only the tickets of that district, or all for citywide, from SQLite
public map ◀─ GET /reports ◀─ the cache                                       no SOS, no rejected tickets
```

### The loop

| Property | How |
|---|---|
| A report is never lost | It is on disk in `db/reports.json` before anything else happens, as today. If the loop stops, reports keep arriving and it catches up later |
| Running twice changes nothing | Every row is keyed by a report id (a ticket by its first report's id), so a retried turn writes the same rows again |
| An analyst's status survives | The loop writes `status` only for a new ticket or a reopen. Status changes come from `PATCH /tickets/{id}` and go to SQLite and the cache at once |
| The cache stays small | A report whose ticket has been fixed or rejected for more than 30 days leaves `reports.json`. SQLite keeps it |
| A bad report cannot block the queue | After 3 failed tries a report gets `sync_error` and is skipped; `/health` counts them |

New settings in `settings.py`: `SYNC_EVERY_S = 5`, `SYNC_MAX_TRIES = 3`, `CACHE_KEEP_DAYS = 30`.

## Sign-in and district roles (Supabase)

Supabase holds two small tables and nothing else: `districts` (1 and 2) and `analysts`, the roles. There are three roles: a District 1 analyst, a District 2 analyst, and a citywide analyst who sees both districts and any ticket that falls in neither. Migration: `supabase/migrations/20261007010000_district_roles.sql`.

**How a dashboard request is checked**
1. The dashboard signs in with Supabase (publishable key) and sends its access token to the Lakad server with every call.
2. The server asks Supabase for the caller's `analysts` row, using the caller's own token. Supabase checks the token, and RLS returns that one row.
3. A bad or expired token gets 401. A signed-in person with no row gets 403. If Supabase can't be reached, the answer is 503: the server fails closed. A good answer is cached for 60 s.
4. The server filters SQLite in one place, `engine.tickets_for(scope)` and `engine.set_status(scope)`. A ticket outside your districts behaves exactly like a missing one (404).

**What protects what**
- **Roles (in Supabase) are guarded by RLS.** You can read only your own row, nobody can give themselves a role or widen it to citywide, a role is one district or the whole city (never both, never neither), and the bare publishable key reads nothing. The tests are in `bash supabase/tests/run_local.sh`: 8 checks on a throwaway local Postgres. Breaking the migration on purpose in five ways made them fail every time.
- **Tickets (in SQLite) are guarded by the server.** SQLite has no RLS, so the district filter is the server's single choke point, and its tests prove each role. The trade-off: a bug there could show one district's tickets to another, with no database rule behind it. If the database itself must enforce districts later, move the tickets to Postgres; the first version of this plan, in git history, has that design.
- **The server never holds the Supabase secret key.** It only needs the URL and the publishable key, which is safe to expose because RLS bounds it.
- **Deleting an analyst's row** removes access within 60 s (the cache).

**Settings that live in the Supabase dashboard, not in SQL:** turn off "Allow new users to sign up" (an admin creates analyst accounts), keep anonymous sign-ins off, and run the Security Advisor after the migration (expect no warnings).

**Gaps to close before real use**
- `PATCH /reports/{id}` and `GET /reports?include_sos=true` are open to anyone today. Branch A closes both once sign-in is configured.
- Photo and SOS video URLs are long random ids, not signed: anyone who has a URL can open it. Upgrade: short-lived signed URLs from the server.
- The ten EMBO barangays are Taguig now, but the server's city box still accepts reports there. They get no district, so only citywide analysts see them.
- The dashboard keeps its session in the browser (supabase-js default), the usual trade-off for a web app.
- On the free tier, a project pauses after a week without use.

**If you already ran the first version of the migration** (tickets in Supabase), clear it before running the new one:

```sql
drop table if exists public.ticket_events, public.sightings, public.tickets, public.analysts, public.districts cascade;
drop function if exists private.ticket_updated();
drop schema if exists private;
```

## Districts

| District | Barangays |
|---|---|
| 1, Western Makati (20) | Bangkal, Bel-Air, Carmona, Dasmariñas, Forbes Park, Kasilawan, La Paz, Magallanes, Olympia, Palanan, Pio del Pilar, Poblacion, San Antonio, San Isidro, San Lorenzo, Santa Cruz, Singkamas, Tejeros, Urdaneta, Valenzuela |
| 2, Eastern Makati (3) | Guadalupe Nuevo, Guadalupe Viejo, Pinagkaisahan |

Since the Supreme Court's EMBO ruling, Makati has 23 barangays. The ten EMBO barangays (Cembo, Comembo, East Rembo, Pembo, Pitogo, Post Proper Northside, Post Proper Southside, Rizal, South Cembo, West Rembo) belong to Taguig. Confirm the list with the city before relying on it.

The engine gives each ticket the district of its anchor point (its most accurate sighting), by point-in-polygon on barangay boundaries from OpenStreetMap (ODbL), in plain Python.

## Execution: two branches at once

`ticket-attach` is the base: this plan, the roles migration and its RLS tests, and the engine scaffold.

### Branch A, `tickets-engine`: the models attached to the ticketing

| File | Change |
|---|---|
| `models/tickets/engine.py` | `attach`, `sync_once`, `tickets_for(scope)`, `set_status(scope)` |
| `models/tickets/storage/db.py` (replaces `supabase.py`) | SQLite: tickets, sightings, ticket_events, migrations by `PRAGMA user_version` |
| `models/tickets/classification/routing.py` | `district_of(lat, lng, districts)`, point-in-polygon |
| `models/tickets/resources/build_districts.py`, `districts.json`, `load.py` | barangay boundaries grouped by district |
| `models/tickets/settings.py`, `README.md` (Status) and tests | the loop settings; status; tests |
| `server/app/services/ticket_sync.py` | the loop: a daemon thread started from the app's lifespan |
| `server/app/services/auth.py` | the token to role check against Supabase, cached 60 s |
| `server/app/routers/tickets.py`, `server/app/main.py` | `GET /tickets`, `PATCH /tickets/{id}`; one include line |
| `server/app/config.py`, `server/.env.example` | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `TICKETS_SYNC` |
| `server/app/db/models.py`, `store.py`, `routers/reports.py` | `Ticket`; a remove method for pruning; with sign-in on, the old `PATCH` answers 403 and the public list never shows SOS |
| `server/tests/test_ticket_sync.py`, `test_tickets_api.py` | the loop; every role against the API |

### Branch B, `district-auth`: district sign-in in the dashboard

| File | Change |
|---|---|
| `dashboard/src/api/supabase.ts`, `supabase.test.ts` | sign in and out, session, the caller's role row and its label |
| `dashboard/src/api/client.ts` | with sign-in on: `GET /tickets` and `PATCH /tickets/{id}` with the token; else `/reports` as today |
| `dashboard/src/features/auth/LoginGate.tsx`, `dashboard/src/App.tsx` | the sign-in screen and "District 1 (Western Makati) · Sign out" |
| `dashboard/src/config/env.ts`, `.env.example`, `src/types/api.ts` | `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`; optional ticket fields |
| `dashboard/package.json`, `package-lock.json` | `@supabase/supabase-js` |
| `supabase/README.md`, `LAKAD-README.md` | project setup and roles; Supabase in the disclosure table |

### The contract between them

- `GET /tickets` returns 200 and a list of tickets, newest first. A ticket is every `Report` field plus `priority` (0 to 100), `band`, `district_id` (1, 2 or null) and `reporters`.
- `PATCH /tickets/{id}` takes `{"status": …}` and returns the ticket.
- Both need `Authorization: Bearer <Supabase access token>`. The errors are 401 (no, bad or expired token), 403 (signed in, no role), 404 (no such ticket, or not in your districts) and 503 (sign-in not configured, or Supabase unreachable).

### Why the two merge cleanly

- **No file is in both lists.** Git only conflicts when both sides change the same lines of the same file.
- **The contract above and the migration are fixed on the base.** A later schema change is a new migration file, never an edit to this one.
- **Neither branch edits this plan.**
- **Before merging,** merge `main` into each branch, run every suite, and trial-merge both onto `main` in a scratch worktree. Then merge A and B one after the other, in either order.

Teammates are changing `server/app/routers/reports.py`, `server/app/main.py`, `dashboard/src/api/client.ts` and `dashboard/src/App.tsx` today, so our edits there stay at a few lines.

## What you set up in Supabase

1. Create a free project (Singapore is closest to Manila).
2. In the SQL editor, run `supabase/migrations/20261007010000_district_roles.sql`.
3. Under Authentication, turn off new sign-ups and keep anonymous sign-ins off.
4. Add one user per role (Authentication > Users > Add user), then give each a role:

   ```sql
   insert into public.analysts (user_id, district_id, name) select id, 1, 'District 1 analyst' from auth.users where email = 'district1@example.com';
   insert into public.analysts (user_id, district_id, name) select id, 2, 'District 2 analyst' from auth.users where email = 'district2@example.com';
   insert into public.analysts (user_id, citywide, name) select id, true, 'Citywide analyst' from auth.users where email = 'citywide@example.com';
   ```

5. Put the project URL and the publishable key into `server/.env` (`SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`) and into `dashboard/.env.local` (`VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`). Lakad does not use the secret key anywhere. Keys never go in the repo or in chat.

## Sources

- [Legislative districts of Makati](https://en.wikipedia.org/wiki/Legislative_districts_of_Makati) and [Things Are About To Get Complicated in Makati](https://halalan.up.edu.ph/things-are-about-to-get-complicated-in-makati/) (UP Halalan), for the districts after the EMBO ruling
- Supabase docs: [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security), [API keys](https://supabase.com/docs/guides/api/api-keys), [upcoming changes to API keys](https://supabase.com/changelog/29260-upcoming-changes-to-supabase-api-keys)
