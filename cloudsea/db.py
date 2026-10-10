"""Postgres access (psycopg 3, sync). Used by the API and by the nightly and morning jobs.

`with connect() as conn:` commits on a clean exit and rolls back on an exception. JSON columns accept plain
Python values; numpy scalars and NaN are converted on the way in (NaN becomes null).
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from cloudsea import settings
from cloudsea.config import IST

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
  date date PRIMARY KEY,
  issued_at timestamptz NOT NULL,
  verdict text NOT NULL CHECK (verdict IN ('GO','MAYBE','SKIP')),
  probability real NOT NULL,
  sunrise text NOT NULL, first_light text NOT NULL,
  text text NOT NULL, text_source text NOT NULL,
  text_kn text, text_hi text,
  carry jsonb NOT NULL, conditions jsonb NOT NULL, leave_by jsonb NOT NULL, gate jsonb NOT NULL,
  model jsonb NOT NULL, features jsonb NOT NULL, thresholds jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS outcomes (
  date date PRIMARY KEY,
  airport_outcome text CHECK (airport_outcome IN ('cloud_sea','no_sea')),
  evidence text, dawn jsonb, graded_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS photos (
  id text PRIMARY KEY, date date NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  image bytea NOT NULL, taken_at timestamptz NOT NULL, gps_present boolean NOT NULL, distance_km real,
  ip_hash text NOT NULL, token_hash text NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  rating jsonb, rated_at timestamptz, attempts int NOT NULL DEFAULT 0,
  confirmed_label text, confirmed_at timestamptz, public boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS photos_date ON photos(date);
CREATE TABLE IF NOT EXISTS going (date date NOT NULL, ip_hash text NOT NULL, at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (date, ip_hash));
CREATE TABLE IF NOT EXISTS train_rows (date date PRIMARY KEY, features jsonb NOT NULL, y real,
  added_at timestamptz NOT NULL DEFAULT now())
"""
SCHEMA_LOCK = 0x0C10D5EA        # advisory lock so the API and a job can both run init_schema at once

CALL_COLUMNS = ["date", "issued_at", "verdict", "probability", "sunrise", "first_light", "text", "text_source",
                "text_kn", "text_hi", "carry", "conditions", "leave_by", "gate", "model", "features",
                "thresholds"]
CALL_JSON = {"carry", "conditions", "leave_by", "gate", "model", "features", "thresholds"}
CALL_OPTIONAL = {"text_kn", "text_hi"}

SEA_LABELS = {"cloud_sea", "partial"}          # photo labels that mean "there was a layer below"
NO_SEA_LABELS = {"clear_no_sea", "socked_in"}


# --- plumbing -----------------------------------------------------------------------------------------

def connect(url: str | None = None) -> psycopg.Connection:
    url = url or settings.DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=10)


def init_schema(conn: psycopg.Connection) -> None:
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK,))
        for stmt in SCHEMA.split(";"):
            if stmt.strip():
                conn.execute(stmt)


def _plain(obj: Any) -> Any:
    """JSON-safe copy: numpy scalars/arrays to Python, NaN/inf to None, dates to ISO strings."""
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if hasattr(obj, "tolist") and not isinstance(obj, (str, bytes)):     # numpy array or scalar
        return _plain(obj.tolist())
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


def _jsonb(obj: Any) -> Jsonb | None:
    return None if obj is None else Jsonb(_plain(obj), dumps=lambda o: json.dumps(o, allow_nan=False))


def _num(x: Any) -> float | None:
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def _round(p: float | None, nd: int = 4) -> float | None:
    """`real` columns come back as float4 noise (0.08 -> 0.07999999821); round them for display."""
    return None if p is None else round(float(p), nd)


def is_correct(verdict: str, airport_outcome: str | None) -> bool | None:
    """GO and MAYBE are right on a cloud sea; SKIP is right on no sea. Unknown outcome: None."""
    if airport_outcome is None:
        return None
    if verdict in ("GO", "MAYBE"):
        return airport_outcome == "cloud_sea"
    return airport_outcome == "no_sea"


