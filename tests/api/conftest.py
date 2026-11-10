"""API tests run against real Postgres in a throwaway schema per test.

Requires SPLITKIT_PG_DSN; skipped otherwise. The admin key is generated per
run, never hardcoded.
"""

import os
import secrets
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
from fastapi.testclient import TestClient  # noqa: E402
from psycopg_pool import ConnectionPool  # noqa: E402

from splitkit.api.app import create_app  # noqa: E402
from splitkit.api.settings import Settings  # noqa: E402
from splitkit.db.schema import create_schema  # noqa: E402

ADMIN_KEY = secrets.token_urlsafe(24)

METRICS = [
    {"name": "purchase_rate", "type": "proportion", "event": "purchase"},
    {"name": "revenue", "type": "mean", "event": "purchase", "agg": "sum"},
]


def experiment_payload(key="checkout-v2", **overrides):
    return {
        "key": key,
        "variants": [{"name": "control", "weight": 0.5}, {"name": "treatment", "weight": 0.5}],
        "metrics": METRICS,
        **overrides,
    }


@pytest.fixture
def pg_dsn():
    dsn = os.environ.get("SPLITKIT_PG_DSN")
    if not dsn:
        pytest.skip("SPLITKIT_PG_DSN not set")
    return dsn


@pytest.fixture
def pool(pg_dsn):
    schema = f"test_{uuid.uuid4().hex[:12]}"
    try:
        admin = psycopg.connect(pg_dsn, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres unreachable: {exc}")
    admin.execute(f'CREATE SCHEMA "{schema}"')  # generated name, not user input
    p = ConnectionPool(
        pg_dsn, min_size=1, max_size=4, open=True,
        kwargs={"autocommit": True, "options": f"-c search_path={schema}"},
    )
    with p.connection() as conn:
        create_schema(conn)
    yield p
    p.close()
    admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    admin.close()


@pytest.fixture
def settings(pg_dsn):
    return Settings(pg_dsn=pg_dsn, admin_key=ADMIN_KEY, rate_limit_per_min=0)


@pytest.fixture
def client(settings, pool):
    with TestClient(create_app(settings, pool=pool)) as c:
        yield c


@pytest.fixture
def admin_headers():
    return {"X-API-Key": ADMIN_KEY}


@pytest.fixture
def running_experiment(client, admin_headers):
    r = client.post("/v1/experiments", json=experiment_payload(), headers=admin_headers)
    assert r.status_code == 201, r.text
    r = client.post("/v1/experiments/checkout-v2/status", json={"status": "running"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]
