from __future__ import annotations

import base64
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, Header, HTTPException

from config import AES_KEY, JWT_SECRET
from database import db, row


def encrypt(value: str) -> str:
    nonce = secrets.token_bytes(12)
    return base64.b64encode(nonce + AESGCM(AES_KEY).encrypt(nonce, value.encode(), None)).decode()


def decrypt(value: str) -> str:
    raw = base64.b64decode(value)
    return AESGCM(AES_KEY).decrypt(raw[:12], raw[12:], None).decode()


def token_for(user_id: int) -> str:
    issued = datetime.now(timezone.utc)
    return jwt.encode({"userId": user_id, "iat": issued, "exp": issued + timedelta(hours=24)}, JWT_SECRET, algorithm="HS256")


def user_id_from_token(token: str) -> int:
    return int(jwt.decode(token, JWT_SECRET, algorithms=["HS256"])["userId"])


def current_user_id(authorization: str | None = Header(default=None)) -> int:
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise HTTPException(401, "missing token")
    try:
        user_id = user_id_from_token(token)
    except Exception as exc:
        raise HTTPException(401, "invalid token") from exc
    with db() as conn:
        user = row(conn, "SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (user_id,))
    if not user:
        raise HTTPException(401, "user not found")
    if bool(user["is_disabled"]):
        raise HTTPException(403, "user is disabled")
    return user_id


def current_super_admin_id(user_id: int = Depends(current_user_id)) -> int:
    with db() as conn:
        user = row(conn, "SELECT role FROM users WHERE id=? AND deleted_at IS NULL", (user_id,))
    if not user or user["role"] != "superAdmin":
        raise HTTPException(403, "superAdmin required")
    return user_id