def photo_agrees(airport_outcome: str | None, photo_majority: str | None) -> bool | None:
    if airport_outcome is None or photo_majority is None:
        return None
    if photo_majority in SEA_LABELS:
        return airport_outcome == "cloud_sea"
    if photo_majority in NO_SEA_LABELS:
        return airport_outcome == "no_sea"
    return None


# --- calls --------------------------------------------------------------------------------------------

def upsert_call(conn: psycopg.Connection, call: dict) -> None:
    values = {}
    for c in CALL_COLUMNS:
        v = call.get(c) if c in CALL_OPTIONAL else call[c]
        if c in CALL_JSON:
            v = _jsonb(v)
        elif c == "probability":
            v = _num(v)
        values[c] = v
    cols = sql.SQL(", ").join(map(sql.Identifier, CALL_COLUMNS))
    params = sql.SQL(", ").join(sql.Placeholder(c) for c in CALL_COLUMNS)
    updates = sql.SQL(", ").join(sql.SQL("{0} = EXCLUDED.{0}").format(sql.Identifier(c))
                                 for c in CALL_COLUMNS if c != "date")
    conn.execute(sql.SQL("INSERT INTO calls ({}) VALUES ({}) ON CONFLICT (date) DO UPDATE SET {}")
                 .format(cols, params, updates), values)


def _call_row(row: dict | None) -> dict | None:
    if row is not None:
        row["probability"] = _round(row["probability"])
    return row


def get_call(conn: psycopg.Connection, day: date) -> dict | None:
    return _call_row(conn.execute("SELECT * FROM calls WHERE date = %s", (day,)).fetchone())


def latest_call(conn: psycopg.Connection) -> dict | None:
    return _call_row(conn.execute("SELECT * FROM calls ORDER BY date DESC LIMIT 1").fetchone())


# --- outcomes and photo summaries ---------------------------------------------------------------------

def upsert_outcome(conn: psycopg.Connection, day: date, airport_outcome: str | None, evidence: str,
                   dawn: dict) -> None:
    conn.execute(
        """INSERT INTO outcomes (date, airport_outcome, evidence, dawn, graded_at) VALUES (%s, %s, %s, %s, now())
           ON CONFLICT (date) DO UPDATE SET airport_outcome = EXCLUDED.airport_outcome,
             evidence = EXCLUDED.evidence, dawn = EXCLUDED.dawn, graded_at = EXCLUDED.graded_at""",
        (day, airport_outcome, evidence, _jsonb(dawn)))


def _votes(conn: psycopg.Connection, day: date | None = None) -> dict[date, tuple[int, Counter]]:
    """Per date: (confirmed photos, Counter of labels with one vote per uploader, their latest confirmation)."""
    where = "confirmed_label IS NOT NULL" + (" AND date = %(day)s" if day is not None else "")
    params = {"day": day} if day is not None else None
    out: dict[date, tuple[int, Counter]] = {
        r["date"]: (r["n"], Counter()) for r in conn.execute(
            f"SELECT date, count(*) AS n FROM photos WHERE {where} GROUP BY date", params)}
    for r in conn.execute(
            f"""SELECT DISTINCT ON (date, ip_hash) date, confirmed_label FROM photos
                WHERE {where} ORDER BY date, ip_hash, confirmed_at DESC""", params):
        out[r["date"]][1][r["confirmed_label"]] += 1
    return out


def _majority(counts: Counter) -> str | None:
    """The label with the most votes; None when there are no votes or the top is tied."""
    top = counts.most_common(2)
    if not top or (len(top) == 2 and top[0][1] == top[1][1]):
        return None
    return top[0][0]


