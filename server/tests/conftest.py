"""Every test starts with analyst sign-in off, whatever server/.env says. The sign-in tests turn it on themselves."""
import pytest

from app import config


@pytest.fixture(autouse=True)
def sign_in_off(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "")
