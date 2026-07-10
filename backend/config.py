from __future__ import annotations

import hashlib
import os
from pathlib import Path


PORT = os.getenv("PORT", "8080")
DB_PATH = os.getenv("SCENEFLOW_DB_PATH", "./sceneflow.db")
JWT_SECRET = os.getenv("SCENEFLOW_JWT_SECRET", "dev-jwt-secret-change-me")
AES_KEY = hashlib.sha256(os.getenv("SCENEFLOW_AES_KEY", "dev-aes-key-change-me").encode()).digest()
PUBLIC_BASE_URL = os.getenv("SCENEFLOW_PUBLIC_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
GENERATED_DIR = Path(os.getenv("SCENEFLOW_GENERATED_DIR", "./generated"))
PRIVATE_GENERATED_DIR = Path(os.getenv("SCENEFLOW_PRIVATE_GENERATED_DIR", "./private_generated"))
CJK_FONT_PATH = os.getenv("SCENEFLOW_CJK_FONT_PATH", "").strip()
CJK_FONT_NAME = os.getenv("SCENEFLOW_CJK_FONT_NAME", "Arial Unicode MS").strip() or "Arial Unicode MS"
