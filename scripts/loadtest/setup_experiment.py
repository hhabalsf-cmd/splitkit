"""Create (or reuse) a running experiment for the load test. Reads admin key from env."""

import os
import sys

import httpx

BASE = os.environ.get("SPLITKIT_URL", "http://127.0.0.1:8000")
KEY = os.environ.get("SPLITKIT_LOADTEST_EXPERIMENT", "loadtest")


def main() -> int:
    headers = {"X-API-Key": os.environ["SPLITKIT_ADMIN_KEY"]}
    payload = {
        "key": KEY,
        "variants": [{"name": "control", "weight": 0.5}, {"name": "treatment", "weight": 0.5}],
        "metrics": [{"name": "purchase_rate", "type": "proportion", "event": "purchase"}],
    }
    r = httpx.post(f"{BASE}/v1/experiments", json=payload, headers=headers)
    if r.status_code not in (201, 409):
        sys.stderr.write(f"create failed: {r.status_code} {r.text}\n")
        return 1
    r = httpx.post(f"{BASE}/v1/experiments/{KEY}/status", json={"status": "running"}, headers=headers)
    if r.status_code not in (200, 409):
        sys.stderr.write(f"start failed: {r.status_code} {r.text}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
