"""API tests. The integration tests run against a real Postgres when TEST_DATABASE_URL is set (`make test-db`).

They DROP and recreate the CloudSea tables in that database, so point it at a throwaway database.
"""
from __future__ import annotations

import io
import json
import os
import time as clock
from collections.abc import Iterator
from datetime import datetime, timedelta

import numpy as np
import psycopg
import pytest
from PIL import Image

from cloudsea import db, gemma, rater, settings
from cloudsea.api import backtest
from cloudsea.config import IST

TEST_DB = os.environ.get("TEST_DATABASE_URL", "")
needs_db = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set; skipping Postgres integration "
                                                  "tests (run `make db-up test-db`)")
FAKE_RATING = {"label": "cloud_sea", "confidence": 0.9, "evidence": "A white layer fills the valleys below.",
               "answers": {"nearby_objects_hazy": False, "ground_visible_far_below": False,
                           "layer_below_horizon": True}}


# --- backtest mapping (no database) --------------------------------------------------------------------

RAW_BACKTEST = {
    "label": "B_low_layer_summit_clear", "test_season": "2025-26", "train_rows": 1200, "test_rows": 151,
    "test_base_rate": 0.31,
    "models": {
        "gbt_full": {"thresholds": {"skip_below": 0.12, "go_at": 0.6},
                     "test": {"n": 151, "brier": 0.15, "roc_auc": 0.8, "go_nights": 9, "go_precision": 0.55},
                     "calibration": []},
        "tabpfn_full": {"thresholds": {"skip_below": 0.15, "go_at": 0.55},
                        "test": {"n": 151, "brier": 0.12, "roc_auc": 0.84, "go_nights": 12, "go_precision": 0.62},
                        "calibration": [{"bin": "0.0-0.1", "predicted": 0.05, "observed": 0.04, "n": 80},
                                        {"bin": "0.9-1.0", "predicted": 0.93, "observed": 1.0, "n": 2}]},
    },
    "baselines": {"climatology": {"n": 151, "brier": 0.2, "roc_auc": 0.6}},
    "headline": {"model": "tabpfn_full", "weekend_mornings": 43, "every_weekend_seas": 12, "go_trips": 5,
                 "go_seas": 4, "go_or_maybe_trips": 11, "go_or_maybe_seas": 8, "seas_missed_by_skip": 4},
}


def test_backtest_shape(tmp_path):
    path = tmp_path / "backtest.json"
    path.write_text(json.dumps(RAW_BACKTEST))
    out = backtest.load(path)
    assert out["season"] == "2025-26"
    h = out["headline"]
    assert h["weekend_mornings"] == 43 and h["go_trips"] == 5 and h["seas_missed_by_skip"] == 4
    assert (h["weekends"], h["every_weekend_seas"], h["cloudsea_trips"], h["cloudsea_seas"]) == (43, 12, 11, 8)
    assert [m["id"] for m in out["metrics"]] == ["tabpfn_full", "gbt_full", "climatology"]
    assert out["metrics"][0]["model"].startswith("TabPFN") and out["metrics"][0]["go_precision"] == 0.62
    assert "go_precision" not in out["metrics"][2] and out["metrics"][2]["kind"] == "baseline"
    assert out["calibration"][0] == {"bin": "0-10%", "predicted": 0.05, "observed": 0.04, "n": 80}
    assert out["calibration"][1]["bin"] == "90-100%"


def test_backtest_missing_file(tmp_path):
    assert backtest.load(tmp_path / "nope.json") is None


# --- integration ---------------------------------------------------------------------------------------

def today() -> datetime:
    return datetime.now(IST)


def dawn_now() -> datetime:
    """A capture time in the latest dawn window that has already started."""
    now = today()
    t = now.replace(hour=6, minute=10, second=0, microsecond=0)
    return t if t <= now else t - timedelta(days=1)


