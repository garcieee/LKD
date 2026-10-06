"""The memory behind the engine: Supabase Postgres, written by the server only. The JSON cache is the server's own
db/reports.json. The only package that touches the network or a database; only engine.py uses it."""
