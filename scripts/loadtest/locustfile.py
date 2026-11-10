"""Simulated SDK traffic: config fetches, batched exposures and batched events.

    locust -f scripts/loadtest/locustfile.py --host http://127.0.0.1:8000
"""

import os
import uuid

from locust import FastHttpUser, between, task

from splitkit.assignment import Variant, assign

EXPERIMENT = os.environ.get("SPLITKIT_LOADTEST_EXPERIMENT", "loadtest")
EVENT_BATCH = 50
EXPOSURE_BATCH = 20


class SdkClient(FastHttpUser):
    wait_time = between(0.0, 0.05)

    def on_start(self) -> None:
        cfg = self.client.get(f"/v1/experiments/{EXPERIMENT}/config").json()["data"]
        self.salt = cfg["salt"]
        self.variants = tuple(Variant(v["name"], v["weight"]) for v in cfg["variants"])

    def _user(self) -> str:
        return f"lt-{uuid.uuid4().hex[:16]}"

    @task(3)
    def config(self) -> None:
        self.client.get(f"/v1/experiments/{EXPERIMENT}/config", name="GET /config")

    @task(2)
    def exposures(self) -> None:
        batch = []
        for _ in range(EXPOSURE_BATCH):
            user = self._user()
            batch.append({"experiment_key": EXPERIMENT, "user_id": user,
                          "variant": assign(self.variants, self.salt, user)})
        self.client.post("/v1/exposures", json={"exposures": batch}, name="POST /exposures x20")

    @task(5)
    def events(self) -> None:
        batch = [{"event_id": uuid.uuid4().hex, "user_id": self._user(),
                  "event_name": "purchase", "value": 9.99} for _ in range(EVENT_BATCH)]
        self.client.post("/v1/events", json={"events": batch}, name="POST /events x50")

    @task(1)
    def assign_user(self) -> None:
        self.client.post("/v1/assign", json={"experiment_key": EXPERIMENT, "user_id": self._user()},
                         name="POST /assign")
