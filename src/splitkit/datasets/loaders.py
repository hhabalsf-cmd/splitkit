"""Import public A/B datasets into the assignments/events schema (DuckDB).

Each loader maps a flat CSV onto exposure + event rows so every dataset is
analyzed by the same metric layer as live traffic. Datasets without
timestamps get synthetic ones relative to a fixed exposure time T0.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

T0 = "2024-01-01 00:00:00"


def _csv(path: str | Path) -> str:
    p = Path(path).expanduser().resolve()
    if p.suffix.lower() != ".csv":
        raise ValueError(f"expected a .csv file, got {p.name}")
    if not p.is_file():
        raise FileNotFoundError(p)
    return str(p)


def load_cookie_cats(conn: Any, path: str | Path) -> None:
    """gate_30 vs gate_40. Events: active_day_1/active_day_7 retention, game_rounds total."""
    params = {"path": _csv(path), "t0": T0}
    conn.execute("""
        INSERT INTO assignments
        SELECT 'cookie_cats', CAST(userid AS VARCHAR), version, CAST($t0 AS TIMESTAMP)
        FROM read_csv($path, header = true)
    """, params)
    conn.execute("""
        INSERT INTO events
        SELECT 'cc-r1-' || userid, CAST(userid AS VARCHAR), 'active_day_1', NULL,
               CAST($t0 AS TIMESTAMP) + INTERVAL '1 day'
        FROM read_csv($path, header = true) WHERE retention_1
        UNION ALL
        SELECT 'cc-r7-' || userid, CAST(userid AS VARCHAR), 'active_day_7', NULL,
               CAST($t0 AS TIMESTAMP) + INTERVAL '7 days'
        FROM read_csv($path, header = true) WHERE retention_7
        UNION ALL
        SELECT 'cc-gr-' || userid, CAST(userid AS VARCHAR), 'game_rounds', sum_gamerounds,
               CAST($t0 AS TIMESTAMP)
        FROM read_csv($path, header = true) WHERE sum_gamerounds > 0
    """, params)


def load_udacity(conn: Any, path: str | Path) -> None:
    """Landing-page test. Rows whose group and landing_page disagree are logging
    errors (user saw the wrong page) and are dropped; users appearing in both
    arms are kept so the metric layer's multi-arm exclusion handles them."""
    params = {"path": _csv(path)}
    valid = """
        SELECT row_number() OVER () AS rid, CAST(user_id AS VARCHAR) AS uid,
               "group" AS grp, CAST("timestamp" AS TIMESTAMP) AS ts, converted
        FROM read_csv($path, header = true)
        WHERE ("group" = 'treatment') = (landing_page = 'new_page')
    """
    conn.execute(f"""
        INSERT INTO assignments
        SELECT 'udacity_landing', uid, grp, MIN(ts) FROM ({valid}) v GROUP BY uid, grp
    """, params)
    conn.execute(f"""
        INSERT INTO events
        SELECT 'ud-' || rid, uid, 'converted', NULL, ts FROM ({valid}) v WHERE converted = 1
    """, params)


def load_criteo(conn: Any, path: str | Path) -> None:
    """Criteo uplift v2.1 (~14M rows, 85/15 treatment split). Row number is the user id."""
    conn.execute("""
        CREATE TEMP TABLE criteo_raw AS
        SELECT CAST(row_number() OVER () AS VARCHAR) AS uid, treatment, visit, conversion
        FROM read_csv($path, header = true)
    """, {"path": _csv(path)})
    try:
        conn.execute("""
            INSERT INTO assignments
            SELECT 'criteo_uplift', uid,
                   CASE WHEN treatment = 1 THEN 'treatment' ELSE 'control' END,
                   CAST($t0 AS TIMESTAMP)
            FROM criteo_raw
        """, {"t0": T0})
        conn.execute("""
            INSERT INTO events
            SELECT 'cr-v-' || uid, uid, 'visit', NULL, CAST($t0 AS TIMESTAMP) + INTERVAL '1 hour'
            FROM criteo_raw WHERE visit = 1
            UNION ALL
            SELECT 'cr-c-' || uid, uid, 'conversion', NULL, CAST($t0 AS TIMESTAMP) + INTERVAL '2 hours'
            FROM criteo_raw WHERE conversion = 1
        """, {"t0": T0})
    finally:
        conn.execute("DROP TABLE IF EXISTS criteo_raw")
