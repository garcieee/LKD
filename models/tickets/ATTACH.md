# Attaching the models to the ticketing, the database and district logins

**Status: plan, 2026-10-07.** The database contract was written and tested first (`supabase/`), so the two branches at the end can be built at the same time against it.

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
                                              │  2. push    upsert the ticket and the sighting to Supabase (secret key)
                                              │  3. mark    write ticket_id, district, priority back onto the report
                                              │  4. pull    status changes analysts made, back into the cache
                                              ▼
analyst ─ signs in ─▶ Supabase Auth ─▶ Postgres: tickets, sightings, ticket_events      RLS: own district only
public map ◀─ GET /reports ◀─ the cache                                                 no SOS, no rejected tickets
```

### The loop

| Property | How |
|---|---|
| A report is never lost | It is on disk in `db/reports.json` before anything else happens, as today. If Supabase is down or not set up, reports keep arriving and the loop catches up later |
| Running twice changes nothing | Every row is keyed by a report id (a ticket by its first report's id), so a retried turn upserts the same rows again |
| One writer | Only the server writes tickets and sightings. Analysts change one column, `status`, through RLS |
| Status flows back | Each turn pulls tickets changed since the last pull, minus a 60 s overlap, and applies them idempotently. Overlapping the window covers transactions that committed late |
| An analyst's status survives | Upserts send only the columns the engine owns, never `status` (except a reopen) |
| The cache stays small | A report whose ticket has been fixed or rejected for more than 30 days leaves `reports.json`. Postgres keeps it |
| A bad report cannot block the queue | After 3 failed tries a report gets `sync_error` and is skipped; `/health` counts them |
| Works without Supabase | With `SUPABASE_URL` empty the loop still attaches and ranks in the cache, and the dashboard reads the server as it does today. Safe for the demo |

New settings in `settings.py`: `SYNC_EVERY_S = 5`, `SYNC_MAX_TRIES = 3`, `PULL_OVERLAP_S = 60`, `CACHE_KEEP_DAYS = 30`.

## Supabase: logins and district rules, nothing else

Supabase does two jobs here: **Auth** (analyst accounts) and **Postgres rows guarded by row level security**. It does not store photos (they stay on the Lakad server), and Realtime and Edge Functions are not used. RLS can only guard rows that live in Postgres, so the tickets analysts read live there.

| Caller | Key | Postgres role | May |
|---|---|---|---|
| Lakad server | secret (`sb_secret_…`), only in `server/.env` | `service_role`, bypasses RLS | write tickets and sightings, read status changes |
| Analyst | publishable key plus their login | `authenticated` | read their district's tickets, sightings and status history; change `status` |
| Anyone else | publishable key alone | `anon` | nothing |

**The rule:** a ticket is visible when `tickets.district_id` equals the district in the signed-in person's row in `analysts`. The migration is `supabase/migrations/20261007010000_tickets_by_district.sql`. Choices behind it:

- **The district lives in a table, not in the token.** Deleting an analyst's row takes access away on the next query, with no token left to expire. Only an admin can write that table. `user_metadata` is never used, because users can edit their own.
- **It fails closed.** Someone signed in without an analyst row matches no ticket. A ticket with no district (outside both) is seen by no analyst.
- **Least privilege.** Supabase grants `anon` and `authenticated` everything on new tables, and policies do not take that back. The migration revokes it all and grants back `select`, plus `update` on the single column `status`.
- **Every status change is recorded** in `ticket_events` (who, from, to, when) by a trigger. Analysts cannot write that table. The trigger runs with its owner's rights, so it lives in a `private` schema the API cannot reach, with a pinned `search_path`.
- **Fast enough:** `(select auth.uid())` runs once per query, and `district_id` is indexed.

**Tested:** `bash supabase/tests/run_local.sh` applies the migration to a throwaway local Postgres and checks 13 promises. Among them: each district sees only its own tickets; a non-analyst and the bare publishable key see nothing; an analyst cannot change another district's ticket, any column but `status`, or their own district; changes are logged with who made it. The migration was broken on purpose in six ways and the tests caught every one. Local Postgres is 14 and Supabase runs 15 or later; the migration uses nothing newer than 14.

**Settings that live in the Supabase dashboard, not in SQL:** turn off "Allow new users to sign up" (an admin creates analyst accounts), keep anonymous sign-ins off, expose only `public` in the Data API, and run the Security Advisor after the migration (expect no warnings). Optional: require MFA by adding `(select auth.jwt() ->> 'aal') = 'aal2'` to the policies.

**Gaps to close before real use:**
- `PATCH /reports/{id}` and `GET /reports?include_sos=true` are open to anyone today. Branch A closes both when Supabase is on.
- Photo and SOS video URLs are long random ids, not signed: anyone who has a URL can open it. Upgrade: short-lived signed URLs from the server.
- The ten EMBO barangays are Taguig now, but the server's city box still accepts reports there. They get no district, so no analyst sees them. Tighten `in_city` to the new boundary, or tell the reporter.
- On the free tier, a project pauses after a week without use.

## Districts

| District | Barangays |
|---|---|
| 1, Western Makati (20) | Bangkal, Bel-Air, Carmona, Dasmariñas, Forbes Park, Kasilawan, La Paz, Magallanes, Olympia, Palanan, Pio del Pilar, Poblacion, San Antonio, San Isidro, San Lorenzo, Santa Cruz, Singkamas, Tejeros, Urdaneta, Valenzuela |
| 2, Eastern Makati (3) | Guadalupe Nuevo, Guadalupe Viejo, Pinagkaisahan |

Since the Supreme Court's EMBO ruling, Makati has 23 barangays. The ten EMBO barangays (Cembo, Comembo, East Rembo, Pembo, Pitogo, Post Proper Northside, Post Proper Southside, Rizal, South Cembo, West Rembo) belong to Taguig. Confirm the list with the city before relying on it.

The engine gives each ticket the district of its anchor point (its most accurate sighting), by point-in-polygon on barangay boundaries, in plain Python. That needs the boundaries of Makati's barangays: from OpenStreetMap (ODbL) through Overpass, the same way `resources/places.json` was built, or from the Makati Data Hub if the organizers shared them.

## Execution: two branches at once

`ticket-attach`, this branch, is the base. It holds this plan, the migration, the RLS tests, the engine scaffold and `tests/test_contract.py`, which fails if the engine's columns and the tables drift apart. Both branches start from it.

### Branch A, `tickets-engine`: the models attached to the ticketing

| File | Change |
|---|---|
| `models/tickets/engine.py` | `attach`, `sync_once`, `database` |
| `models/tickets/storage/supabase.py` | upserts and the status pull, standard library HTTP |
| `models/tickets/classification/routing.py` | `district_of(lat, lng, districts)`, point-in-polygon |
| `models/tickets/resources/build_districts.py`, `districts.json`, `load.py` | barangay boundaries grouped by district |
| `models/tickets/settings.py`, `README.md` | the four loop settings; status |
| `models/tickets/tests/test_engine.py`, `test_district.py`, `test_settings.py` | tests |
| `server/app/services/ticket_sync.py` | the loop: a daemon thread calling `engine.sync_once` every `SYNC_EVERY_S` |
| `server/app/main.py`, `config.py` | start the loop; read `SUPABASE_URL`, `SUPABASE_SECRET_KEY` |
| `server/app/db/models.py` | `Report` gains optional `ticket_id`, `district_id`, `priority`, `band` |
| `server/app/routers/reports.py` | with Supabase on: `PATCH` answers 403, the public list ignores `include_sos` and `include_rejected` |
| `server/.env.example`, `server/tests/test_ticket_sync.py` | the two variables, empty; the loop on a temp store with a fake database |

Done when the rule tests, the contract test and the server tests pass, and a report posted to a local server shows its `ticket_id` and priority in `GET /reports` within one turn. With a Supabase project, it also appears in `tickets`.

### Branch B, `district-auth`: district logins in the dashboard

| File | Change |
|---|---|
| `dashboard/src/api/supabase.ts`, `supabase.test.ts` | the client, sign in and out, tickets with their sightings, status change, row to `Report` adapter |
| `dashboard/src/api/client.ts` | `listReports` and `patchStatus` go to Supabase when it is configured, else to the server as today |
| `dashboard/src/features/auth/LoginGate.tsx`, `dashboard/src/App.tsx` | the sign-in screen, and "District 1 (Western Makati) · Sign out" |
| `dashboard/src/config/env.ts`, `dashboard/.env.example` | `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` |
| `dashboard/src/types/api.ts` | optional `priority`, `band`, `district_id` |
| `dashboard/package.json`, `package-lock.json` | `@supabase/supabase-js` (about 650 KB unpacked plus five sub-packages), if approved |
| `supabase/README.md` | project setup, creating an analyst, the dashboard settings above |
| `LAKAD-README.md` | Supabase (free tier) in the disclosure table |

Done when the dashboard tests, lint and build pass, and, signed in as a District 1 analyst, the queue and the map show District 1 only, the status stepper works, and signed out the queue asks for a sign-in.

### Why the two merge cleanly

- **No file is in both lists.** Git only conflicts when both sides change the same lines of the same file.
- **The contract is frozen on the base:** this plan, the migration and the column lists. A schema change after the split is a new migration file with its own timestamp, never an edit to this one.
- **Neither branch edits this plan.** It gets updated after the merge.
- **Before merging,** merge `main` into each branch, run every suite, and trial-merge both onto `main` in a scratch worktree. Then merge A and B one after the other, in either order.

The real risk is outside the two branches. Teammates are changing `server/app/routers/reports.py`, `server/app/main.py`, `dashboard/src/api/client.ts` and `dashboard/src/App.tsx` right now. Keep our edits there to a few lines, and merge `main` in just before merging back.

## Needed before executing

1. **Boundaries:** OK to download Makati's barangay boundaries from OpenStreetMap via Overpass (one query, well under 1 MB)? Or the Makati Data Hub file, if you have it.
2. **Dashboard client:** OK to `npm install @supabase/supabase-js`? Without it the dashboard can call Supabase's REST endpoints with `fetch`, but session refresh is then ours to get right.
3. **A Supabase project:** you create it (free tier), paste the migration into the SQL editor, create the analyst accounts, and put the URL and keys into `server/.env` and `dashboard/.env.local` yourselves. Keys never go in the repo or in chat.
4. **Merge timing:** both branches are off by default (no Supabase settings means today's behaviour), but say whether they should go into `main` before 1:00 PM.

## Sources

- [Legislative districts of Makati](https://en.wikipedia.org/wiki/Legislative_districts_of_Makati) and [Things Are About To Get Complicated in Makati](https://halalan.up.edu.ph/things-are-about-to-get-complicated-in-makati/) (UP Halalan), for the districts after the EMBO ruling
- Supabase docs: [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security), [API keys](https://supabase.com/docs/guides/api/api-keys), [upcoming changes to API keys](https://supabase.com/changelog/29260-upcoming-changes-to-supabase-api-keys)