def jpeg(size=(800, 600)) -> bytes:
    im = Image.new("RGB", size, (200, 200, 220))
    exif = Image.Exif()
    exif.get_ifd(0x8825).update({1: "N", 2: (13.0, 22.0, 12.7), 3: "E", 4: (77.0, 41.0, 0.6)})
    out = io.BytesIO()
    im.save(out, "JPEG", exif=exif)
    return out.getvalue()


@pytest.fixture
def client(monkeypatch) -> Iterator:
    from fastapi.testclient import TestClient

    from cloudsea.api import main
    monkeypatch.setattr(settings, "DATABASE_URL", TEST_DB)
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS calls, outcomes, photos, going, train_rows")
    monkeypatch.setattr(gemma, "available", lambda timeout=5: True)
    monkeypatch.setattr(rater, "rate_photo", lambda jpeg_bytes: dict(FAKE_RATING))
    main.post_limiter.reset()
    with TestClient(main.app) as c:
        yield c


def upload(client, ip="203.0.113.5", taken: datetime | None = None, data: bytes | None = None, **form):
    fields = {"taken_at": (taken or dawn_now()).isoformat(), "gps_present": "false", **form}
    return client.post("/api/photos", files={"photo": ("dawn.jpg", data or jpeg(), "image/jpeg")}, data=fields,
                       headers={"X-Forwarded-For": f"{ip}, 10.0.0.1"})


def wait_rated(client, pid: str, token: str, timeout: float = 10) -> dict:
    end = clock.monotonic() + timeout
    while True:
        body = client.get(f"/api/photos/{pid}", params={"token": token}).json()
        if body["status"] != "queued" or clock.monotonic() > end:
            return body
        clock.sleep(0.1)


@needs_db
def test_today_before_the_first_call(client):
    r = client.get("/api/today")
    assert r.status_code == 200
    assert r.json() == {"status": "no_call_yet", "call": None, "last_graded": None}


@needs_db
def test_today_and_going(client, new_call):
    tomorrow = (today() + timedelta(days=1)).date()
    with db.connect() as conn:
        db.upsert_call(conn, new_call(tomorrow, "SKIP", 0.08))
        db.upsert_call(conn, new_call(tomorrow, "MAYBE", 0.41))       # re-issue replaces
    body = client.get("/api/today").json()
    assert body["status"] == "ok" and body["last_graded"] is None
    call = body["call"]
    assert set(call) == {"date", "issued_at", "verdict", "probability", "sunrise", "first_light", "text",
                         "text_kn", "text_hi", "carry", "conditions", "leave_by", "gate", "model", "going_count"}
    assert call["date"] == tomorrow.isoformat() and call["verdict"] == "MAYBE" and call["probability"] == 0.41
    assert call["issued_at"].endswith("+05:30") and call["going_count"] == 0
    assert call["leave_by"][0]["leave_by"] == "03:39" and call["gate"]["verified"] is False

    def going(ip):
        return client.post("/api/going", json={"date": tomorrow.isoformat()}, headers={"X-Forwarded-For": ip})
    assert going("198.51.100.1").json() == {"count": 1}
    r = going("198.51.100.1")
    assert r.status_code == 200 and r.json() == {"count": 1}
    assert going("198.51.100.2").json() == {"count": 2}
    assert client.get("/api/today").json()["call"]["going_count"] == 2
    past = (today() - timedelta(days=2)).date().isoformat()
    assert client.post("/api/going", json={"date": past}).status_code == 400
    later = (today() + timedelta(days=5)).date().isoformat()
    assert client.post("/api/going", json={"date": later}).status_code == 404
    r = client.post("/api/going", json={"date": "not-a-date"})
    assert r.status_code == 400 and "error" in r.json()


