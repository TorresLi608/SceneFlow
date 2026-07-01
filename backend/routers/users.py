from __future__ import annotations

import sqlite3
from typing import Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException

from database import db, row
from security import current_user_id
from serializers import user_json
from utils import now


router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me")
def get_me(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        user = row(conn, "SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (user_id,))
    if not user:
        raise HTTPException(401, "user not found")
    return {"user": user_json(user)}


@router.patch("/me")
def update_me(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    updates, args = [], []
    if "username" in payload:
        username = str(payload["username"]).strip()
        if not 3 <= len(username) <= 64:
            raise HTTPException(400, "username length must be between 3 and 64")
        updates.append("username=?")
        args.append(username)
    if "password" in payload:
        password = str(payload["password"])
        if not 6 <= len(password) <= 128:
            raise HTTPException(400, "password length must be between 6 and 128")
        updates.append("password=?")
        args.append(bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode())
    if not updates:
        raise HTTPException(400, "no fields to update")
    with db() as conn:
        try:
            conn.execute(
                f"UPDATE users SET {', '.join(updates)}, updated_at=? WHERE id=? AND deleted_at IS NULL",
                (*args, now(), user_id),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "username already exists") from exc
        user = row(conn, "SELECT * FROM users WHERE id=?", (user_id,))
    return {"user": user_json(user)}


@router.delete("/me", status_code=204)
def delete_me(user_id: int = Depends(current_user_id)) -> None:
    with db() as conn:
        conn.execute("UPDATE users SET deleted_at=?, updated_at=? WHERE id=? AND deleted_at IS NULL", (now(), now(), user_id))
