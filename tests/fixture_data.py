"""Tiny hand-built experiment whose metric values can be checked by hand.

Shared by the DuckDB unit tests and the Postgres integration tests so both
engines see identical rows.

exp1, all assigned 2024-01-01 00:00:
  control:   u1, u2, u3
  treatment: u4, u5, u6
  u7 appears in BOTH arms -> must be excluded from analysis

purchases (value):
  u1: 10 @ day0, 5 @ day2           -> in window
  u2: 99 @ day -1                   -> before assignment, excluded
  u4: 20 @ day1                     -> in window
  u5: 7  @ day10                    -> outside a 7-day window
  u7: 50 @ day1                     -> contaminated user, excluded
session_start (count):
  u1 x2, u2 x1, u4 x1, u5 x1, u6 x3
"""

from datetime import datetime, timedelta

T0 = datetime(2024, 1, 1)


def _day(d: float) -> datetime:
    return T0 + timedelta(days=d)


def _assignments() -> tuple[tuple, ...]:
    rows = [("exp1", u, "control", T0) for u in ("u1", "u2", "u3")]
    rows += [("exp1", u, "treatment", T0) for u in ("u4", "u5", "u6")]
    rows += [("exp1", "u7", "control", T0), ("exp1", "u7", "treatment", _day(0.5))]
    rows += [("other_exp", "u1", "treatment", T0)]
    return tuple(rows)


def _events() -> tuple[tuple, ...]:
    rows = [
        ("p1", "u1", "purchase", 10.0, _day(0)),
        ("p2", "u1", "purchase", 5.0, _day(2)),
        ("p3", "u2", "purchase", 99.0, _day(-1)),
        ("p4", "u4", "purchase", 20.0, _day(1)),
        ("p5", "u5", "purchase", 7.0, _day(10)),
        ("p6", "u7", "purchase", 50.0, _day(1)),
    ]
    sessions = {"u1": 2, "u2": 1, "u4": 1, "u5": 1, "u6": 3}
    for user, k in sessions.items():
        rows += [(f"s-{user}-{i}", user, "session_start", None, _day(0.1 * (i + 1))) for i in range(k)]
    return tuple(rows)


ASSIGNMENTS = _assignments()
EVENTS = _events()