@needs_db
def test_photo_upload_rating_confirm_gallery(client):
    r = upload(client, public="false")
    assert r.status_code == 201, r.text
    up = r.json()
    assert up["status"] == "queued" and up["id"].startswith("p_") and up["token"].startswith("t_")
    pid, token = up["id"], up["token"]

    photo = wait_rated(client, pid, token)
    assert photo["status"] == "rated"
    assert photo["rating"] == {k: FAKE_RATING[k] for k in ("label", "confidence", "evidence")}
    assert photo["date"] == dawn_now().date().isoformat() and photo["confirmed_label"] is None
    assert photo["public"] is False

    assert client.get(f"/api/photos/{pid}", params={"token": "t_wrong"}).status_code == 403
    assert client.get(f"/api/photos/{pid}").status_code == 403
    assert client.get("/api/photos/p_missing", params={"token": token}).status_code == 404

    # Private photo: only the owner's token opens the image; nothing identifying survives.
    assert client.get(f"/api/photos/{pid}/image").status_code == 404
    assert client.get(f"/api/photos/{pid}/image", params={"token": "t_wrong"}).status_code == 403
    img = client.get(f"/api/photos/{pid}/image", params={"token": token})
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert img.headers["cache-control"].startswith("private")
    assert b"Exif\x00\x00" not in img.content and len(Image.open(io.BytesIO(img.content)).getexif()) == 0
    with psycopg.connect(TEST_DB) as conn:
        stored = conn.execute("SELECT token_hash, ip_hash FROM photos WHERE id = %s", (pid,)).fetchone()
    assert token not in stored and "203.0.113.5" not in stored[1]

    assert client.get("/api/gallery").json() == []
    bad = client.post(f"/api/photos/{pid}/confirm", json={"token": token, "label": "unusable", "public": True})
    assert bad.status_code == 400
    r = client.post(f"/api/photos/{pid}/confirm", json={"token": "t_wrong", "label": "cloud_sea", "public": True})
    assert r.status_code == 403
    r = client.post(f"/api/photos/{pid}/confirm", json={"token": token, "label": "partial", "public": True})
    assert r.status_code == 200
    assert r.json()["confirmed_label"] == "partial" and r.json()["public"] is True

    gallery = client.get("/api/gallery").json()
    assert gallery == [{"id": pid, "date": photo["date"], "label": "partial",
                        "image_url": f"/api/photos/{pid}/image"}]
    pub = client.get(f"/api/photos/{pid}/image")
    assert pub.status_code == 200 and pub.headers["cache-control"] == "public, max-age=86400"

    # Confirming again without `public` keeps the current choice; with it, overrides.
    r = client.post(f"/api/photos/{pid}/confirm", json={"token": token, "label": "cloud_sea"})
    assert r.json()["public"] is True and r.json()["confirmed_label"] == "cloud_sea"
    r = client.post(f"/api/photos/{pid}/confirm", json={"token": token, "label": "cloud_sea", "public": False})
    assert r.json()["public"] is False and client.get("/api/gallery").json() == []

    with db.connect() as conn:
        assert db.photo_summary(conn, dawn_now().date()) == {"photos": 1, "majority": "cloud_sea",
                                                              "counts": {"cloud_sea": 1}}


@needs_db
def test_rating_failures_give_up_after_three_attempts(client, monkeypatch):
    from cloudsea.api import main, sweeper

    main.sweeper.stop()

    def broken(_):
        raise ValueError("bad JSON from the model")
    monkeypatch.setattr(rater, "rate_photo", broken)
    up = upload(client).json()
    for _ in range(3):
        sweeper.rate_one()
    assert sweeper.rate_one() is None
    body = client.get(f"/api/photos/{up['id']}", params={"token": up["token"]}).json()
    assert body["status"] == "failed" and body["rating"] is None
    # Gemma unreachable: nothing is claimed, so no attempts are used up.
    monkeypatch.setattr(gemma, "available", lambda timeout=5: False)
    assert sweeper.sweep() == 0


