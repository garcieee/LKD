"""The engine writes the rows (tickets-engine branch) and the dashboard reads them (district-auth branch). Both build
against the tables in supabase/migrations/, so the engine's column lists and the tables must stay equal."""
import re
from pathlib import Path

from models.tickets import engine

MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"


def columns(table: str) -> set[str]:
    """Column names of `create table public.<table>`: lines indented by exactly two spaces, constraints aside."""
    sql = "\n".join(p.read_text() for p in sorted(MIGRATIONS.glob("*.sql")))
    found = re.search(rf"create table public\.{table} \((.*?)\n\);", sql, re.S)
    assert found, f"no create table public.{table} in {MIGRATIONS}"
    return set(re.findall(r"^  ([a-z_]+) ", found.group(1), re.M))


def test_ticket_rows_match_the_tickets_table():
    assert set(engine.TICKET_COLUMNS) == columns("tickets")


def test_sighting_rows_match_the_sightings_table():
    assert set(engine.SIGHTING_COLUMNS) == columns("sightings")
