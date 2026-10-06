"""The one place that talks to the database: Supabase's Data API, from the server only, with the secret key (role
service_role, which bypasses RLS). Standard library HTTP (urllib), so no new dependency. Plan: ATTACH.md.

Scaffold: the bodies come on the tickets-engine branch.
"""


class Supabase:
    def __init__(self, url: str, secret_key: str, timeout_s: float = 8.0):
        self.url, self.secret_key, self.timeout_s = url.rstrip("/"), secret_key, timeout_s

    def upsert_tickets(self, rows: list[dict]) -> None:
        """POST /rest/v1/tickets with Prefer: resolution=merge-duplicates. Sends only the columns it sets, so an
        analyst's status is never overwritten by a later report."""
        raise NotImplementedError

    def upsert_sightings(self, rows: list[dict]) -> None:
        raise NotImplementedError

    def status_changes(self, since_iso: str) -> list[dict]:
        """id, status, updated_at of every ticket changed after since_iso, oldest first."""
        raise NotImplementedError
