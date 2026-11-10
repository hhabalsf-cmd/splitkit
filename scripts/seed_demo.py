"""Seed a demo experiment with 14 days of simulated traffic and a known true effect.

The experiment is created through the real API (admin key from SPLITKIT_ADMIN_KEY).
Traffic is then backfilled straight into Postgres (SPLITKIT_PG_DSN) because the
ingest API, by design, refuses timestamps older than 7 days, and a realistic
timeline needs history. Users are bucketed with the production hash, so the
data is indistinguishable from SDK traffic.

    SPLITKIT_URL=http://127.0.0.1:8080 python scripts/seed_demo.py
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np
import psycopg

from splitkit.assignment import Variant, assign

log = logging.getLogger("seed_demo")

KEY = "checkout-redesign"
USERS = 20_000
DAYS = 14
BASE_RATE = 0.10
TRUE_LIFT = 0.015  # absolute, on purchase rate
METRICS = [
    {"name": "purchase_rate", "type": "proportion", "event": "purchase", "window_days": 7,
     "description": "Bought within 7 days of first seeing checkout"},
    {"name": "revenue_per_user", "type": "mean", "event": "purchase", "agg": "sum", "window_days": 7},
    {"name": "revenue_per_session", "type": "ratio", "window_days": 7,
     "numerator": {"event": "purchase", "agg": "sum"},
     "denominator": {"event": "session_start", "agg": "count"}},
]


def create_experiment(base: str, admin_key: str) -> dict:
    headers = {"X-API-Key": admin_key}
    payload = {
        "key": KEY,
        "variants": [{"name": "control", "weight": 0.5}, {"name": "treatment", "weight": 0.5}],
        "metrics": METRICS,
    }
    r = httpx.post(f"{base}/v1/experiments", json=payload, headers=headers)
    if r.status_code == 409:
        raise SystemExit(f"'{KEY}' already exists; drop it or change KEY to reseed")
    r.raise_for_status()
    httpx.post(f"{base}/v1/experiments/{KEY}/status", json={"status": "running"}, headers=headers).raise_for_status()
    return r.json()["data"]


def simulate(salt: str, variants: tuple[Variant, ...], now: datetime, rng: np.random.Generator):
    start = now - timedelta(days=DAYS)
    exposures, events = [], []
    for i in range(USERS):
        user = f"demo-{i:06d}"
        variant = assign(variants, salt, user)
        seen = start + timedelta(seconds=float(rng.uniform(0, DAYS * 86_400)))
        exposures.append((KEY, user, variant, seen))
        latest = min(seen + timedelta(days=7), now)
        span = (latest - seen).total_seconds()

        def at() -> datetime:
            return seen + timedelta(seconds=float(rng.uniform(0, span)))  # noqa: B023 (bound per user)

        for s in range(int(rng.poisson(2.0)) + 1):
            events.append((f"{user}-s{s}", user, "session_start", None, at()))
        rate = BASE_RATE + (TRUE_LIFT if variant == "treatment" else 0.0)
        if rng.random() < rate:
            events.append((f"{user}-p", user, "purchase", round(float(rng.gamma(2.0, 24.0)), 2), at()))
    return exposures, events


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    base = os.environ.get("SPLITKIT_URL", "http://127.0.0.1:8080")
    admin_key, dsn = os.environ.get("SPLITKIT_ADMIN_KEY"), os.environ.get("SPLITKIT_PG_DSN")
    if not admin_key or not dsn:
        log.error("set SPLITKIT_ADMIN_KEY and SPLITKIT_PG_DSN")
        return 1

    exp = create_experiment(base, admin_key)
    variants = tuple(Variant(v["name"], v["weight"]) for v in exp["variants"])
    now = datetime.now(UTC).replace(tzinfo=None)
    exposures, events = simulate(exp["salt"], variants, now, np.random.default_rng(2026))

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        with cur.copy("COPY assignments (experiment_key, user_id, variant, assigned_at) FROM STDIN") as cp:
            for row in exposures:
                cp.write_row(row)
        with cur.copy("COPY events (event_id, user_id, event_name, value, ts) FROM STDIN") as cp:
            for row in events:
                cp.write_row(row)
    log.info("seeded %s: %d users, %d events over %d days", KEY, len(exposures), len(events), DAYS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
