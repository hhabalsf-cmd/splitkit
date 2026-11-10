"""Endpoints the dashboard needs: experiment list and the sequential timeline."""

from tests.api.conftest import experiment_payload
from tests.api.test_results import _simulate_traffic


def test_list_experiments_newest_first(client, admin_headers):
    for key in ("first-exp", "second-exp"):
        client.post("/v1/experiments", json=experiment_payload(key=key), headers=admin_headers)
    r = client.get("/v1/experiments", headers=admin_headers)
    assert r.status_code == 200
    keys = [e["key"] for e in r.json()["data"]]
    assert keys == ["second-exp", "first-exp"]


def test_list_requires_admin(client):
    assert client.get("/v1/experiments").status_code == 401


def test_timeline(client, admin_headers, running_experiment):
    _simulate_traffic(client, running_experiment)
    r = client.get(
        "/v1/experiments/checkout-v2/timeline",
        params={"metric": "purchase_rate", "points": 5},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["metric"] == "purchase_rate"
    pts = data["points"]
    assert 1 <= len(pts) <= 5
    last = pts[-1]
    assert last["n_control"] + last["n_treatment"] == 400
    assert set(last) >= {"as_of", "abs_lift", "ci_low", "ci_high", "p_value", "always_valid_p"}
    avp = [p["always_valid_p"] for p in pts]
    assert avp == sorted(avp, reverse=True)


def test_timeline_defaults_to_first_metric(client, admin_headers, running_experiment):
    _simulate_traffic(client, running_experiment, n_users=50)
    r = client.get("/v1/experiments/checkout-v2/timeline", headers=admin_headers)
    assert r.status_code == 200 and r.json()["data"]["metric"] == "purchase_rate"


def test_timeline_errors(client, admin_headers, running_experiment):
    url = "/v1/experiments/checkout-v2/timeline"
    assert client.get(url, headers=admin_headers).status_code == 409  # no exposures yet
    r = client.get(url, params={"metric": "nope"}, headers=admin_headers)
    assert r.status_code == 404
    assert client.get(url, params={"points": 500}, headers=admin_headers).status_code == 422


def test_serves_dashboard_when_configured(pg_dsn, pool, tmp_path):
    from fastapi.testclient import TestClient

    from splitkit.api.app import create_app
    from splitkit.api.settings import Settings
    from tests.api.conftest import ADMIN_KEY

    (tmp_path / "index.html").write_text("<!doctype html><title>Splitkit</title>")
    settings = Settings(pg_dsn=pg_dsn, admin_key=ADMIN_KEY, rate_limit_per_min=0, dashboard_dir=str(tmp_path))
    with TestClient(create_app(settings, pool=pool)) as c:
        page = c.get("/dashboard/")
        assert page.status_code == 200 and "Splitkit" in page.text
        root = c.get("/", follow_redirects=False)
        assert root.status_code == 307 and root.headers["location"] == "/dashboard/"
        assert c.get("/dashboard/../pyproject.toml").status_code == 404  # no traversal out of the dir


def test_no_dashboard_routes_when_not_configured(client):
    assert client.get("/dashboard/").status_code == 404


def test_missing_dashboard_dir_fails_fast(pg_dsn, tmp_path):
    import pytest

    from splitkit.api.settings import Settings
    from tests.api.conftest import ADMIN_KEY

    with pytest.raises(ValueError, match="dashboard"):
        Settings(pg_dsn=pg_dsn, admin_key=ADMIN_KEY, dashboard_dir=str(tmp_path / "missing"))
