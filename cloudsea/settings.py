"""Configuration from environment variables (a local .env is loaded if present). Secrets never live in code."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma4:e2b-it-q4_K_M")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DATA_DIR = ROOT / "data"
