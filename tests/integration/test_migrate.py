import os
import uuid

import pytest

from splitkit.db.migrate import main, run

psycopg = pytest.importorskip("psycopg")
pytestmark = pytest.mark.integration

TABLES = {"experiments", "experiment_variants", "assignments", "events"}


@pytest.fixture
def scoped_dsn():
    dsn = os.environ.get("SPLITKIT_PG_DSN")
    if not dsn:
        pytest.skip("SPLITKIT_PG_DSN not set")
    schema = f"test_{uuid.uuid4().hex[:12]}"
    admin = psycopg.connect(dsn, autocommit=True)
    admin.execute(f'CREATE SCHEMA "{schema}"')  # generated name, not user input
    yield dsn, schema
    admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    admin.close()


def _tables(dsn, schema):
    with psycopg.connect(dsn) as c:
        rows = c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (schema,))
        return {r[0] for r in rows}


def test_run_creates_schema_and_is_idempotent(scoped_dsn):
    dsn, schema = scoped_dsn
    run(dsn, search_path=schema)
    run(dsn, search_path=schema)  # second run must be a no-op, not an error
    assert _tables(dsn, schema) >= TABLES


def test_main_requires_dsn(monkeypatch):
    monkeypatch.delenv("SPLITKIT_PG_DSN", raising=False)
    assert main() == 1
