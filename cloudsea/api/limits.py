"""Client identity without storing IPs: a salted SHA-256 of the address, plus a small in-memory POST limiter."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import threading
import time

from starlette.requests import Request

log = logging.getLogger("cloudsea.api")

DEV_SALT = "cloudsea-dev-salt-not-for-production"
POSTS_PER_MINUTE = 30


def ip_salt() -> str:
    salt = os.environ.get("IP_SALT", "")
    if not salt:
        if not getattr(ip_salt, "_warned", False):
            log.warning("IP_SALT is not set; using the development salt. Set IP_SALT in production.")
            ip_salt._warned = True  # type: ignore[attr-defined]
        return DEV_SALT
    return salt


def client_ip(request: Request) -> str:
    """First X-Forwarded-For entry (Render's proxy puts the client there), else the socket peer."""
    xff = request.headers.get("x-forwarded-for", "")
    first = xff.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"


def ip_hash(request: Request) -> str:
    return hashlib.sha256((ip_salt() + client_ip(request)).encode()).hexdigest()


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def token_matches(token: str | None, token_hash: str) -> bool:
    """Constant-time comparison of the token's hash with the stored hash."""
    if not token:
        return False
    return hmac.compare_digest(sha256_hex(token), token_hash)


class MinuteLimiter:
    """Fixed one-minute windows per key. Process-local: a backstop under the database limits, not a fence."""

    def __init__(self, per_minute: int = POSTS_PER_MINUTE):
        self.per_minute = per_minute
        self._lock = threading.Lock()
        self._window = 0
        self._counts: dict[str, int] = {}

    def allow(self, key: str) -> bool:
        window = int(time.monotonic() // 60)
        with self._lock:
            if window != self._window:
                self._window, self._counts = window, {}
            n = self._counts.get(key, 0) + 1
            self._counts[key] = n
            return n <= self.per_minute

    def reset(self) -> None:
        with self._lock:
            self._counts = {}
