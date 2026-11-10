import pytest

from splitkit.analysis import analyze_experiment, duckdb_fetcher
from splitkit.metrics.spec import load_metrics

METRICS = load_metrics("""
metrics:
  - {name: purchase_rate, type: proportion, event: purchase, window_days: 7}
  - {name: revenue, type: mean, event: purchase, agg: sum}
  - name: rev_per_session
    type: ratio
    numerator: {event: purchase, agg: sum}
    denominator: {event: session_start, agg: count}
""")


def test_end_to_end_on_fixture(conn):
    report = analyze_experiment(duckdb_fetcher(conn), "exp1", METRICS, "control", "treatment")
    assert report.counts == {"control": 3, "treatment": 3}
    assert report.blocked is False
    by_name = {m.metric: m for m in report.metrics}
    assert by_name["purchase_rate"].result.mean_a == pytest.approx(1 / 3)
    assert by_name["revenue"].result.mean_b == pytest.approx(9.0)
    assert by_name["rev_per_session"].result.mean_a == pytest.approx(5.0)
    assert by_name["rev_per_session"].result.mean_b == pytest.approx(27 / 5)
    assert all(m.adjusted_p >= m.result.p_value for m in report.metrics)
    assert "WITH clean_exposure" in by_name["revenue"].sql


def test_srm_failure_blocks_results(conn):
    report = analyze_experiment(
        duckdb_fetcher(conn), "exp1", METRICS, "control", "treatment",
        weights=(0.9, 0.1), srm_threshold=0.5,  # planned 90/10, observed 50/50
    )
    assert report.blocked is True
    assert all(m.significant is False for m in report.metrics)


def test_unknown_variant_raises(conn):
    with pytest.raises(ValueError, match="variant"):
        analyze_experiment(duckdb_fetcher(conn), "exp1", METRICS, "control", "nope")


def test_weights_must_match_variants(conn):
    with pytest.raises(ValueError):
        analyze_experiment(duckdb_fetcher(conn), "exp1", METRICS, "control", "treatment", weights=(1.0,))
