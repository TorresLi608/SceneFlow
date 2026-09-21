from __future__ import annotations

import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


PORT = os.getenv("PORT", "8080")
DATABASE_URL = make_url(
    os.getenv("DATABASE_URL")
    or URL.create(
        "sqlite",
        database=str(Path(__file__).resolve().parents[3] / "data" / "app.db"),
    )
)
if DATABASE_URL.get_backend_name() != "sqlite" or DATABASE_URL.query.get("uri", "").lower() in {"true", "1"}:
    raise RuntimeError("DATABASE_URL must use a SQLite file URL (sqlite:///...) or sqlite:///:memory:")
DB_PATH = DATABASE_URL.database or ":memory:"
ENVIRONMENT = os.getenv("SCENEFLOW_ENV", "development").strip().lower()
JWT_SECRET = os.getenv("SCENEFLOW_JWT_SECRET", "dev-jwt-secret-change-me-at-least-32-bytes")
AES_SECRET = os.getenv("SCENEFLOW_AES_KEY", "dev-aes-key-change-me")
SUPER_ADMIN_USERNAME = os.getenv("SCENEFLOW_SUPER_ADMIN_USERNAME", "superAdmin").strip()
if not 3 <= len(SUPER_ADMIN_USERNAME) <= 64:
    raise RuntimeError("SCENEFLOW_SUPER_ADMIN_USERNAME must be between 3 and 64 characters")
SUPER_ADMIN_PASSWORD = os.getenv("SCENEFLOW_SUPER_ADMIN_PASSWORD", "superAdmin@123")
if ENVIRONMENT == "production" and (
    JWT_SECRET == "dev-jwt-secret-change-me-at-least-32-bytes"
    or AES_SECRET == "dev-aes-key-change-me"
    or SUPER_ADMIN_PASSWORD == "superAdmin@123"
):
    raise RuntimeError("production requires SCENEFLOW_JWT_SECRET, SCENEFLOW_AES_KEY, and SCENEFLOW_SUPER_ADMIN_PASSWORD")
AES_KEY = hashlib.sha256(AES_SECRET.encode()).digest()
PUBLIC_BASE_URL = os.getenv("SCENEFLOW_PUBLIC_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("SCENEFLOW_CORS_ORIGINS", "http://localhost:4000,http://127.0.0.1:4000").split(",")
    if origin.strip()
]
PRIVATE_GENERATED_DIR = Path(
    os.getenv(
        "SCENEFLOW_PRIVATE_GENERATED_DIR",
        str(Path(__file__).resolve().parents[3] / "data" / "private_generated"),
    )
)
CJK_FONT_PATH = os.getenv("SCENEFLOW_CJK_FONT_PATH", "").strip()
CJK_FONT_NAME = os.getenv("SCENEFLOW_CJK_FONT_NAME", "Arial Unicode MS").strip() or "Arial Unicode MS"
MAX_CONTEXT_TOKENS = max(10_000, int(os.getenv("SCENEFLOW_MAX_CONTEXT_TOKENS", "100000")))
LOG_LEVEL = os.getenv("SCENEFLOW_LOG_LEVEL", "INFO").strip().upper()
SEARXNG_BASE_URL = (
    os.getenv("SCENEFLOW_SEARXNG_BASE_URL", "")
    or os.getenv("SEARXNG_BASE_URL", "")
).strip().rstrip("/")
SEARXNG_ENGINE_TOKEN = (
    os.getenv("SCENEFLOW_SEARXNG_ENGINE_TOKEN", "")
    or os.getenv("SCENEFLOW_SEARXNG_TOKEN", "")
    or os.getenv("SEARXNG_TOKEN", "")
).strip()
SEARXNG_ENGINES = (
    os.getenv("SCENEFLOW_SEARXNG_ENGINES", "")
    or os.getenv("SEARXNG_ENGINES", "")
).strip()
SEARXNG_RESULT_COUNT = max(1, min(10, int(os.getenv("SCENEFLOW_SEARXNG_RESULT_COUNT", "4"))))
SEARXNG_MAX_SNIPPET_CHARS = max(50, min(1000, int(os.getenv("SCENEFLOW_SEARXNG_MAX_SNIPPET_CHARS", "180"))))
SEARXNG_MAX_TOTAL_CHARS = max(200, min(5000, int(os.getenv("SCENEFLOW_SEARXNG_MAX_TOTAL_CHARS", "900"))))
CRAWL4AI_BASE_URL = (
    os.getenv("SCENEFLOW_CRAWL4AI_BASE_URL", "")
    or os.getenv("CRAWL4AI_BASE_URL", "")
).strip().rstrip("/")
CRAWL4AI_API_TOKEN = (
    os.getenv("SCENEFLOW_CRAWL4AI_API_TOKEN", "")
    or os.getenv("CRAWL4AI_API_TOKEN", "")
).strip()
CRAWL4AI_MAX_CHARS = max(500, min(10000, int(os.getenv("SCENEFLOW_CRAWL4AI_MAX_CHARS", "2000"))))
