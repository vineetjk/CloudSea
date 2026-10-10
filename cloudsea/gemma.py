"""Small Ollama client for Gemma 4. Thinking is off: on CPU it costs 5x the time and made answers worse (Phase 0)."""
from __future__ import annotations

import httpx

from cloudsea import settings


def chat(messages: list[dict], timeout: float = 300, **body) -> dict:
    """POST /api/chat and return the response JSON. Extra keyword args go into the request body."""
    payload = {"model": settings.GEMMA_MODEL, "messages": messages, "stream": False, "think": False, **body}
    with httpx.Client(base_url=settings.OLLAMA_URL, timeout=timeout) as http:
        r = http.post("/api/chat", json=payload)
        r.raise_for_status()
        return r.json()


def available(timeout: float = 5) -> bool:
    try:
        with httpx.Client(base_url=settings.OLLAMA_URL, timeout=timeout) as http:
            names = [m["name"] for m in http.get("/api/tags").json().get("models", [])]
        return settings.GEMMA_MODEL in names
    except httpx.HTTPError:
        return False
