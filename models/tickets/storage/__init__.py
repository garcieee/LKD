"""The memory behind the engine: SQLite (db/lakad.db), with tickets, sightings and their status history. The JSON
cache is the server's own db/reports.json. The only package that touches a database; only engine.py uses it."""
