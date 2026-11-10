"""All SQL the service runs, behind one repository. Every value is a bound parameter."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import errors
from psycopg_pool import ConnectionPool

from splitkit.analysis import ExperimentAnalysis, analyze_experiment, postgres_fetcher
from splitkit.assignment import Variant
from splitkit.metrics.spec import MetricSpec

# status -> statuses it may move to
TRANSITIONS: dict[str, tuple[str, ...]] = {"draft": ("running", "stopped"), "running": ("stopped",), "stopped": ()}


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


@dataclass(frozen=True)
class ExperimentRecord:
    key: str
    salt: str
    status: str
    variants: tuple[Variant, ...]
    metrics: tuple[MetricSpec, ...]
    created_at: datetime

    def config(self) -> dict[str, Any]:
        """Public view for SDKs: just enough to assign locally."""
        return {
            "key": self.key,
            "salt": self.salt,
            "status": self.status,
            "variants": [{"name": v.name, "weight": v.weight} for v in self.variants],
        }

    def admin_view(self) -> dict[str, Any]:
        return {
            **self.config(),
            "metrics": [m.model_dump(mode="json") for m in self.metrics],
            "created_at": self.created_at.isoformat(),
        }


_SELECT_EXPERIMENTS = """
    SELECT e.experiment_key, e.salt, e.status, e.metrics_json, e.created_at,
           v.variant, v.weight
    FROM experiments e
    JOIN experiment_variants v ON v.experiment_key = e.experiment_key
    WHERE e.experiment_key = ANY(%(keys)s)
    ORDER BY e.experiment_key, v.position
"""


def _records(rows: Sequence[tuple]) -> dict[str, ExperimentRecord]:
    grouped: dict[str, list[tuple]] = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(row)
    return {
        key: ExperimentRecord(
            key=key,
            salt=rs[0][1],
            status=rs[0][2],
            variants=tuple(Variant(r[5], float(r[6])) for r in rs),
            metrics=tuple(MetricSpec.model_validate(m) for m in json.loads(rs[0][3])),
            created_at=rs[0][4],
        )
        for key, rs in grouped.items()
    }


class ExperimentRepository:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def ping(self) -> None:
        with self._pool.connection() as conn:
            conn.execute("SELECT 1")

    def create(self, key: str, salt: str, variants: Sequence[Variant], metrics: Sequence[MetricSpec]) -> ExperimentRecord:
        metrics_json = json.dumps([m.model_dump(mode="json") for m in metrics])
        try:
            with self._pool.connection() as conn, conn.transaction():
                conn.execute(
                    "INSERT INTO experiments (experiment_key, salt, metrics_json) VALUES (%s, %s, %s)",
                    (key, salt, metrics_json),
                )
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO experiment_variants (experiment_key, variant, weight, position) "
                        "VALUES (%s, %s, %s, %s)",
                        [(key, v.name, v.weight, i) for i, v in enumerate(variants)],
                    )
        except errors.UniqueViolation as exc:
            raise ConflictError(f"experiment '{key}' already exists") from exc
        return self.get_required(key)

    def get_many(self, keys: Sequence[str]) -> dict[str, ExperimentRecord]:
        with self._pool.connection() as conn:
            return _records(conn.execute(_SELECT_EXPERIMENTS, {"keys": list(set(keys))}).fetchall())

    def get(self, key: str) -> ExperimentRecord | None:
        return self.get_many([key]).get(key)

    def get_required(self, key: str) -> ExperimentRecord:
        record = self.get(key)
        if record is None:
            raise NotFoundError(f"experiment '{key}' not found")
        return record

    def set_status(self, key: str, status: str) -> ExperimentRecord:
        allowed_from = [s for s, targets in TRANSITIONS.items() if status in targets]
        with self._pool.connection() as conn:
            updated = conn.execute(
                "UPDATE experiments SET status = %s WHERE experiment_key = %s AND status = ANY(%s) "
                "RETURNING experiment_key",
                (status, key, allowed_from),
            ).fetchone()
        if updated is None:
            current = self.get_required(key)  # raises NotFoundError if missing
            raise ConflictError(f"cannot move experiment from '{current.status}' to '{status}'")
        return self.get_required(key)

    def insert_exposures(self, rows: Sequence[tuple[str, str, str]]) -> int:
        """rows: (experiment_key, user_id, variant). Returns newly inserted count."""
        if not rows:
            return 0
        keys, users, variants = (list(col) for col in zip(*rows))
        with self._pool.connection() as conn:
            inserted = conn.execute(
                """
                INSERT INTO assignments (experiment_key, user_id, variant, assigned_at)
                SELECT k, u, v, (now() AT TIME ZONE 'UTC')
                FROM unnest(%s::varchar[], %s::varchar[], %s::varchar[]) AS t(k, u, v)
                ON CONFLICT DO NOTHING
                RETURNING 1
                """,
                (keys, users, variants),
            ).fetchall()
        return len(inserted)

    def insert_events(self, rows: Sequence[tuple[str, str, str, float | None, datetime | None]]) -> int:
        """rows: (event_id, user_id, event_name, value, ts or None for server time)."""
        ids, users, names, values, stamps = (list(col) for col in zip(*rows))
        with self._pool.connection() as conn:
            inserted = conn.execute(
                """
                INSERT INTO events (event_id, user_id, event_name, value, ts)
                SELECT i, u, n, v, COALESCE(t, now() AT TIME ZONE 'UTC')
                FROM unnest(%s::varchar[], %s::varchar[], %s::varchar[], %s::float8[], %s::timestamp[])
                     AS x(i, u, n, v, t)
                ON CONFLICT (event_id) DO NOTHING
                RETURNING 1
                """,
                (ids, users, names, values, stamps),
            ).fetchall()
        return len(inserted)

    def analyze(self, record: ExperimentRecord, alpha: float) -> ExperimentAnalysis:
        control, treatment = record.variants[0], record.variants[1]
        with self._pool.connection() as conn:
            return analyze_experiment(
                postgres_fetcher(conn), record.key, record.metrics,
                control.name, treatment.name,
                weights=(control.weight, treatment.weight), alpha=alpha, dialect="postgres",
            )
