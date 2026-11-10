"""Service configuration, read from the environment and validated at startup."""

from __future__ import annotations

import os
from dataclasses import dataclass

MIN_ADMIN_KEY_LEN = 16


@dataclass(frozen=True)
class Settings:
    pg_dsn: str
    admin_key: str
    rate_limit_per_min: int = 1200  # per client IP; 0 disables
    cors_origins: tuple[str, ...] = ()
    pool_max: int = 10
    trust_proxy: bool = False  # honor X-Forwarded-For (only behind a trusted load balancer)

    def __post_init__(self) -> None:
        if not self.pg_dsn:
            raise ValueError("SPLITKIT_PG_DSN is required")
        if len(self.admin_key) < MIN_ADMIN_KEY_LEN:
            raise ValueError(f"SPLITKIT_ADMIN_KEY must be at least {MIN_ADMIN_KEY_LEN} characters")
        if self.rate_limit_per_min < 0 or self.pool_max < 1:
            raise ValueError("rate limit must be >= 0 and pool size >= 1")

    @classmethod
    def from_env(cls) -> Settings:
        dsn = os.environ.get("SPLITKIT_PG_DSN", "")
        if not dsn:
            raise ValueError("SPLITKIT_PG_DSN is required")
        origins = os.environ.get("SPLITKIT_CORS_ORIGINS", "")
        return cls(
            pg_dsn=dsn,
            admin_key=os.environ.get("SPLITKIT_ADMIN_KEY", ""),
            rate_limit_per_min=int(os.environ.get("SPLITKIT_RATE_LIMIT_PER_MIN", "1200")),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
            pool_max=int(os.environ.get("SPLITKIT_POOL_MAX", "10")),
            trust_proxy=os.environ.get("SPLITKIT_TRUST_PROXY", "").lower() in ("1", "true", "yes"),
        )