@needs_db
def test_upload_validation(client):
    r = upload(client, data=b"\xff\xd8" + b"0" * (260 * 1024))
    assert r.status_code == 413 and "250 KB" in r.json()["error"]
    r = upload(client, taken=dawn_now().replace(hour=12))
    assert r.status_code == 400 and "05:00 and 08:30" in r.json()["error"]
    r = upload(client, taken=dawn_now() - timedelta(days=3))
    assert r.status_code == 400 and "36 hours" in r.json()["error"]
    r = upload(client, gps_present="true", distance_km="12.5")
    assert r.status_code == 400 and "km from the summit" in r.json()["error"]
    assert upload(client, gps_present="true", distance_km="0.8").status_code == 201
    r = upload(client, data=b"hello")
    assert r.status_code == 400 and "error" in r.json()
    r = client.post("/api/photos", data={"taken_at": dawn_now().isoformat()})
    assert r.status_code == 400
    r = client.post("/api/photos", files={"photo": ("a.jpg", jpeg(), "image/jpeg")},
                    data={"taken_at": "2026-10-11T06:00:00"})
    assert r.status_code == 400 and "timezone" in r.json()["error"]


@needs_db
def test_five_uploads_per_ip_per_day(client):
    for _ in range(5):
        assert upload(client, ip="192.0.2.77").status_code == 201
    r = upload(client, ip="192.0.2.77")
    assert r.status_code == 429 and "daily limit" in r.json()["error"]
    assert upload(client, ip="192.0.2.78").status_code == 201


@needs_db
def test_post_limiter(client):
    codes = [client.post("/api/going", json={}, headers={"X-Forwarded-For": "192.0.2.9"}).status_code
             for _ in range(31)]
    assert codes[:30] == [400] * 30 and codes[30] == 429


@needs_db
def test_scoreboard_and_last_graded(client, new_call):
    empty = client.get("/api/scoreboard").json()
    assert empty == {"summary": {"graded": 0, "correct": 0, "go_calls": 0, "go_hits": 0, "brier": None,
                                 "since": None},
                     "days": [], "agreement": {"days_with_both": 0, "airport_and_photos_agree": 0}}

    d = today().date()
    d3, d2, d1 = d - timedelta(days=3), d - timedelta(days=2), d - timedelta(days=1)
    with db.connect() as conn:
        db.upsert_call(conn, new_call(d3, "SKIP", 0.08))
        db.upsert_call(conn, new_call(d2, "MAYBE", 0.41))
        db.upsert_call(conn, new_call(d1, "GO", 0.7))
        db.upsert_call(conn, new_call(d + timedelta(days=1), "GO", 0.9))      # tonight's: not on the board
        db.upsert_outcome(conn, d3, "no_sea", "VOBL 05:30-07:30: vis 6000 m, FEW020", {"n_dawn": 5})
        db.upsert_outcome(conn, d2, "no_sea", "VOBL: BR, SCT012", {"n_dawn": 5})
        db.upsert_outcome(conn, d1, "cloud_sea", "VOBL: FG, BKN004", {"n_dawn": 5, "rh850": np.float64(61.5)})
        # One uploader with three photos counts once: votes are clear_no_sea 1, cloud_sea 2.
        for i, (who, label) in enumerate([("a", "clear_no_sea")] * 3 + [("b", "cloud_sea"), ("c", "cloud_sea")]):
            conn.execute(
                """INSERT INTO photos (id, date, image, taken_at, gps_present, ip_hash, token_hash, status,
                   confirmed_label, confirmed_at) VALUES (%s, %s, %s, now(), false, %s, 'x', 'rated', %s, now())""",
                (f"p_{i}", d1, b"jpeg", who, label))
        assert db.photo_summary(conn, d1) == {"photos": 5, "majority": "cloud_sea",
                                              "counts": {"clear_no_sea": 1, "cloud_sea": 2}}

    body = client.get("/api/scoreboard").json()
    assert body["summary"] == {"graded": 3, "correct": 2, "go_calls": 1, "go_hits": 1, "brier": 0.088,
                               "since": d3.isoformat()}
    assert [x["date"] for x in body["days"]] == [d1.isoformat(), d2.isoformat(), d3.isoformat()]
    assert body["days"][0] == {"date": d1.isoformat(), "verdict": "GO", "probability": 0.7,
                               "airport_outcome": "cloud_sea", "photo_outcome": "cloud_sea", "photos": 5,
                               "correct": True, "evidence": "VOBL: FG, BKN004"}
    assert body["days"][1]["correct"] is False          # MAYBE on a no-sea morning
    assert body["agreement"] == {"days_with_both": 1, "airport_and_photos_agree": 1}

    last = client.get("/api/today").json()["last_graded"]
    assert last == {"date": d1.isoformat(), "verdict": "GO", "probability": 0.7, "airport_outcome": "cloud_sea",
                    "photo_outcome": "cloud_sea", "correct": True}

    with db.connect() as conn:                          # "could not tell": listed, not graded
        db.upsert_outcome(conn, d1, None, "Too few reports", {})
    body = client.get("/api/scoreboard").json()
    assert body["summary"]["graded"] == 2 and body["days"][0]["correct"] is None


