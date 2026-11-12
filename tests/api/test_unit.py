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
    assert s.trusted_proxy_hops == 0


def test_settings_proxy_hops_from_env(monkeypatch):
    monkeypatch.setenv("SPLITKIT_PG_DSN", "postgresql://x")
    monkeypatch.setenv("SPLITKIT_ADMIN_KEY", "k" * 32)
    monkeypatch.setenv("SPLITKIT_TRUSTED_PROXY_HOPS", "2")
    assert Settings.from_env().trusted_proxy_hops == 2
    # legacy boolean flag means one trusted proxy
    monkeypatch.delenv("SPLITKIT_TRUSTED_PROXY_HOPS")
    monkeypatch.setenv("SPLITKIT_TRUST_PROXY", "true")
    assert Settings.from_env().trusted_proxy_hops == 1


def test_settings_rejects_negative_proxy_hops():
    with pytest.raises(ValueError, match="proxy hops"):
        Settings(pg_dsn="postgresql://x", admin_key="k" * 32, trusted_proxy_hops=-1)


class _Req:
    def __init__(self, xff: str | None, peer: str = "10.0.0.9"):
        self.headers = {"x-forwarded-for": xff} if xff is not None else {}
        self.client = type("C", (), {"host": peer})()


@pytest.mark.parametrize(
    ("xff", "hops", "expected"),
    [
        (None, 2, "10.0.0.9"),  # no header: socket peer
        ("1.1.1.1, 2.2.2.2", 0, "10.0.0.9"),  # proxies not trusted: header ignored
        ("203.0.113.5", 1, "203.0.113.5"),  # ALB appended the real client
        # CloudFront appends viewer IP, ALB appends edge IP; spoofed prefix ignored
        ("6.6.6.6, 203.0.113.5, 130.176.0.1", 2, "203.0.113.5"),
        ("203.0.113.5, 130.176.0.1", 2, "203.0.113.5"),
        ("130.176.0.1", 2, "10.0.0.9"),  # fewer entries than hops: don't trust it
    ],
)
def test_client_id_uses_rightmost_trusted_hop(xff, hops, expected):
    from splitkit.api.app import _client_id

    assert _client_id(_Req(xff), hops) == expected
