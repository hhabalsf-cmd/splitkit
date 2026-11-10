"""API pieces that need no database."""

import pytest

from splitkit.api.ratelimit import FixedWindowLimiter
from splitkit.api.settings import Settings


def test_limiter_allows_up_to_limit_per_window():
    clock = [1000.0]
    limiter = FixedWindowLimiter(limit=3, window_s=60, clock=lambda: clock[0])
    assert [limiter.allow("ip") for _ in range(4)] == [True, True, True, False]
    assert limiter.allow("other-ip") is True
    clock[0] += 60
    assert limiter.allow("ip") is True


def test_limiter_zero_disables():
    limiter = FixedWindowLimiter(limit=0)
    assert all(limiter.allow("ip") for _ in range(10_000))


def test_limiter_prunes_old_windows():
    clock = [0.0]
    limiter = FixedWindowLimiter(limit=5, window_s=1, clock=lambda: clock[0])
    for i in range(100):
        limiter.allow(f"ip-{i}")
    clock[0] += 5
    limiter.allow("fresh")
    assert limiter.tracked_clients() == 1


def test_settings_from_env_requires_secrets(monkeypatch):
    monkeypatch.delenv("SPLITKIT_PG_DSN", raising=False)
    monkeypatch.delenv("SPLITKIT_ADMIN_KEY", raising=False)
    with pytest.raises(ValueError, match="SPLITKIT_PG_DSN"):
        Settings.from_env()
    monkeypatch.setenv("SPLITKIT_PG_DSN", "postgresql://x")
    monkeypatch.setenv("SPLITKIT_ADMIN_KEY", "short")
    with pytest.raises(ValueError, match="at least 16"):
        Settings.from_env()


def test_settings_from_env_parses_options(monkeypatch):
    monkeypatch.setenv("SPLITKIT_PG_DSN", "postgresql://x")
    monkeypatch.setenv("SPLITKIT_ADMIN_KEY", "k" * 32)
    monkeypatch.setenv("SPLITKIT_RATE_LIMIT_PER_MIN", "0")
    monkeypatch.setenv("SPLITKIT_CORS_ORIGINS", "https://a.example, https://b.example")
    s = Settings.from_env()
    assert s.rate_limit_per_min == 0
    assert s.cors_origins == ("https://a.example", "https://b.example")
