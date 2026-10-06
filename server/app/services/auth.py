"""Who is calling /tickets, and which districts they may see. Supabase Auth checks the access token, and the analysts
table says the district: its row level security lets each person read only their own row.

  GET {SUPABASE_URL}/rest/v1/analysts?select=user_id,district_id,citywide&user_id=eq.<the token's user id>
      apikey: the publishable key        Authorization: Bearer <the caller's access token>

No token, or an invalid or expired one: 401. Signed in without an analyst row: 403. Sign-in not set up, Supabase
unreachable or failing, or an answer that is not exactly the caller's own row: 503. Every failure keeps the caller out.
"""
import base64
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from fastapi import Header, HTTPException

from app import config

# ponytail: a role is remembered for CACHE_S, so removing an analyst can take up to a minute to bite. Lower it, or
# drop the cache, if revocation must be instant.
CACHE_S = 60.0
CACHE_MAX = 1000  # tokens remembered at once; the oldest goes first
TIMEOUT_S = 5.0
_roles: dict[str, tuple[float, "Analyst"]] = {}  # sha256 of the token -> (expires, analyst); never the token itself
_lock = threading.Lock()


@dataclass(frozen=True)
class Analyst:
    user_id: str  # Supabase's user id, logged with every status change
    scope: object  # "all" (citywide) or a frozenset of district ids, as engine.tickets_for takes it


def configured() -> bool:
    """Whether analyst sign-in is set up. Without it /tickets answers 503 and /reports works as it always has."""
    return bool(config.SUPABASE_URL and config.SUPABASE_PUBLISHABLE_KEY)


def _user_id(token: str) -> str:
    """The user id in the token, read without checking the signature: Supabase checks the token on the same request,
    so this can only narrow the query to the caller's own row, never widen it."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return str(uuid.UUID(str(claims["sub"])))  # a uuid, so it is safe in the query string
    except (IndexError, KeyError, TypeError, ValueError):
        raise HTTPException(401, "Your sign-in is invalid or has expired.") from None


def _rows(token: str, user_id: str) -> list[dict]:
    """The caller's row in analysts, read with their own token and asked for by their user id as well: if RLS on
    analysts were ever switched off, Supabase would still return this person's row and nobody else's."""
    request = urllib.request.Request(
        f"{config.SUPABASE_URL.rstrip('/')}/rest/v1/analysts?select=user_id,district_id,citywide&user_id=eq.{user_id}",
        headers={"apikey": config.SUPABASE_PUBLISHABLE_KEY, "Authorization": f"Bearer {token}",
                 "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            rows = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise HTTPException(401, "Your sign-in is invalid or has expired.") from None
        if error.code == 403:
            raise HTTPException(403, "This account may not read the tickets.") from None
        raise HTTPException(503, "Sign-in is unavailable. Try again shortly.") from None
    except (OSError, ValueError):  # no connection, a timeout, an answer that is not JSON
        raise HTTPException(503, "Sign-in is unavailable. Try again shortly.") from None
    if not isinstance(rows, list):
        raise HTTPException(503, "Sign-in is unavailable. Try again shortly.")
    return rows


def analyst(authorization: str | None = Header(None)) -> Analyst:
    """The signed-in analyst, for Depends(). Raises the HTTP error instead of ever letting a caller through."""
    if not configured():
        raise HTTPException(503, "Analyst sign-in is not configured on this server.")
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Sign in first.")
    key = hashlib.sha256(token.encode()).hexdigest()
    with _lock:
        expires, known = _roles.get(key, (0.0, None))
    if known and expires > time.monotonic():
        return known
    user_id = _user_id(token)
    rows = _rows(token, user_id)
    if not rows:
        raise HTTPException(403, "This account is not an analyst.")
    if len(rows) != 1 or str(rows[0].get("user_id")) != user_id:  # never pick a role out of someone else's rows
        raise HTTPException(503, "Sign-in is misconfigured on the server.")
    row = rows[0]
    if row.get("citywide") is True:
        scope = "all"
    elif row.get("district_id") is not None:
        scope = frozenset({row["district_id"]})
    else:
        raise HTTPException(403, "This account is not an analyst.")
    who = Analyst(user_id, scope)
    with _lock:
        if len(_roles) >= CACHE_MAX:
            _roles.pop(next(iter(_roles)))
        _roles[key] = (time.monotonic() + CACHE_S, who)
    return who
