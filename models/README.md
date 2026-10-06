# models/

Decision models for Lakad, one folder per job. Each folder is self-contained: its rules, its memory and its tests.

| Folder | What it does | Status |
|---|---|---|
| `tickets/` | Merges reports of the same place, ranks what to fix first, classifies | Layout, settings and tests. See `tickets/README.md` |

Run the tests from the repo root:

- the ticketing rules (standard library only): `server/.venv/bin/pytest models/tickets/tests`
- everything, including the evaluation code (needs `models/.venv`, see `requirements-eval.txt`): `models/.venv/bin/pytest models`
