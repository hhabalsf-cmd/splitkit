import duckdb
import pytest

from splitkit.analysis import analyze_experiment, duckdb_fetcher
from splitkit.datasets.loaders import load_cookie_cats, load_criteo, load_udacity
from splitkit.db.schema import create_schema
from splitkit.metrics.spec import load_metrics


@pytest.fixture
def con():
    c = duckdb.connect()
    create_schema(c)
    yield c
    c.close()


def test_cookie_cats_loader(con, tmp_path):
    csv = tmp_path / "cookie_cats.csv"
    csv.write_text(
        "userid,version,sum_gamerounds,retention_1,retention_7\n"
        "1,gate_30,3,FALSE,FALSE\n2,gate_30,40,TRUE,TRUE\n"
        "3,gate_40,0,FALSE,FALSE\n4,gate_40,12,TRUE,FALSE\n"
    )
    load_cookie_cats(con, csv)
    metrics = load_metrics("metrics:\n  - {name: retention_7, type: proportion, event: active_day_7}\n"
                           "  - {name: rounds, type: mean, event: game_rounds, agg: sum}\n")
    rep = analyze_experiment(duckdb_fetcher(con), "cookie_cats", metrics, "gate_30", "gate_40")
    by = {m.metric: m.result for m in rep.metrics}
    assert by["retention_7"].mean_a == 0.5 and by["retention_7"].mean_b == 0.0
    assert by["rounds"].mean_a == pytest.approx(21.5) and by["rounds"].mean_b == pytest.approx(6.0)


def test_udacity_loader_drops_misrouted_rows_and_multi_arm_users(con, tmp_path):
    csv = tmp_path / "ab_data.csv"
    csv.write_text(
        "user_id,timestamp,group,landing_page,converted\n"
        "1,2017-01-02 10:00:00,control,old_page,0\n"
        "2,2017-01-02 10:00:00,control,old_page,1\n"
        "3,2017-01-02 10:00:00,treatment,new_page,1\n"
        "4,2017-01-02 10:00:00,treatment,new_page,0\n"
        "5,2017-01-02 10:00:00,treatment,old_page,1\n"  # misrouted: dropped
        "6,2017-01-02 10:00:00,control,old_page,0\n"
        "6,2017-01-03 10:00:00,treatment,new_page,1\n"  # both arms: excluded
    )
    load_udacity(con, csv)
    metrics = load_metrics("metrics:\n  - {name: conv, type: proportion, event: converted}\n")
    rep = analyze_experiment(duckdb_fetcher(con), "udacity_landing", metrics, "control", "treatment")
    assert rep.counts == {"control": 2, "treatment": 2}
    assert rep.metrics[0].result.mean_a == 0.5 and rep.metrics[0].result.mean_b == 0.5


def test_criteo_loader(con, tmp_path):
    header = ",".join(f"f{i}" for i in range(12)) + ",treatment,conversion,visit,exposure\n"
    zeros = ",".join("0" for _ in range(12))
    rows = [f"{zeros},{t},{c},{v},0\n" for t, c, v in [(1, 1, 1), (1, 0, 1), (1, 0, 0), (0, 0, 1), (0, 0, 0)]]
    csv = tmp_path / "criteo.csv"
    csv.write_text(header + "".join(rows))
    load_criteo(con, csv)
    metrics = load_metrics("metrics:\n  - {name: visit, type: proportion, event: visit}\n"
                           "  - {name: conversion, type: proportion, event: conversion}\n")
    rep = analyze_experiment(duckdb_fetcher(con), "criteo_uplift", metrics, "control", "treatment",
                             weights=(0.15, 0.85))
    assert rep.counts == {"control": 2, "treatment": 3}
    by = {m.metric: m.result for m in rep.metrics}
    assert by["visit"].mean_b == pytest.approx(2 / 3) and by["conversion"].mean_a == 0.0


def test_loader_rejects_missing_or_non_csv(con, tmp_path):
    with pytest.raises(FileNotFoundError):
        load_cookie_cats(con, tmp_path / "missing.csv")
    bad = tmp_path / "data.txt"
    bad.write_text("x")
    with pytest.raises(ValueError):
        load_cookie_cats(con, bad)
