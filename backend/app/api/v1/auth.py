from __future__ import annotations

import sqlite3
from typing import Any

import bcrypt
from fastapi import APIRouter, HTTPException

from app.core.database import db, row
from app.core.security import token_for
from app.schemas.serializers import user_json
from app.utils.common import now


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(payload: dict[str, Any]) -> dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    invitation_code = str(payload.get("invitationCode", "")).strip().upper()
    if not 3 <= len(username) <= 64 or not 6 <= len(password) <= 128:
        raise HTTPException(400, "invalid username or password length")
    if not invitation_code:
        raise HTTPException(400, "invitation code required")
    stamp = now()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db() as conn:
        invitation = row(conn, "SELECT * FROM invitation_codes WHERE code=?", (invitation_code,))
        if not invitation:
            raise HTTPException(400, "invalid invitation code")
        if invitation["used_at"]:
            raise HTTPException(409, "invitation code already used")
        if invitation["expires_at"] <= stamp:
            raise HTTPException(410, "invitation code expired")
        if row(conn, "SELECT id FROM users WHERE username=? AND deleted_at IS NULL", (username,)):
            raise HTTPException(409, "username already exists")
        try:
            cur = conn.execute(
                "INSERT INTO users (created_at, updated_at, username, password, role, is_disabled) VALUES (?, ?, ?, ?, 'user', 0)",
                (stamp, stamp, username, hashed),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "username already exists") from exc
        consumed = conn.execute(
            "UPDATE invitation_codes SET used_at=?, used_by_user_id=? WHERE id=? AND used_at IS NULL AND expires_at>?",
            (stamp, cur.lastrowid, invitation["id"], stamp),
        )
        if consumed.rowcount != 1:
            raise HTTPException(409, "invitation code is no longer available")
        user = row(conn, "SELECT * FROM users WHERE id=?", (cur.lastrowid,))
        return {"token": token_for(user["id"]), "user": user_json(user)}


@router.post("/login")
def login(payload: dict[str, Any]) -> dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    with db() as conn:
        user = row(conn, "SELECT * FROM users WHERE username=? AND deleted_at IS NULL", (username,))
    if not user or not bcrypt.checkpw(password.encode(), user["password"].encode()):
        raise HTTPException(401, "invalid credentials")
    if bool(user["is_disabled"]):
        raise HTTPException(403, "user is disabled")
    return {"token": token_for(user["id"]), "user": user_json(user)}
