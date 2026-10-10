"""Background photo rating: one thread, one photo at a time, woken by an upload or every 120 s.

Gemma on CPU takes 15-60 s per photo, so rating never happens inside a request. An attempt is counted when a
photo is claimed, so a crash mid-rating still counts. After 3 failed attempts the photo is marked 'failed';
the uploader can still confirm a label themselves. When Gemma is unreachable the sweep is skipped without
using up attempts.
"""
from __future__ import annotations

import logging
import threading

from cloudsea import db, gemma, rater

log = logging.getLogger("cloudsea.api.sweeper")

INTERVAL_S = 120
MAX_ATTEMPTS = 3


def rate_one() -> str | None:
    """Rate the oldest queued photo. Returns its id, or None when nothing was waiting."""
    with db.connect() as conn:
        photo = db.claim_photo_for_rating(conn, MAX_ATTEMPTS)
    if photo is None:
        return None
    try:
        rating = rater.rate_photo(bytes(photo["image"]))
    except Exception as exc:  # noqa: BLE001 - any rater failure is retried, then given up on
        log.warning("rating %s failed (attempt %d): %s", photo["id"], photo["attempts"], exc)
        if photo["attempts"] >= MAX_ATTEMPTS:
            with db.connect() as conn:
                db.mark_rating_failed(conn, photo["id"])
        return photo["id"]
    with db.connect() as conn:
        db.save_rating(conn, photo["id"], rating)
    log.info("rated %s: %s", photo["id"], rating.get("label"))
    return photo["id"]


def sweep(limit: int = 50) -> int:
    """Rate queued photos until none are left (or `limit`). Returns how many were attempted."""
    if not gemma.available(timeout=5):
        log.info("Gemma is not reachable; leaving photos queued")
        return 0
    n = 0
    while n < limit and rate_one() is not None:
        n += 1
    return n


class Sweeper:
    def __init__(self, interval_s: float = INTERVAL_S):
        self.interval_s = interval_s
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="photo-sweeper", daemon=True)
        self._thread.start()
        self.kick()                   # pick up anything left queued before a restart

    def kick(self) -> None:
        self._wake.set()

    def stop(self, timeout: float = 2) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.interval_s)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                sweep()
            except Exception:  # noqa: BLE001 - keep the thread alive through database hiccups
                log.exception("photo sweep failed")
