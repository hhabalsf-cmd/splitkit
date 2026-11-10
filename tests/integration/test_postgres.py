"""Postgres integration: the compiled SQL must give identical results on both engines.

Requires SPLITKIT_PG_DSN (e.g. from infra/docker-compose.yml); skipped otherwise.
Each test runs in its own throwaway schema so nothing touches other data.
"""

import os
import uuid

import duckdb
import pytest

from splitkit.analysis import analyze_experiment, duckdb_fetcher, postgres_fetcher
from splitkit.db.schema import create_schema
from splitkit.metrics.compiler import compile_assignment_counts, compile_metric
from splitkit.metrics.spec import load_metrics
from tests.fixture_data import ASSIGNMENTS, EVENTS

psycopg = pytest.importorskip("psycopg")
pytestmark = pytest.mark.integration

METRICS = load_metrics("""
metrics:
  - {name: purchase_any, type: proportion, event: purchase}
  - {name: purchase_7d, type: proportion, event: purchase, window_days: 7}
  - {name: revenue, type: mean, event: purchase, agg: sum}
  - {name: revenue_7d, type: mean, event: purchase, agg: sum, window_days: 7}
  - {name: sessions, type: mean, event: session_start, agg: count}
  - name: rev_per_session
    type: ratio
    numerator: {event: purchase, agg: sum}
    denominator: {event: session_start, agg: count}
  - name: rev_per_session_7d
    type: ratio
    numerator: {event: purchase, agg: sum}
    denominator: {event: session_start, agg: count}
    window_days: 7
""")


@pytest.fixture
def pg():
    dsn = os.environ.get("SPLITKIT_PG_DSN")
    if not dsn:
        pytest.skip("SPLITKIT_PG_DSN not set")
    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres unreachable: {exc}")
    schema = f"test_{uuid.uuid4().hex[:12]}"
    conn.execute(f'CREATE SCHEMA "{schema}"')  # generated name, not user input
    conn.execute(f'SET search_path TO "{schema}"')
    create_schema(conn)
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO assignments VALUES (%s, %s, %s, %s)", ASSIGNMENTS)
        cur.executemany("INSERT INTO events VALUES (%s, %s, %s, %s, %s)", EVENTS)
    yield conn
    conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
    conn.close()


@pytest.fixture
def duck():
    con = duckdb.connect()
    create_schema(con)
    con.executemany("INSERT INTO assignments VALUES (?, ?, ?, ?)", ASSIGNMENTS)
    con.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?)", EVENTS)
    yield con
    con.close()


def _normalize(rows):
    return [tuple(None if v is None else (str(v) if i == 0 else float(v)) for i, v in enumerate(r)) for r in rows]


@pytest.mark.parametrize("spec", METRICS, ids=[m.name for m in METRICS])
def test_metric_sql_matches_duckdb(pg, duck, spec):
    pq = compile_metric(spec, "exp1", dialect="postgres")
    dq = compile_metric(spec, "exp1", dialect="duckdb")
    pg_rows = _normalize(pg.execute(pq.sql, pq.params).fetchall())
    duck_rows = _normalize(duck.execute(dq.sql, dq.params).fetchall())
    assert pg_rows == duck_rows
    assert len(pg_rows) == 2


def test_assignment_counts_match(pg, duck):
    pq = compile_assignment_counts("exp1", dialect="postgres")
    dq = compile_assignment_counts("exp1", dialect="duckdb")
    assert dict(pg.execute(pq.sql, pq.params).fetchall()) == dict(duck.execute(dq.sql, dq.params).fetchall())


def test_full_readout_identical_on_both_engines(pg, duck):
    pg_rep = analyze_experiment(postgres_fetcher(pg), "exp1", METRICS, "control", "treatment", dialect="postgres")
    duck_rep = analyze_experiment(duckdb_fetcher(duck), "exp1", METRICS, "control", "treatment", dialect="duckdb")
    assert pg_rep.counts == duck_rep.counts == {"control": 3, "treatment": 3}
    for p, d in zip(pg_rep.metrics, duck_rep.metrics):
        assert p.result.p_value == pytest.approx(d.result.p_value)
        assert p.result.abs_lift == pytest.approx(d.result.abs_lift)


def test_hostile_event_name_is_inert_data(pg):
    """Even if validation were bypassed, bound parameters keep SQL text out of the query."""
    hostile = "x'); DROP TABLE events; --"
    spec = METRICS[0].model_copy(update={"numerator": METRICS[0].numerator.model_copy(update={"event": hostile})})
    q = compile_metric(spec, "exp1", dialect="postgres")
    pg.execute(q.sql, q.params).fetchall()
    assert pg.execute("SELECT COUNT(*) FROM events").fetchone()[0] == len(EVENTS)
