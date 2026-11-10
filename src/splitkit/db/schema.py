"""Portable DDL (runs unchanged on DuckDB and PostgreSQL).

Timestamps are stored as TIMESTAMP in UTC by convention.
assignments' primary key includes variant on purpose: imported datasets can
contain users exposed to more than one arm, and the metric layer must be able
to see (and exclude) them rather than have the insert silently fail.
"""

from __future__ import annotations

from typing import Protocol

DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS experiments (
        experiment_key VARCHAR(64) PRIMARY KEY,
        salt           VARCHAR(64) NOT NULL,
        status         VARCHAR(16) NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft', 'running', 'stopped')),
        metrics_json   TEXT        NOT NULL DEFAULT '[]',
        created_at     TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # position fixes variant order: assignment walks cumulative weights in this order
    """
    CREATE TABLE IF NOT EXISTS experiment_variants (
        experiment_key VARCHAR(64)      NOT NULL REFERENCES experiments (experiment_key),
        variant        VARCHAR(32)      NOT NULL,
        weight         DOUBLE PRECISION NOT NULL CHECK (weight > 0 AND weight <= 1),
        position       SMALLINT         NOT NULL,
        PRIMARY KEY (experiment_key, variant),
        UNIQUE (experiment_key, position)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assignments (
        experiment_key VARCHAR(64)  NOT NULL,
        user_id        VARCHAR(128) NOT NULL,
        variant        VARCHAR(32)  NOT NULL,
        assigned_at    TIMESTAMP    NOT NULL,
        PRIMARY KEY (experiment_key, user_id, variant)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id   VARCHAR(64)  PRIMARY KEY,
        user_id    VARCHAR(128) NOT NULL,
        event_name VARCHAR(64)  NOT NULL,
        value      DOUBLE PRECISION,
        ts         TIMESTAMP    NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS events_user_name_ts ON events (user_id, event_name, ts)",
)


class Executor(Protocol):
    def execute(self, sql: str, *args: object) -> object: ...


def create_schema(conn: Executor) -> None:
    for statement in DDL:
        conn.execute(statement)
