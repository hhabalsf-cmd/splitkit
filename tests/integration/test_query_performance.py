"""Regression test: metric SQL must stay fast when planner statistics are stale.

Freshly loaded tables (bulk import, new experiment) have no statistics, so
Postgres may estimate one row where there are thousands. An earlier query
shape joined two per-user aggregates and, under that misestimate, recomputed
one of them for every user: 62 s for 20k users. The single-pass shape must
stay well under a second even without ANALYZE.
"""

import os
import time
import uuid
from datetime import datetime, timedelta

import pytest

from splitkit.analysis import analyze_experiment, postgres_fetcher
from splitkit.db.schema import create_schema
from splitkit.metrics.spec import load_metrics

psycopg = pytest.importorskip("psycopg")
pytestmark = pytest.mark.integration

USERS = 8000
BUDGET_S = 3.0
T0 = datetime(2024, 1, 1)

METRICS = load_metrics("""
metrics:
  - {name: purchase_rate, type: proportion, event: purchase, window_days: 7}
  - {name: revenue, type: mean, event: purchase, agg: sum, window_days: 7}
  - name: rev_per_session
    type: ratio
    window_days: 7
    numerator: {event: purchase, agg: sum}
    denominator: {event: session_start, agg: count}
""")


@pytest.fixture
def stale_stats_conn():
    dsn = os.environ.get("SPLITKIT_PG_DSN")
    if not dsn:
        pytest.skip("SPLITKIT_PG_DSN not set")
    schema = f"test_{uuid.uuid4().hex[:12]}"
    admin = psycopg.connect(dsn, autocommit=True)
    admin.execute(f'CREATE SCHEMA "{schema}"')  # generated name, not user input
    conn = psycopg.connect(dsn, autocommit=True, options=f"-c search_path={schema}")
    create_schema(conn)
    # keep autovacuum from analyzing mid-test so statistics stay stale
    for table in ("assignments", "events"):
        conn.execute(f"ALTER TABLE {table} SET (autovacuum_enabled = false)")  # fixed names
    with conn.cursor() as cur:
        with cur.copy("COPY assignments FROM STDIN") as cp:
            for i in range(USERS):
                cp.write_row(("perf", f"u{i}", "control" if i % 2 else "treatment", T0))
        with cur.copy("COPY events FROM STDIN") as cp:
            for i in range(USERS):
                for s in range(3):
                    cp.write_row((f"s{i}-{s}", f"u{i}", "session_start", None, T0 + timedelta(hours=s + 1)))
                if i % 7 == 0:
                    cp.write_row((f"p{i}", f"u{i}", "purchase", 20.0, T0 + timedelta(hours=5)))
    yield conn
    conn.close()
    admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    admin.close()


def test_readout_fast_without_statistics(stale_stats_conn):
    start = time.perf_counter()
    report = analyze_experiment(
        postgres_fetcher(stale_stats_conn), "perf", METRICS, "control", "treatment", dialect="postgres"
    )
    elapsed = time.perf_counter() - start
    assert sum(report.counts.values()) == USERS
    ratio = next(m for m in report.metrics if m.metric == "rev_per_session")
    assert ratio.result.mean_a > 0
    assert elapsed < BUDGET_S, f"readout took {elapsed:.1f}s with stale statistics"