@needs_db
def test_train_rows_roundtrip(client):
    d = today().date()
    with db.connect() as conn:
        db.upsert_train_row(conn, d, {"a": np.float64(1.5), "b": float("nan"), "c": np.int64(3)}, np.float32(1.0))
        db.upsert_train_row(conn, d, {"a": 2.0, "b": None, "c": 4}, None)
        rows = db.train_rows(conn)
    assert len(rows) == 1 and rows[0]["features"] == {"a": 2.0, "b": None, "c": 4} and rows[0]["y"] is None
    with db.connect() as conn:
        db.upsert_train_row(conn, d - timedelta(days=1), {"a": 1.0, "b": float("nan")}, 0.0)
        rows = db.train_rows(conn)
    assert [r["date"] for r in rows] == [d - timedelta(days=1), d] and rows[0]["features"]["b"] is None
    with db.connect() as conn:
        call = db.get_call(conn, d)
        assert call is None and db.latest_call(conn) is None


@needs_db
def test_share_routes(client, new_call):
    d = (today() + timedelta(days=1)).date()
    with db.connect() as conn:
        db.upsert_call(conn, new_call(d, "SKIP", 0.08))
    page = client.get(f"/s/{d}", headers={"X-Forwarded-Proto": "https"})
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert f'content="https://testserver/og/{d}.png?v=' in page.text
    assert "SKIP · 8% cloud sea" in page.text and 'twitter:card" content="summary_large_image"' in page.text
    og = client.get(f"/og/{d}.png")
    assert og.status_code == 200 and og.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(og.content)).size == (1200, 630)
    assert "content-disposition" not in og.headers
    story = client.get(f"/story/{d}.png")
    assert Image.open(io.BytesIO(story.content)).size == (1080, 1920)
    assert story.headers["content-disposition"] == f'attachment; filename="cloudsea-{d}.png"'
    missing = d + timedelta(days=9)
    assert client.get(f"/og/{missing}.png").status_code == 404
    assert client.get(f"/story/{missing}.png").json()["error"]
    assert client.get(f"/s/{missing}").status_code == 404
    assert client.get("/og/garbage.png").status_code == 404


@needs_db
def test_cors_health_and_errors(client):
    pre = client.options("/api/going", headers={"Origin": "http://localhost:5173",
                                                "Access-Control-Request-Method": "POST",
                                                "Access-Control-Request-Headers": "content-type"})
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "content-type" in pre.headers["access-control-allow-headers"].lower()
    denied = client.options("/api/going", headers={"Origin": "https://evil.example",
                                                   "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in denied.headers
    assert client.get("/healthz").json() == {"ok": True, "gemma": True}
    r = client.get("/api/nothing-here")
    assert r.status_code == 404 and r.json() == {"error": "Not found."}