def photo_summary(conn: psycopg.Connection, day: date) -> dict:
    """{"photos": confirmed photos, "majority": label or None, "counts": {label: votes}}.

    Votes count one per uploader (salted IP hash, their latest confirmed photo of the day), so one person
    uploading five photos can't outvote the others. `photos` counts every confirmed photo.
    """
    n, counts = _votes(conn, day).get(day, (0, Counter()))
    return {"photos": n, "majority": _majority(counts), "counts": dict(counts)}


# --- training rows ------------------------------------------------------------------------------------

def upsert_train_row(conn: psycopg.Connection, day: date, features: dict, y: float | None) -> None:
    conn.execute(
        """INSERT INTO train_rows (date, features, y) VALUES (%s, %s, %s)
           ON CONFLICT (date) DO UPDATE SET features = EXCLUDED.features, y = EXCLUDED.y, added_at = now()""",
        (day, _jsonb(features), _num(y)))


def train_rows(conn: psycopg.Connection) -> list[dict]:
    """All rows oldest first: {"date", "features", "y", "added_at"}. Missing feature values come back as None."""
    return conn.execute("SELECT date, features, y, added_at FROM train_rows ORDER BY date").fetchall()


# --- scoreboard ---------------------------------------------------------------------------------------

def scoreboard(conn: psycopg.Connection, today: date | None = None) -> dict:
    """The GET /api/scoreboard body (JSON-ready). Days are live calls up to today (IST), newest first.

    A day is graded when it has a call and an outcome with a known airport result. `correct` follows
    `is_correct`. Photo agreement compares the photo majority (cloud_sea/partial vs clear_no_sea/socked_in)
    with the airport result. Brier is over graded days.
    """
    today = today or datetime.now(IST).date()
    rows = conn.execute(
        """SELECT c.date, c.verdict, c.probability, o.airport_outcome, o.evidence, o.graded_at
           FROM calls c LEFT JOIN outcomes o ON o.date = c.date
           WHERE c.date <= %s ORDER BY c.date DESC""", (today,)).fetchall()
    votes = _votes(conn)
    days, graded, sq_err = [], [], []
    with_both = agree = 0
    for r in rows:
        n, counts = votes.get(r["date"], (0, Counter()))
        majority = _majority(counts)
        correct = is_correct(r["verdict"], r["airport_outcome"])
        p = _round(r["probability"])
        days.append({"date": r["date"].isoformat(), "verdict": r["verdict"], "probability": p,
                     "airport_outcome": r["airport_outcome"], "photo_outcome": majority, "photos": n,
                     "correct": correct, "evidence": r["evidence"]})
        if r["airport_outcome"] is not None:
            graded.append(days[-1])
            sq_err.append((p - (1.0 if r["airport_outcome"] == "cloud_sea" else 0.0)) ** 2)
        a = photo_agrees(r["airport_outcome"], majority)
        if a is not None:
            with_both += 1
            agree += a
    summary = {
        "graded": len(graded),
        "correct": sum(1 for d in graded if d["correct"]),
        "go_calls": sum(1 for d in graded if d["verdict"] == "GO"),
        "go_hits": sum(1 for d in graded if d["verdict"] == "GO" and d["airport_outcome"] == "cloud_sea"),
        "brier": round(sum(sq_err) / len(sq_err), 3) if sq_err else None,
        "since": graded[-1]["date"] if graded else None,
    }
    return {"summary": summary, "days": days,
            "agreement": {"days_with_both": with_both, "airport_and_photos_agree": agree}}


def last_graded(conn: psycopg.Connection) -> dict | None:
    """The most recent call with an outcome row: the `last_graded` block of GET /api/today."""
    r = conn.execute(
        """SELECT c.date, c.verdict, c.probability, o.airport_outcome FROM calls c JOIN outcomes o ON o.date = c.date
           ORDER BY c.date DESC LIMIT 1""").fetchone()
    if r is None:
        return None
    s = photo_summary(conn, r["date"])
    return {"date": r["date"].isoformat(), "verdict": r["verdict"], "probability": _round(r["probability"]),
            "airport_outcome": r["airport_outcome"], "photo_outcome": s["majority"],
            "correct": is_correct(r["verdict"], r["airport_outcome"])}


