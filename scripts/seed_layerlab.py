"""Create the LayerLab home-page experiment through the API (W5 live experiment).

Control shows the curated suggestion chips below the pickers (today's page); treatment
shows them above. Primary metric: did the visitor reach a layering verdict.

The experiment is created in `draft`, so nothing is assigned until you start it:

    SPLITKIT_URL=https://<cloudfront-domain> SPLITKIT_ADMIN_KEY=... python scripts/seed_layerlab.py
    SPLITKIT_URL=... SPLITKIT_ADMIN_KEY=... python scripts/seed_layerlab.py --start
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import httpx

log = logging.getLogger("seed_layerlab")

KEY = "home-suggestions-position"  # must match src/lib/experiment.ts in LayerLab
METRICS = [
    {"name": "verdict_rate", "type": "proportion", "event": "verdict_viewed", "window_days": 1,
     "description": "Reached a layering verdict within a day of first seeing the home page"},
    {"name": "suggestion_click_rate", "type": "proportion", "event": "suggestion_clicked",
     "window_days": 1, "description": "Clicked a curated suggestion chip"},
]


def build_payload() -> dict:
    return {
        "key": KEY,
        "variants": [{"name": "control", "weight": 0.5}, {"name": "treatment", "weight": 0.5}],
        "metrics": METRICS,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", action="store_true", help="set an existing experiment to running")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    base = os.environ.get("SPLITKIT_URL", "").rstrip("/")
    admin_key = os.environ.get("SPLITKIT_ADMIN_KEY", "")
    if not base.startswith(("http://", "https://")) or len(admin_key) < 16:
        log.error("set SPLITKIT_URL (http/https) and SPLITKIT_ADMIN_KEY (16+ chars)")
        return 2

    headers = {"X-API-Key": admin_key}
    with httpx.Client(base_url=base, headers=headers, timeout=10) as client:
        if args.start:
            client.post(f"/v1/experiments/{KEY}/status", json={"status": "running"}).raise_for_status()
            log.info("'%s' is running", KEY)
            return 0
        r = client.post("/v1/experiments", json=build_payload())
        if r.status_code == 409:
            log.error("'%s' already exists; use --start to run it", KEY)
            return 1
        r.raise_for_status()
        log.info("created '%s' (draft, salt %s); start it with --start", KEY, r.json()["data"]["salt"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
