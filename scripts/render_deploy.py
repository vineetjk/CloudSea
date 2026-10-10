"""Create CloudSea's Render resources through the Render API, mirroring render.yaml.

The Blueprint (render.yaml) is the normal way to deploy: Dashboard -> New -> Blueprint -> this repo.
This script exists because a Blueprint instance can't be created through the API, and the live instance was
set up from an agent session. It is idempotent: resources are found by name and only missing ones are created.

    uv run python scripts/render_deploy.py db gemma        # slow pieces first
    uv run python scripts/render_deploy.py api nightly grader web
    uv run python scripts/render_deploy.py status
"""
from __future__ import annotations

import os
import secrets
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cloudsea import settings  # noqa: E402,F401  (loads .env)

API = "https://api.render.com/v1"
REPO = "https://github.com/vineetjk/CloudSea"
REGION = "singapore"
UV_BUILD = "pip install uv && uv sync --frozen --no-dev"
SHARED_ENV = [{"key": "PYTHON_VERSION", "value": "3.12.11"}, {"key": "GEMMA_MODEL", "value": "gemma4:e2b-it-q4_K_M"}]


def api() -> httpx.Client:
    return httpx.Client(base_url=API, timeout=60, headers={
        "Authorization": f"Bearer {os.environ['RENDER_API_KEY']}", "Accept": "application/json"})


def owner(http) -> str:
    return http.get("/owners", params={"limit": 1}).raise_for_status().json()[0]["owner"]["id"]


def find_service(http, name: str) -> dict | None:
    for s in http.get("/services", params={"name": name, "limit": 20}).raise_for_status().json():
        if s["service"]["name"] == name:
            return s["service"]
    return None


def find_db(http, name: str) -> dict | None:
    for p in http.get("/postgres", params={"name": name, "limit": 20}).raise_for_status().json():
        if p["postgres"]["name"] == name:
            return p["postgres"]
    return None


def db_internal_url(http, db_id: str) -> str:
    return http.get(f"/postgres/{db_id}/connection-info").raise_for_status().json()["internalConnectionString"]


def create_service(http, body: dict) -> dict:
    existing = find_service(http, body["name"])
    if existing:
        print(f"exists: {body['name']} {existing['id']}")
        return existing
    r = http.post("/services", json=body)
    if r.status_code >= 400:
        raise RuntimeError(f"{body['name']}: {r.status_code} {r.text[:400]}")
    svc = r.json()["service"]
    print(f"created: {body['name']} {svc['id']}")
    return svc


def ensure_db(http, own: str) -> dict:
    db = find_db(http, "cloudsea-db")
    if db:
        print(f"exists: cloudsea-db {db['id']} ({db.get('status')})")
        return db
    r = http.post("/postgres", json={"name": "cloudsea-db", "ownerId": own, "plan": "0.1c-256mb", "region": REGION,
                                     "version": "17", "diskSizeGB": 1, "databaseName": "cloudsea"})
    if r.status_code >= 400:
        raise RuntimeError(f"cloudsea-db: {r.status_code} {r.text[:400]}")
    db = r.json()
    print(f"created: cloudsea-db {db['id']}")
    return db


def ensure_gemma(http, own: str) -> dict:
    return create_service(http, {
        "type": "private_service", "name": "cloudsea-gemma", "ownerId": own, "repo": REPO, "branch": "main",
        "autoDeploy": "yes",
        "serviceDetails": {"runtime": "docker", "plan": "2c-8g", "region": REGION, "numInstances": 1,
                           "disk": {"name": "ollama-models", "mountPath": "/var/data", "sizeGB": 10},
                           "envSpecificDetails": {"dockerfilePath": "./infra/gemma/Dockerfile",
                                                  "dockerContext": "./infra/gemma"}}})


def common_env(http) -> list[dict]:
    db = find_db(http, "cloudsea-db")
    gemma = find_service(http, "cloudsea-gemma")
    if not db or not gemma:
        raise RuntimeError("create db and gemma first")
    return SHARED_ENV + [{"key": "DATABASE_URL", "value": db_internal_url(http, db["id"])},
                         {"key": "OLLAMA_HOSTPORT", "value": f"{gemma['slug']}:11434"}]


