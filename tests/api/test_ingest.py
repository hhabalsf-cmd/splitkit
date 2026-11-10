from datetime import datetime, timedelta, timezone

from splitkit.assignment import Variant, assign

AB = (Variant("control", 0.5), Variant("treatment", 0.5))


def _variant_for(experiment, user):
    return assign(AB, experiment["salt"], user)


def test_assign_is_deterministic_and_records_one_exposure(client, running_experiment):
    body = {"experiment_key": "checkout-v2", "user_id": "user-1"}
    first = client.post("/v1/assign", json=body).json()["data"]
    second = client.post("/v1/assign", json=body).json()["data"]
    assert first["variant"] == second["variant"] == _variant_for(running_experiment, "user-1")
    assert first["new_exposure"] is True and second["new_exposure"] is False


def test_assign_returns_null_variant_when_not_running(client, admin_headers):
    from tests.api.conftest import experiment_payload

    client.post("/v1/experiments", json=experiment_payload(), headers=admin_headers)
    r = client.post("/v1/assign", json={"experiment_key": "checkout-v2", "user_id": "u"})
    assert r.status_code == 200 and r.json()["data"]["variant"] is None


def test_exposures_verified_against_hash(client, running_experiment):
    right = _variant_for(running_experiment, "u1")
    wrong = "treatment" if right == "control" else "control"
    r = client.post("/v1/exposures", json={"exposures": [
        {"experiment_key": "checkout-v2", "user_id": "u1", "variant": right},
        {"experiment_key": "checkout-v2", "user_id": "u2", "variant": wrong if _variant_for(running_experiment, "u2") == right else right},
        {"experiment_key": "checkout-v2", "user_id": "u1", "variant": right},
        {"experiment_key": "missing-exp", "user_id": "u3", "variant": "control"},
    ]})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["accepted"] == 1  # u1 once
    assert data["duplicates"] == 1  # u1 repeated
    assert data["rejected"] == 2  # u2 wrong arm, unknown experiment


def test_events_are_idempotent_by_event_id(client, running_experiment):
    events = [
        {"event_id": "e1", "user_id": "u1", "event_name": "purchase", "value": 10.0},
        {"event_id": "e2", "user_id": "u1", "event_name": "page_view"},
    ]
    first = client.post("/v1/events", json={"events": events}).json()["data"]
    retry = client.post("/v1/events", json={"events": events}).json()["data"]
    assert first == {"accepted": 2, "duplicates": 0}
    assert retry == {"accepted": 0, "duplicates": 2}


def test_event_validation(client):
    now = datetime.now(timezone.utc)
    bad = [
        {"event_id": "e1", "user_id": "u", "event_name": "Bad Name"},
        {"event_id": "e1", "user_id": "", "event_name": "ok"},
        {"event_id": "e1", "user_id": "u", "event_name": "ok", "ts": (now + timedelta(hours=1)).isoformat()},
        {"event_id": "e1", "user_id": "u", "event_name": "ok", "ts": (now - timedelta(days=30)).isoformat()},
        {"event_id": "bad id!", "user_id": "u", "event_name": "ok"},
    ]
    for event in bad:
        r = client.post("/v1/events", json={"events": [event]})
        assert r.status_code == 422, event
    assert client.post("/v1/events", json={"events": []}).status_code == 422
    too_many = [{"event_id": f"e{i}", "user_id": "u", "event_name": "ok"} for i in range(1001)]
    assert client.post("/v1/events", json={"events": too_many}).status_code == 422


def test_non_finite_value_rejected(client):
    r = client.post(
        "/v1/events",
        content='{"events":[{"event_id":"e1","user_id":"u","event_name":"ok","value":NaN}]}',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422
