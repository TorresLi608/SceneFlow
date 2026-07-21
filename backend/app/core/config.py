from __future__ import annotations

import hashlib
import os
from pathlib import Path


PORT = os.getenv("PORT", "8080")
DB_PATH = os.getenv("SCENEFLOW_DB_PATH", "./sceneflow.db")
ENVIRONMENT = os.getenv("SCENEFLOW_ENV", "development").strip().lower()
JWT_SECRET = os.getenv("SCENEFLOW_JWT_SECRET", "dev-jwt-secret-change-me-at-least-32-bytes")
AES_SECRET = os.getenv("SCENEFLOW_AES_KEY", "dev-aes-key-change-me")
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
    for origin in os.getenv("SCENEFLOW_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if origin.strip()
]
GENERATED_DIR = Path(os.getenv("SCENEFLOW_GENERATED_DIR", "./generated"))
PRIVATE_GENERATED_DIR = Path(os.getenv("SCENEFLOW_PRIVATE_GENERATED_DIR", "./private_generated"))
CJK_FONT_PATH = os.getenv("SCENEFLOW_CJK_FONT_PATH", "").strip()
CJK_FONT_NAME = os.getenv("SCENEFLOW_CJK_FONT_NAME", "Arial Unicode MS").strip() or "Arial Unicode MS"
MAX_CONTEXT_TOKENS = max(10_000, int(os.getenv("SCENEFLOW_MAX_CONTEXT_TOKENS", "100000")))
