from __future__ import annotations

from typing import Any

import bcrypt
from fastapi import APIRouter, HTTPException

from database import db, row
from security import token_for
from serializers import user_json
from utils import now


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(payload: dict[str, Any]) -> dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if not 3 <= len(username) <= 64 or not 6 <= len(password) <= 128:
        raise HTTPException(400, "invalid username or password length")
    stamp = now()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db() as conn:
        if row(conn, "SELECT id FROM users WHERE username=? AND deleted_at IS NULL", (username,)):
            raise HTTPException(409, "username already exists")
        cur = conn.execute(
            "INSERT INTO users (created_at, updated_at, username, password) VALUES (?, ?, ?, ?)",
            (stamp, stamp, username, hashed),
        )
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
    return {"token": token_for(user["id"]), "user": user_json(user)}
