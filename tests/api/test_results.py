from splitkit.assignment import Variant, assign

AB = (Variant("control", 0.5), Variant("treatment", 0.5))


def _simulate_traffic(client, experiment, n_users=400):
    """Treatment users buy far more often, so the readout must detect it."""
    exposures, events = [], []
    for i in range(n_users):
        user = f"user-{i}"
        variant = assign(AB, experiment["salt"], user)
        exposures.append({"experiment_key": "checkout-v2", "user_id": user, "variant": variant})
        buys = (i % 2 == 0) if variant == "treatment" else (i % 10 == 0)
        if buys:
            events.append({"event_id": f"p-{i}", "user_id": user, "event_name": "purchase", "value": 20.0})
    for start in range(0, len(exposures), 1000):
        client.post("/v1/exposures", json={"exposures": exposures[start:start + 1000]})
    client.post("/v1/events", json={"events": events})


def test_results_readout(client, admin_headers, running_experiment):
    _simulate_traffic(client, running_experiment)
    r = client.get("/v1/experiments/checkout-v2/results", headers=admin_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert sum(data["counts"].values()) == 400
    assert data["srm"]["mismatch"] is False and data["blocked"] is False
    by = {m["metric"]: m for m in data["metrics"]}
    rate = by["purchase_rate"]
    assert rate["mean_b"] > rate["mean_a"]
    assert rate["significant"] is True and rate["adjusted_p"] < 0.05
    assert rate["ci"][0] < rate["abs_lift"] < rate["ci"][1]
    assert "WITH clean_exposure" in rate["sql"]


def test_results_require_admin(client, running_experiment):
    assert client.get("/v1/experiments/checkout-v2/results").status_code == 401


def test_results_without_data_is_conflict(client, admin_headers, running_experiment):
    r = client.get("/v1/experiments/checkout-v2/results", headers=admin_headers)
    assert r.status_code == 409
    assert "not enough" in r.json()["error"]
