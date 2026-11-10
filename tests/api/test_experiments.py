import pytest

from tests.api.conftest import experiment_payload


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"success": True, "data": {"status": "ok", "database": "ok"}, "error": None}


def test_create_and_get_experiment(client, admin_headers):
    r = client.post("/v1/experiments", json=experiment_payload(), headers=admin_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True and body["error"] is None
    data = body["data"]
    assert data["key"] == "checkout-v2" and data["status"] == "draft"
    assert len(data["salt"]) >= 16  # random by default so experiments are independent
    assert [m["name"] for m in data["metrics"]] == ["purchase_rate", "revenue"]

    got = client.get("/v1/experiments/checkout-v2", headers=admin_headers).json()["data"]
    assert got == data


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong-key-wrong-key"}])
def test_admin_endpoints_require_key(client, headers):
    assert client.post("/v1/experiments", json=experiment_payload(), headers=headers).status_code == 401
    r = client.get("/v1/experiments/checkout-v2", headers=headers)
    assert r.status_code == 401
    assert r.json() == {"success": False, "data": None, "error": "invalid or missing API key"}


def test_duplicate_key_conflicts(client, admin_headers):
    client.post("/v1/experiments", json=experiment_payload(), headers=admin_headers)
    r = client.post("/v1/experiments", json=experiment_payload(), headers=admin_headers)
    assert r.status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [
        {"key": "Bad Key!"},
        {"variants": [{"name": "control", "weight": 0.5}, {"name": "treatment", "weight": 0.4}]},
        {"variants": [{"name": "a", "weight": 0.5}, {"name": "a", "weight": 0.5}]},
        {"variants": [{"name": "a", "weight": 1.0}]},
        {"metrics": []},
        {"metrics": [{"name": "x", "type": "ratio", "numerator": {"event": "a", "agg": "sum"}}]},
    ],
)
def test_invalid_experiment_rejected_with_envelope(client, admin_headers, overrides):
    r = client.post("/v1/experiments", json=experiment_payload(**overrides), headers=admin_headers)
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False and body["data"] is None and body["error"]


def test_status_transitions(client, admin_headers):
    client.post("/v1/experiments", json=experiment_payload(), headers=admin_headers)
    url = "/v1/experiments/checkout-v2/status"
    assert client.post(url, json={"status": "running"}, headers=admin_headers).status_code == 200
    assert client.post(url, json={"status": "draft"}, headers=admin_headers).status_code == 409
    assert client.post(url, json={"status": "stopped"}, headers=admin_headers).status_code == 200
    assert client.post(url, json={"status": "running"}, headers=admin_headers).status_code == 409


def test_unknown_experiment_404(client, admin_headers):
    assert client.get("/v1/experiments/nope", headers=admin_headers).status_code == 404
    assert client.get("/v1/experiments/nope/config").status_code == 404


def test_public_config_exposes_only_what_sdk_needs(client, running_experiment):
    r = client.get("/v1/experiments/checkout-v2/config")
    assert r.status_code == 200
    assert set(r.json()["data"]) == {"key", "salt", "status", "variants"}
