import pytest

from splitkit.metrics.compiler import compile_assignment_counts, compile_metric
from splitkit.metrics.spec import MetricSpec


def _run(conn, spec, experiment="exp1"):
    q = compile_metric(spec, experiment, dialect="duckdb")
    cols = [
        "variant", "n", "sum_x", "sum_x2", "sum_y", "sum_y2", "sum_xy",
    ]
    rows = conn.execute(q.sql, q.params).fetchall()
    return {r[0]: dict(zip(cols, r, strict=True)) for r in rows}


def test_proportion_with_window(conn):
    spec = MetricSpec.model_validate(
        {"name": "purchase_rate", "type": "proportion", "event": "purchase", "window_days": 7}
    )
    res = _run(conn, spec)
    assert res["control"]["n"] == 3 and res["control"]["sum_x"] == 1  # only u1
    assert res["treatment"]["n"] == 3 and res["treatment"]["sum_x"] == 1  # only u4 (u5 too late)


def test_mean_sum_without_window_includes_late_events(conn):
    spec = MetricSpec.model_validate(
        {"name": "rev", "type": "mean", "event": "purchase", "agg": "sum"}
    )
    res = _run(conn, spec)
    assert res["control"]["sum_x"] == 15 and res["control"]["sum_x2"] == 225
    assert res["treatment"]["sum_x"] == 27 and res["treatment"]["sum_x2"] == 20**2 + 7**2


def test_events_before_assignment_never_count(conn):
    spec = MetricSpec.model_validate({"name": "rev", "type": "mean", "event": "purchase", "agg": "sum"})
    assert _run(conn, spec)["control"]["sum_x"] == 15  # u2's pre-assignment 99 excluded


def test_ratio_metric_moments(conn):
    spec = MetricSpec.model_validate({
        "name": "rev_per_session", "type": "ratio",
        "numerator": {"event": "purchase", "agg": "sum"},
        "denominator": {"event": "session_start", "agg": "count"},
    })
    res = _run(conn, spec)
    c = res["control"]  # u1:(15,2) u2:(0,1) u3:(0,0)
    assert (c["sum_x"], c["sum_y"], c["sum_xy"], c["sum_y2"]) == (15, 3, 30, 5)
    t = res["treatment"]  # u4:(20,1) u5:(7,1) u6:(0,3)
    assert (t["sum_x"], t["sum_y"], t["sum_xy"], t["sum_y2"]) == (27, 5, 27, 11)


def test_multi_variant_user_excluded(conn):
    counts = conn.execute(*_counts_args()).fetchall()
    assert dict(counts) == {"control": 3, "treatment": 3}


def _counts_args():
    q = compile_assignment_counts("exp1", dialect="duckdb")
    return q.sql, q.params


def test_event_names_are_bound_not_interpolated():
    spec = MetricSpec.model_validate({"name": "m", "type": "proportion", "event": "purchase"})
    q = compile_metric(spec, "exp1", dialect="duckdb")
    assert "purchase" not in q.sql and "exp1" not in q.sql
    assert q.params["num_event"] == "purchase" and q.params["experiment_key"] == "exp1"


def test_postgres_dialect_uses_pyformat_placeholders():
    spec = MetricSpec.model_validate({"name": "m", "type": "proportion", "event": "e", "window_days": 3})
    q = compile_metric(spec, "exp1", dialect="postgres")
    assert "%(experiment_key)s" in q.sql and "%(window_days)s" in q.sql
    assert "$" not in q.sql


def test_unknown_dialect_and_bad_experiment_key():
    spec = MetricSpec.model_validate({"name": "m", "type": "proportion", "event": "e"})
    with pytest.raises(ValueError):
        compile_metric(spec, "exp1", dialect="mysql")
    with pytest.raises(ValueError):
        compile_metric(spec, "", dialect="duckdb")
