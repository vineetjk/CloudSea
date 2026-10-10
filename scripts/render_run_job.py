"""Trigger a CloudSea cron job on Render now and print its logs until it finishes.

    uv run python scripts/render_run_job.py cloudsea-nightly
"""
from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime, timedelta

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cloudsea import settings  # noqa: E402,F401
from scripts.render_deploy import api, find_service, owner  # noqa: E402

DONE = ("saved call", "graded ", "Traceback", "Error", "Cron job run finished", "Cron job run failed")


def main() -> None:
    name = sys.argv[1]
    with api() as http:
        own, svc = owner(http), find_service(http, name)
        while (d := http.get(f"/services/{svc['id']}/deploys", params={"limit": 1}).json()[0]["deploy"])["status"] != "live":
            print(f"waiting for deploy ({d['status']})", flush=True)
            time.sleep(15)
        since = datetime.now(UTC) - timedelta(seconds=5)
        http.post(f"/cron-jobs/{svc['id']}/runs").raise_for_status()
        print(f"triggered {name}", flush=True)
        seen, t0 = 0, time.time()
        while time.time() - t0 < 900:
            time.sleep(15)
            params = {"ownerId": own, "resource": [svc["id"]], "direction": "forward", "limit": 100,
                      "startTime": since.isoformat().replace("+00:00", "Z"),
                      "endTime": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
            lines = [x["message"] for x in http.get("/logs", params=params).json()["logs"]]
            for line in lines[seen:]:
                print(line, flush=True)
            seen = len(lines)
            if any(k in ln for ln in lines for k in ("Cron job run finished", "Cron job run failed")):
                return


if __name__ == "__main__":
    main()
