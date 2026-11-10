import pytest
from pydantic import ValidationError

from splitkit.metrics.spec import MetricSpec, load_metrics

YAML = """
metrics:
  - name: purchase_rate
    type: proportion
    event: purchase
    window_days: 7
  - name: revenue_per_user
    type: mean
    event: purchase
    agg: sum
  - name: revenue_per_session
    type: ratio
    numerator: {event: purchase, agg: sum}
    denominator: {event: session_start, agg: count}
"""


def test_loads_all_metric_types():
    metrics = load_metrics(YAML)
    assert [m.name for m in metrics] == ["purchase_rate", "revenue_per_user", "revenue_per_session"]
    assert metrics[0].numerator.agg == "any"
    assert metrics[0].window_days == 7
    assert metrics[2].denominator.event == "session_start"


def test_rejects_sql_injection_in_event_name():
    with pytest.raises(ValidationError):
        MetricSpec.model_validate({"name": "x", "type": "proportion", "event": "a'; DROP TABLE events;--"})


def test_ratio_requires_denominator():
    with pytest.raises(ValidationError):
        MetricSpec.model_validate({"name": "x", "type": "ratio", "numerator": {"event": "a", "agg": "sum"}})


def test_non_ratio_forbids_denominator():
    with pytest.raises(ValidationError):
        MetricSpec.model_validate({
            "name": "x", "type": "mean", "event": "a", "agg": "count",
            "denominator": {"event": "b", "agg": "count"},
        })


def test_proportion_cannot_sum():
    with pytest.raises(ValidationError):
        MetricSpec.model_validate({"name": "x", "type": "proportion", "event": "a", "agg": "sum"})


def test_window_bounds():
    with pytest.raises(ValidationError):
        MetricSpec.model_validate({"name": "x", "type": "proportion", "event": "a", "window_days": 0})


def test_duplicate_names_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        load_metrics("metrics:\n  - {name: a, type: proportion, event: e}\n  - {name: a, type: proportion, event: e}\n")


def test_rejects_non_mapping_yaml():
    with pytest.raises(ValueError):
        load_metrics("- just\n- a list\n")


def test_spec_is_frozen():
    m = load_metrics(YAML)[0]
    with pytest.raises(ValidationError):
        m.name = "other"
