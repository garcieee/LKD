# models/

Decision models for Lakad, one folder per job. Each folder is self-contained: its rules, its memory and its tests.

| Folder | What it does | Status |
|---|---|---|
| `tickets/` | Merges reports of the same place, ranks what to fix first, classifies | Layout, settings and tests. See `tickets/README.md` |

Run every test from the repo root: `server/.venv/bin/pytest models`
