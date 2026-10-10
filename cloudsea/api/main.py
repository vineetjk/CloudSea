"""CloudSea API: tonight's call, the public scoreboard, summit photos, and share cards. Contract: docs/API.md.

Run: `uvicorn cloudsea.api.main:app`. Needs DATABASE_URL; see `make api`.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated

import psycopg
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from cloudsea import db, gemma, photos, rater, share
from cloudsea.api import backtest
from cloudsea.api.limits import MinuteLimiter, ip_hash, ip_salt, sha256_hex, token_matches
from cloudsea.api.sweeper import Sweeper
from cloudsea.config import IST

log = logging.getLogger("cloudsea.api")

DAILY_UPLOADS = 5
GALLERY_MAX = 60
MAX_UPLOAD_REQUEST = 400 * 1024          # multipart overhead on top of the 250 KB photo
SWEEPER_ENABLED = os.environ.get("CLOUDSEA_SWEEPER", "1") != "0"
WEB_BASE_URL = os.environ.get("WEB_BASE_URL", "http://localhost:5173")
ORIGINS = [o.strip().rstrip("/") for o in os.environ.get("WEB_ORIGIN", "").split(",") if o.strip()]
ORIGINS += [o for o in ("http://localhost:5173", "http://localhost:4173") if o not in ORIGINS]

sweeper = Sweeper()
post_limiter = MinuteLimiter()


def _init_db(tries: int = 5) -> None:
    for i in range(tries):
        try:
            with db.connect() as conn:
                db.init_schema(conn)
            return
        except psycopg.OperationalError as exc:
            if i == tries - 1:
                raise
            log.warning("database not ready (%s); retrying", exc)
            time.sleep(2 * (i + 1))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)       # the sweeper polls Ollama every 120 s
    ip_salt()                                 # warn early if the salt is missing
    _init_db()
    if SWEEPER_ENABLED:
        sweeper.start()
    yield
    sweeper.stop()


app = FastAPI(title="CloudSea API", version="1.0", lifespan=lifespan, docs_url="/api/docs",
              redoc_url=None, openapi_url="/api/openapi.json")


# --- errors: always {"error": "..."} ------------------------------------------------------------------

def _error(status: int, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status, headers=headers)


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    if exc.status_code == 404 and message == "Not Found":
        message = "Not found."
    return _error(exc.status_code, message, getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    first = errors[0] if errors else {}
    if first.get("type") == "json_invalid":
        return _error(400, "The request body isn't valid JSON.")
    where = ".".join(str(x) for x in first.get("loc", ()) if x not in ("body", "query", "path", "form"))
    return _error(400, f"Invalid {where or 'request'}: {first.get('msg', 'check the request')}.")


@app.exception_handler(photos.PhotoError)
async def _photo_error(request: Request, exc: photos.PhotoError) -> JSONResponse:
    return _error(exc.status, str(exc))


@app.exception_handler(psycopg.OperationalError)
async def _db_down(request: Request, exc: psycopg.OperationalError) -> JSONResponse:
    log.error("database error: %s", exc)
    return _error(503, "The database is unavailable right now. Please try again in a minute.")


# --- middleware: request size and a per-IP POST limit; CORS outermost so errors stay readable ----------

@app.middleware("http")
async def _guards(request: Request, call_next):
    if request.method == "POST":
        if request.url.path == "/api/photos":
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                length = 0
            if length > MAX_UPLOAD_REQUEST:
                return _error(413, "This photo is larger than 250 KB. Try again from the app, which shrinks it first.")
        if not post_limiter.allow(ip_hash(request)):
            return _error(429, "Too many requests from your network. Please wait a minute.",
                          {"Retry-After": "60"})
    return await call_next(request)


app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"], max_age=600)


# --- helpers -------------------------------------------------------------------------------------------

def today_ist() -> date:
    return datetime.now(IST).date()


def _iso_ist(ts: datetime | None) -> str | None:
    return ts.astimezone(IST).isoformat(timespec="seconds") if ts else None


def public_call(call: dict) -> dict:
    """The call as the public sees it: no features, thresholds or text source."""
    return {
        "date": call["date"].isoformat(), "issued_at": _iso_ist(call["issued_at"]),
        "verdict": call["verdict"], "probability": call["probability"],
        "sunrise": call["sunrise"], "first_light": call["first_light"],
        "text": call["text"], "text_kn": call.get("text_kn"), "text_hi": call.get("text_hi"),
        "carry": call["carry"], "conditions": call["conditions"], "leave_by": call["leave_by"],
        "gate": call["gate"], "model": call["model"],
    }


def photo_out(row: dict) -> dict:
    r = row.get("rating")
    rating = ({"label": r.get("label"), "confidence": r.get("confidence"), "evidence": r.get("evidence")}
              if r else None)
    return {"id": row["id"], "date": row["date"].isoformat(), "status": row["status"], "rating": rating,
            "confirmed_label": row["confirmed_label"], "public": row["public"]}


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(404, "That isn't a date in the form YYYY-MM-DD.") from None


def _public_base(request: Request) -> str:
    """Base URL as the outside world sees it (Render terminates TLS and sets X-Forwarded-Proto)."""
    base = str(request.base_url)
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if proto in ("http", "https"):
        base = proto + base[base.index(":"):]
    return base


NO_STORE = {"Cache-Control": "no-store"}


# --- routes --------------------------------------------------------------------------------------------

@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "gemma": gemma.available(timeout=3)}


@app.get("/api/today")
def get_today() -> JSONResponse:
    with db.connect() as conn:
        call = db.latest_call(conn)
        last = db.last_graded(conn)
        body: dict = {"status": "no_call_yet", "call": None, "last_graded": last}
        if call is not None:
            out = public_call(call)
            out["going_count"] = db.going_count(conn, call["date"])
            body = {"status": "ok", "call": out, "last_graded": last}
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=30"})


@app.get("/api/scoreboard")
def get_scoreboard() -> JSONResponse:
    with db.connect() as conn:
        body = db.scoreboard(conn, today_ist())
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=60"})


@app.get("/api/backtest")
def get_backtest() -> JSONResponse:
    body = backtest.load()
    if body is None:
        raise HTTPException(404, "The backtest results haven't been published yet.")
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=300"})


class GoingIn(BaseModel):
    date: date


@app.post("/api/going")
def post_going(body: GoingIn, request: Request) -> dict:
    if body.date < today_ist():
        raise HTTPException(400, "That sunrise has already happened.")
    with db.connect() as conn:
        if db.get_call(conn, body.date) is None:
            raise HTTPException(404, "There's no call for that date.")
        count = db.add_going(conn, body.date, ip_hash(request))
    return {"count": count}


@app.post("/api/photos", status_code=201)
def post_photo(
    request: Request,
    photo: Annotated[UploadFile | None, File()] = None,
    taken_at: Annotated[str | None, Form()] = None,
    gps_present: Annotated[str | None, Form()] = None,
    distance_km: Annotated[str | None, Form()] = None,
    public: Annotated[str | None, Form()] = None,
) -> JSONResponse:
    if photo is None:
        raise photos.PhotoError("Attach a photo to upload.")
    data = photo.file.read(photos.MAX_BYTES + 1)
    if len(data) > photos.MAX_BYTES:
        raise photos.PhotoError("This photo is larger than 250 KB. Try again from the app, which shrinks it first.",
                                413)
    taken = photos.parse_taken_at(taken_at)
    day = photos.check_taken_at(taken)
    gps = photos.parse_bool(gps_present)
    distance = photos.parse_distance(distance_km)
    photos.check_distance(gps, distance)
    is_public = photos.parse_bool(public)
    jpeg = photos.reencode(data)

    who = ip_hash(request)
    photo_id, token = "p_" + secrets.token_urlsafe(9), "t_" + secrets.token_urlsafe(18)
    midnight = datetime.combine(today_ist(), datetime.min.time(), IST)
    with db.connect() as conn:
        db.lock_uploader(conn, who)
        if db.uploads_since(conn, who, midnight) >= DAILY_UPLOADS:
            raise HTTPException(429, f"You've uploaded {DAILY_UPLOADS} photos today, which is the daily limit. "
                                     "Thank you for sharing.")
        db.insert_photo(conn, id=photo_id, day=day, image=jpeg, taken_at=taken, gps_present=gps,
                        distance_km=distance if gps else None, ip_hash=who, token_hash=sha256_hex(token),
                        public=is_public)
    sweeper.kick()
    return JSONResponse({"id": photo_id, "token": token, "status": "queued"}, status_code=201, headers=NO_STORE)


def _owned_photo(conn: psycopg.Connection, photo_id: str, token: str | None) -> dict:
    row = db.get_photo(conn, photo_id)
    if row is None:
        raise HTTPException(404, "We couldn't find that photo.")
    if not token_matches(token, row["token_hash"]):
        raise HTTPException(403, "This photo can only be seen from the device that uploaded it.")
    return row


@app.get("/api/photos/{photo_id}")
def get_photo(photo_id: str, token: str | None = None) -> JSONResponse:
    with db.connect() as conn:
        row = _owned_photo(conn, photo_id, token)
    return JSONResponse(photo_out(row), headers=NO_STORE)


class ConfirmIn(BaseModel):
    token: str
    label: str
    public: bool | None = None


@app.post("/api/photos/{photo_id}/confirm")
def confirm_photo(photo_id: str, body: ConfirmIn) -> JSONResponse:
    if body.label not in rater.CONFIRMABLE:
        raise HTTPException(400, f"label must be one of: {', '.join(rater.CONFIRMABLE)}.")
    with db.connect() as conn:
        _owned_photo(conn, photo_id, body.token)
        row = db.confirm_photo(conn, photo_id, body.label, body.public)
    return JSONResponse(photo_out(row), headers=NO_STORE)


@app.get("/api/gallery")
def get_gallery() -> JSONResponse:
    with db.connect() as conn:
        rows = db.gallery(conn, GALLERY_MAX)
    body = [{"id": r["id"], "date": r["date"].isoformat(), "label": r["label"],
             "image_url": f"/api/photos/{r['id']}/image"} for r in rows]
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=60"})


@app.get("/api/photos/{photo_id}/image")
def get_photo_image(photo_id: str, token: str | None = None) -> Response:
    with db.connect() as conn:
        row = db.get_photo_image(conn, photo_id)
    if row is None:
        raise HTTPException(404, "We couldn't find that photo.")
    if row["public"]:
        cache = "public, max-age=86400"
    elif token_matches(token, row["token_hash"]):
        cache = "private, max-age=3600"
    elif token:
        raise HTTPException(403, "This photo can only be seen from the device that uploaded it.")
    else:
        raise HTTPException(404, "We couldn't find that photo.")
    return Response(bytes(row["image"]), media_type="image/jpeg",
                    headers={"Cache-Control": cache, "X-Content-Type-Options": "nosniff"})


# --- share ---------------------------------------------------------------------------------------------

@app.get("/s/{day}", response_class=HTMLResponse)
def share_page(day: str, request: Request) -> HTMLResponse:
    d = _parse_day(day)
    with db.connect() as conn:
        call = db.get_call(conn, d)
    page = share.share_html(call, d, base_url=_public_base(request), web_base_url=WEB_BASE_URL)
    return HTMLResponse(page, status_code=200 if call else 404,
                        headers={"Cache-Control": "public, max-age=300"})


def _card(day: str, kind: str) -> bytes:
    d = _parse_day(day)
    with db.connect() as conn:
        call = db.get_call(conn, d)
    if call is None:
        raise HTTPException(404, "There's no call for that date.")
    return share.card_png(kind, call)


@app.get("/og/{day}.png")
def og_card(day: str) -> Response:
    return Response(_card(day, "og"), media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/story/{day}.png")
def story_card(day: str) -> Response:
    return Response(_card(day, "story"), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600",
                             "Content-Disposition": f'attachment; filename="cloudsea-{day}.png"'})