def ensure_api(http, own: str, web_url: str) -> dict:
    env = common_env(http) + [{"key": "WEB_ORIGIN", "value": web_url}, {"key": "WEB_BASE_URL", "value": web_url},
                              {"key": "IP_SALT", "value": secrets.token_urlsafe(32)}]
    return create_service(http, {
        "type": "web_service", "name": "cloudsea-api", "ownerId": own, "repo": REPO, "branch": "main",
        "autoDeploy": "yes", "envVars": env,
        "serviceDetails": {"runtime": "python", "plan": "0.5c-512mb", "region": REGION, "healthCheckPath": "/healthz",
                           "envSpecificDetails": {"buildCommand": UV_BUILD, "startCommand": (
                               "uv run --no-sync uvicorn cloudsea.api.main:app --host 0.0.0.0 --port $PORT "
                               "--proxy-headers --forwarded-allow-ips '*'")}}})


def ensure_cron(http, own: str, name: str, schedule: str, module: str, extra_env: list[dict]) -> dict:
    return create_service(http, {
        "type": "cron_job", "name": name, "ownerId": own, "repo": REPO, "branch": "main", "autoDeploy": "yes",
        "envVars": common_env(http) + extra_env,
        "serviceDetails": {"runtime": "python", "plan": "1c-2g", "region": REGION, "schedule": schedule,
                           "envSpecificDetails": {"buildCommand": UV_BUILD,
                                                  "startCommand": f"uv run --no-sync python -m {module}"}}})


def ensure_web(http, own: str, api_url: str) -> dict:
    svc = create_service(http, {
        "type": "static_site", "name": "cloudsea-web", "ownerId": own, "repo": REPO, "branch": "main",
        "autoDeploy": "yes", "envVars": [{"key": "VITE_API_BASE", "value": api_url}],
        "serviceDetails": {"buildCommand": "cd web && npm ci && npm run build", "publishPath": "web/dist",
                           "pullRequestPreviewsEnabled": "no"}})
    routes = http.get(f"/services/{svc['id']}/routes").json()
    if not any(r.get("route", r).get("source") == "/*" for r in routes):
        http.post(f"/services/{svc['id']}/routes",
                  json={"type": "rewrite", "source": "/*", "destination": "/index.html"}).raise_for_status()
        print("added SPA rewrite route")
    return svc


def status(http) -> None:
    for name in ["cloudsea-gemma", "cloudsea-api", "cloudsea-nightly", "cloudsea-grader", "cloudsea-web"]:
        s = find_service(http, name)
        if not s:
            print(f"{name:18s} -")
            continue
        d = http.get(f"/services/{s['id']}/deploys", params={"limit": 1}).json()
        dep = d[0]["deploy"]["status"] if d else "no deploys"
        print(f"{name:18s} {s['id']} {dep:22s} {s['serviceDetails'].get('url', '')}")
    db = find_db(http, "cloudsea-db")
    print(f"{'cloudsea-db':18s} {db['id'] if db else '-'} {db.get('status') if db else ''}")


def main() -> None:
    steps = sys.argv[1:] or ["status"]
    with api() as http:
        own = owner(http)
        for step in steps:
            if step == "db":
                ensure_db(http, own)
            elif step == "gemma":
                ensure_gemma(http, own)
            elif step == "api":
                ensure_api(http, own, os.environ.get("WEB_URL", "https://cloudsea-web.onrender.com"))
            elif step == "nightly":
                ensure_cron(http, own, "cloudsea-nightly", "0 15 * * *", "cloudsea.jobs.nightly",
                            [{"key": "TABPFN_TOKEN", "value": os.environ["TABPFN_TOKEN"]}])
            elif step == "grader":
                ensure_cron(http, own, "cloudsea-grader", "45 2 * * *", "cloudsea.jobs.grader", [])
            elif step == "web":
                ensure_web(http, own, os.environ.get("API_URL", "https://cloudsea-api.onrender.com"))
            elif step == "status":
                status(http)
            else:
                raise SystemExit(f"unknown step {step}")
            time.sleep(1)


if __name__ == "__main__":
    main()
