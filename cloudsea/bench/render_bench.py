"""Phase 0: benchmark Gemma on Render CPU instances, then delete everything this script created.

Creates a private Ollama service from infra/gemma and a cron job that runs gemma_bench against it over the
private network (which also proves a cron job can reach a private service). Runs the benchmark on each plan
in --plans by resizing the same service, so the model stays on its disk between runs.
Render bills per second; the cost estimate is in BUILD_LOG.md.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from cloudsea import settings  # noqa: F401  (loads RENDER_API_KEY from .env)

API = "https://api.render.com/v1"
REPO = "https://github.com/vineetjk/CloudSea"
REGION = "singapore"
GEMMA_NAME = "cloudsea-gemma-bench"
RUNNER_NAME = "cloudsea-bench-runner"
PYTHON_VERSION = "3.12.11"


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def api() -> httpx.Client:
    return httpx.Client(base_url=API, timeout=60, headers={
        "Authorization": f"Bearer {os.environ['RENDER_API_KEY']}", "Accept": "application/json"})


def owner_id(http: httpx.Client) -> str:
    return http.get("/owners", params={"limit": 1}).raise_for_status().json()[0]["owner"]["id"]


def create_gemma(http: httpx.Client, owner: str, plan: str) -> dict:
    body = {
        "type": "private_service", "name": GEMMA_NAME, "ownerId": owner, "repo": REPO, "branch": "main",
        "autoDeploy": "no",
        "serviceDetails": {
            "runtime": "docker", "plan": plan, "region": REGION, "numInstances": 1,
            "disk": {"name": "ollama-models", "mountPath": "/var/data", "sizeGB": 10},
            "envSpecificDetails": {"dockerfilePath": "./infra/gemma/Dockerfile", "dockerContext": "./infra/gemma"},
        },
    }
    return http.post("/services", json=body).raise_for_status().json()["service"]


def create_runner(http: httpx.Client, owner: str, ollama_url: str) -> dict:
    body = {
        "type": "cron_job", "name": RUNNER_NAME, "ownerId": owner, "repo": REPO, "branch": "main",
        "autoDeploy": "no",
        "envVars": [{"key": "OLLAMA_URL", "value": ollama_url},
                    {"key": "PYTHON_VERSION", "value": PYTHON_VERSION}],
        "serviceDetails": {
            "runtime": "python", "plan": "starter", "region": REGION,
            "schedule": "0 0 1 1 *",  # effectively never; runs are triggered through the API
            "envSpecificDetails": {
                "buildCommand": "pip install uv && uv sync --frozen --no-dev",
                "startCommand": ("uv run --no-sync python -m cloudsea.bench.fetch_test_photos && "
                                 "uv run --no-sync python -m cloudsea.bench.gemma_bench --label render "
                                 "--out /tmp/bench --wait-model --print-json"),
            },
        },
    }
    return http.post("/services", json=body).raise_for_status().json()["service"]


def latest_deploy(http: httpx.Client, sid: str) -> dict:
    return http.get(f"/services/{sid}/deploys", params={"limit": 1}).raise_for_status().json()[0]["deploy"]


def wait_deploy(http: httpx.Client, sid: str, want_new_after: str | None = None, timeout: int = 3600) -> dict:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        d = latest_deploy(http, sid)
        if want_new_after and d["id"] == want_new_after:
            time.sleep(10)
            continue
        if d["status"] != last:
            log(f"  {sid} deploy {d['id']}: {d['status']}")
            last = d["status"]
        if d["status"] == "live":
            return d
        if d["status"] in ("build_failed", "update_failed", "canceled", "deactivated", "pre_deploy_failed"):
            raise RuntimeError(f"deploy {d['id']} ended as {d['status']}")
        time.sleep(15)
    raise TimeoutError(f"{sid} not live after {timeout}s")


def logs_since(http: httpx.Client, owner: str, resource: str, since: datetime) -> list[str]:
    params = {"ownerId": owner, "resource": [resource], "direction": "forward", "limit": 100,
              "startTime": since.isoformat().replace("+00:00", "Z"),
              "endTime": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    lines = []
    for _ in range(50):
        page = http.get("/logs", params=params).raise_for_status().json()
        lines += [entry["message"] for entry in page["logs"]]
        if not page.get("hasMore"):
            break
        params["startTime"], params["endTime"] = page["nextStartTime"], page["nextEndTime"]
    return lines


def run_bench(http: httpx.Client, owner: str, runner_id: str, timeout: int = 2400) -> tuple[dict, list[str]]:
    since = datetime.now(UTC) - timedelta(seconds=5)
    http.post(f"/cron-jobs/{runner_id}/runs").raise_for_status()
    log("  benchmark run triggered")
    t0, seen = time.time(), 0
    while time.time() - t0 < timeout:
        time.sleep(20)
        lines = logs_since(http, owner, runner_id, since)
        for line in lines[seen:]:
            if not line.startswith("BENCH_JSON"):
                log(f"  runner: {line[:160]}")
        seen = len(lines)
        parts = [ln for ln in lines if ln.startswith("BENCH_JSON ")]
        if parts:
            return json.loads(parts[-1].removeprefix("BENCH_JSON ")), lines
    raise TimeoutError("no BENCH_JSON in runner logs")


def peak_memory_gb(http: httpx.Client, sid: str, since: datetime) -> float | None:
    try:
        r = http.get("/metrics/memory", params={
            "resource": sid, "startTime": since.isoformat().replace("+00:00", "Z"),
            "endTime": datetime.now(UTC).isoformat().replace("+00:00", "Z"), "resolutionSeconds": 60})
        series = r.raise_for_status().json()
        values = [float(v["value"]) for s in series for v in s.get("values", [])]
        return round(max(values) / 1e9, 2) if values else None
    except (httpx.HTTPError, KeyError, ValueError) as err:
        log(f"  memory metrics unavailable: {err}")
        return None


def find_service(http: httpx.Client, owner: str, name: str) -> dict | None:
    found = http.get("/services", params={"ownerId": owner, "name": name, "limit": 5}).raise_for_status().json()
    return next((s["service"] for s in found if s["service"]["name"] == name), None)


def set_plan(http: httpx.Client, sid: str, plan: str) -> None:
    previous = latest_deploy(http, sid)["id"]
    http.patch(f"/services/{sid}", json={"serviceDetails": {"plan": plan}}).raise_for_status()
    log(f"resized {sid} to {plan}")
    wait_deploy(http, sid, want_new_after=previous)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plans", nargs="+", default=["4c-8g", "2c-8g"])
    ap.add_argument("--out", type=Path, default=Path("docs/phase0"))
    ap.add_argument("--keep", action="store_true", help="do not delete the services afterwards")
    args = ap.parse_args()

    # Turn SIGTERM into SystemExit so the cleanup in `finally` still runs when the job is stopped.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
    created: list[str] = []
    with api() as http:
        owner = owner_id(http)
        try:
            t_first = datetime.now(UTC)
            gemma = find_service(http, owner, GEMMA_NAME)
            if gemma:
                log(f"reusing private service {gemma['id']} ({gemma['serviceDetails']['plan']})")
                created.append(gemma["id"])
                if gemma["serviceDetails"]["plan"] != args.plans[0]:
                    set_plan(http, gemma["id"], args.plans[0])
            else:
                gemma = create_gemma(http, owner, args.plans[0])
                created.append(gemma["id"])
                log(f"created private service {gemma['id']} ({args.plans[0]}), slug {gemma['slug']}")
                wait_deploy(http, gemma["id"])
            runner = find_service(http, owner, RUNNER_NAME)
            if runner:
                created.append(runner["id"])
                previous = latest_deploy(http, runner["id"])["id"]
                http.post(f"/services/{runner['id']}/deploys", json={}).raise_for_status()
                log(f"reusing cron runner {runner['id']}, redeploying latest commit")
                wait_deploy(http, runner["id"], want_new_after=previous)
            else:
                runner = create_runner(http, owner, f"http://{gemma['slug']}:11434")
                created.append(runner["id"])
                log(f"created cron runner {runner['id']}")
                wait_deploy(http, runner["id"])

            for i, plan in enumerate(args.plans):
                if i > 0:
                    set_plan(http, gemma["id"], plan)
                since = datetime.now(UTC)
                result, lines = run_bench(http, owner, runner["id"])
                result["label"] = f"render-{plan}"
                result["render"] = {"plan": plan, "region": REGION,
                                    "peak_memory_gb": peak_memory_gb(http, gemma["id"], since),
                                    "first_deploy_started": t_first.isoformat()}
                path = args.out / f"bench_gemma_render-{plan}.json"
                path.write_text(json.dumps(result, indent=2))
                log(f"saved {path}")
                for line in lines:
                    if line.lstrip().startswith(("render:", "cold load", "writer agent", "photo rating", "memory")):
                        log(f"  {line.strip()}")
        finally:
            if args.keep:
                log(f"keeping services: {created}")
            for sid in reversed(created if not args.keep else []):
                r = http.delete(f"/services/{sid}")
                log(f"deleted {sid}: HTTP {r.status_code}")
    sys.exit(0)


if __name__ == "__main__":
    main()
