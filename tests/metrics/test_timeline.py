from datetime import timedelta

import pytest

from splitkit.analysis import analyze_experiment, duckdb_fetcher
from splitkit.metrics.compiler import compile_assignment_counts, compile_metric
from splitkit.metrics.spec import MetricSpec, load_metrics
from splitkit.stats.sequential import msprt_from_estimate, msprt_pvalue
from splitkit.timeline import evenly_spaced, experiment_timeline
from tests.fixture_data import T0

REVENUE = MetricSpec.model_validate({"name": "rev", "type": "mean", "event": "purchase", "agg": "sum"})


def test_msprt_from_estimate_matches_per_observation_form():
    diff, var_obs, n, tau2 = 0.3, 2.0, 500, 0.01
    assert msprt_from_estimate(diff, var_obs / n, tau2) == pytest.approx(msprt_pvalue(diff, var_obs, n, tau2))


def test_msprt_from_estimate_validates():
    with pytest.raises(ValueError):
        msprt_from_estimate(0.1, 0.0, 0.01)


def test_as_of_cuts_events_and_exposures(conn):
    cutoff = T0 + timedelta(days=1.5)
    q = compile_metric(REVENUE, "exp1", dialect="duckdb", as_of=cutoff)
    rows = {r[0]: r for r in conn.execute(q.sql, q.params).fetchall()}
    assert rows["control"][2] == 10  # u1's day-2 purchase is after the cutoff
    assert rows["treatment"][2] == 20  # u4 day 1 counts, u5 day 10 doesn't

    early = compile_assignment_counts("exp1", dialect="duckdb", as_of=T0 + timedelta(hours=1))
    assert dict(conn.execute(early.sql, early.params).fetchall()) == {"control": 4, "treatment": 3}
    # before u7's second exposure (day 0.5), u7 still looks like a clean control user


def test_analyze_experiment_as_of(conn):
    report = analyze_experiment(
        duckdb_fetcher(conn), "exp1", (REVENUE,), "control", "treatment",
        as_of=T0 + timedelta(days=1.5),
    )
    assert report.metrics[0].result.mean_b == pytest.approx(20 / 3)


def test_evenly_spaced_points():
    pts = evenly_spaced(T0, T0 + timedelta(days=10), 5)
    assert pts[0] == T0 + timedelta(days=2) and pts[-1] == T0 + timedelta(days=10) and len(pts) == 5
    with pytest.raises(ValueError):
        evenly_spaced(T0, T0, 5)


def test_timeline_always_valid_p_is_monotone(conn):
    points = evenly_spaced(T0, T0 + timedelta(days=12), 6)
    tl = experiment_timeline(duckdb_fetcher(conn), "exp1", REVENUE, "control", "treatment", points)
    assert len(tl) == 6
    avp = [p.always_valid_p for p in tl]
    assert all(b <= a for a, b in zip(avp, avp[1:], strict=False))
    assert all(0 < p.always_valid_p <= 1 for p in tl)
    assert tl[-1].abs_lift == pytest.approx(27 / 3 - 15 / 3)


def test_timeline_skips_points_without_enough_data(conn):
    points = [T0 - timedelta(days=1), T0 + timedelta(days=3)]
    tl = experiment_timeline(duckdb_fetcher(conn), "exp1", REVENUE, "control", "treatment", points)
    assert len(tl) == 1 and tl[0].as_of == points[1]


def test_timeline_supports_proportions(conn):
    rate = load_metrics("metrics:\n  - {name: r, type: proportion, event: purchase}\n")[0]
    tl = experiment_timeline(duckdb_fetcher(conn), "exp1", rate, "control", "treatment",
                             [T0 + timedelta(days=11)])
    assert tl[0].mean_a == pytest.approx(1 / 3)


def _delayed_conversion_db():
    """2,000 users/arm exposed over 10 days; purchases land 0-5 days later, so early
    cutoffs see a depressed baseline. Treatment converts 15% vs 10%."""
    import duckdb
    import numpy as np

    from splitkit.db.schema import create_schema

    rng = np.random.default_rng(7)
    con = duckdb.connect()
    create_schema(con)
    assignments, events = [], []
    for arm, rate in (("control", 0.10), ("treatment", 0.15)):
        for i in range(2000):
            user = f"{arm}-{i}"
            seen = T0 + timedelta(days=float(rng.uniform(0, 10)))
            assignments.append(("delay", user, arm, seen))
            if rng.random() < rate:
                events.append((f"p-{user}", user, "purchase", 1.0, seen + timedelta(days=float(rng.uniform(0, 5)))))
    con.executemany("INSERT INTO assignments VALUES (?, ?, ?, ?)", assignments)
    con.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?)", events)
    return con


def test_default_tau2_is_anchored_on_latest_baseline():
    """Early checkpoints undercount conversions (not enough time has passed), so the
    prior scale must come from the most recent control mean, not the first one."""
    from splitkit.timeline import DEFAULT_RELATIVE_EFFECT

    con = _delayed_conversion_db()
    rate = load_metrics("metrics:\n  - {name: r, type: proportion, event: purchase}\n")[0]
    points = evenly_spaced(T0, T0 + timedelta(days=15), 10)
    fetch = duckdb_fetcher(con)
    default = experiment_timeline(fetch, "delay", rate, "control", "treatment", points)
    assert default[0].mean_a < 0.6 * default[-1].mean_a  # the trap: early baseline is understated

    def run(tau2):
        series = experiment_timeline(fetch, "delay", rate, "control", "treatment", points, tau2=tau2)
        return [p.always_valid_p for p in series]

    latest = run((DEFAULT_RELATIVE_EFFECT * default[-1].mean_a) ** 2)
    first = run((DEFAULT_RELATIVE_EFFECT * default[0].mean_a) ** 2)
    assert [p.always_valid_p for p in default] == latest
    assert latest != first
    assert latest[-1] < 0.05  # a 50% relative lift on 4,000 users should clear the bar