# --- going --------------------------------------------------------------------------------------------

def add_going(conn: psycopg.Connection, day: date, ip_hash: str) -> int:
    conn.execute("INSERT INTO going (date, ip_hash) VALUES (%s, %s) ON CONFLICT DO NOTHING", (day, ip_hash))
    return going_count(conn, day)


def going_count(conn: psycopg.Connection, day: date) -> int:
    return conn.execute("SELECT count(*) AS n FROM going WHERE date = %s", (day,)).fetchone()["n"]


# --- photos -------------------------------------------------------------------------------------------

def uploads_since(conn: psycopg.Connection, ip_hash: str, since: datetime) -> int:
    return conn.execute("SELECT count(*) AS n FROM photos WHERE ip_hash = %s AND created_at >= %s",
                        (ip_hash, since)).fetchone()["n"]


def lock_uploader(conn: psycopg.Connection, ip_hash: str) -> None:
    """Serialise concurrent uploads from one uploader inside the current transaction (for the daily limit)."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (ip_hash,))


def insert_photo(conn: psycopg.Connection, *, id: str, day: date, image: bytes, taken_at: datetime,
                 gps_present: bool, distance_km: float | None, ip_hash: str, token_hash: str,
                 public: bool) -> None:
    conn.execute(
        """INSERT INTO photos (id, date, image, taken_at, gps_present, distance_km, ip_hash, token_hash, public)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (id, day, image, taken_at, gps_present, _num(distance_km), ip_hash, token_hash, public))


PHOTO_META = "id, date, status, rating, confirmed_label, public, token_hash"


def get_photo(conn: psycopg.Connection, photo_id: str) -> dict | None:
    return conn.execute(f"SELECT {PHOTO_META} FROM photos WHERE id = %s", (photo_id,)).fetchone()


def get_photo_image(conn: psycopg.Connection, photo_id: str) -> dict | None:
    return conn.execute("SELECT image, public, token_hash FROM photos WHERE id = %s", (photo_id,)).fetchone()


def confirm_photo(conn: psycopg.Connection, photo_id: str, label: str, public: bool | None) -> dict | None:
    """Set the uploader's label. `public` overrides the upload-time choice; None keeps it."""
    return conn.execute(
        f"""UPDATE photos SET confirmed_label = %s, confirmed_at = now(), public = COALESCE(%s, public)
            WHERE id = %s RETURNING {PHOTO_META}""", (label, public, photo_id)).fetchone()


def gallery(conn: psycopg.Connection, limit: int = 60) -> list[dict]:
    return conn.execute(
        """SELECT id, date, confirmed_label AS label FROM photos
           WHERE public AND confirmed_label IS NOT NULL ORDER BY created_at DESC LIMIT %s""", (limit,)).fetchall()


def claim_photo_for_rating(conn: psycopg.Connection, max_attempts: int) -> dict | None:
    """Take the oldest queued photo and count the attempt up front, so a crash mid-rating still counts."""
    return conn.execute(
        """UPDATE photos SET attempts = attempts + 1
           WHERE id = (SELECT id FROM photos WHERE status = 'queued' AND attempts < %s
                       ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
           RETURNING id, image, attempts""", (max_attempts,)).fetchone()


def save_rating(conn: psycopg.Connection, photo_id: str, rating: dict) -> None:
    conn.execute("UPDATE photos SET status = 'rated', rating = %s, rated_at = now() WHERE id = %s",
                 (_jsonb(rating), photo_id))


def mark_rating_failed(conn: psycopg.Connection, photo_id: str) -> None:
    conn.execute("UPDATE photos SET status = 'failed' WHERE id = %s", (photo_id,))
