#!/usr/bin/env bash
# Applies every migration to a throwaway local Postgres and runs the row level security tests against it.
# Needs initdb, pg_ctl and psql on PATH (brew install postgresql). Leaves nothing behind.
#   bash supabase/tests/run_local.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
port=$((54000 + RANDOM % 1000))
cleanup() { pg_ctl -D "$tmp/data" -m immediate stop >/dev/null 2>&1 || true; rm -rf "$tmp"; }
trap cleanup EXIT

initdb -D "$tmp/data" -U postgres -A trust --no-locale -E UTF8 >/dev/null
pg_ctl -D "$tmp/data" -o "-p $port -k $tmp -c listen_addresses=''" -l "$tmp/log" -w start >/dev/null
run() { psql -X -q -v ON_ERROR_STOP=1 -h "$tmp" -p "$port" -U postgres -d postgres -f "$1"; }

run "$here/shim.sql"
for migration in "$here"/../migrations/*.sql; do run "$migration"; done
run "$here/rls_test.sql"
echo "RLS tests passed on $(postgres --version)"
