from __future__ import annotations

import sqlite3
from typing import Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException

from app.core.database import db, row
from app.api.deps import current_user_id
from app.schemas.serializers import user_json
from app.utils.common import now


router = APIRouter(prefix="/api/users", tags=["users"])


def user_profile(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return row(
        conn,
        """SELECT users.*, COUNT(usage_logs.id) AS request_count,
        COALESCE(SUM(usage_logs.cost_micros), 0) AS historical_cost_micros
        FROM users
        LEFT JOIN usage_logs ON usage_logs.user_id=users.id
        WHERE users.id=? AND users.deleted_at IS NULL
        GROUP BY users.id""",
        (user_id,),
    )


@router.get("/me")
def get_me(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        user = user_profile(conn, user_id)
    if not user:
        raise HTTPException(401, "user not found")
    return {"user": user_json(user)}


@router.post("/redeem")
def redeem_code(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    code = str(payload.get("code") or "").strip().upper()
    if not 4 <= len(code) <= 64:
        raise HTTPException(400, "invalid redemption code")
    stamp = now()
    with db() as conn:
        redemption = row(conn, "SELECT * FROM redemption_codes WHERE code=?", (code,))
        if not redemption:
            raise HTTPException(404, "redemption code not found")
        if redemption["redeemed_at"]:
            raise HTTPException(409, "redemption code already redeemed")
        if redemption["expires_at"] <= stamp:
            raise HTTPException(410, "redemption code expired")
        redeemed = conn.execute(
            """UPDATE redemption_codes SET redeemed_at=?, redeemed_by_user_id=?
            WHERE id=? AND redeemed_at IS NULL AND expires_at>?""",
            (stamp, user_id, redemption["id"], stamp),
        )
        if redeemed.rowcount != 1:
            raise HTTPException(409, "redemption code is no longer available")
        conn.execute(
            "UPDATE users SET balance_micros=balance_micros+?, updated_at=? WHERE id=?",
            (redemption["amount_micros"], stamp, user_id),
        )
        user = user_profile(conn, user_id)
    return {"amountMicros": str(redemption["amount_micros"]), "user": user_json(user)}


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
        current_password = str(payload.get("currentPassword", ""))
        password = str(payload["password"])
        if not 1 <= len(current_password) <= 128:
            raise HTTPException(400, "current password is invalid")
        if not 6 <= len(password) <= 128:
            raise HTTPException(400, "password length must be between 6 and 128")
        if len(password.encode()) > 72:
            raise HTTPException(400, "password must be at most 72 bytes")
    if not updates and "password" not in payload:
        raise HTTPException(400, "no fields to update")
    with db() as conn:
        if "password" in payload:
            user = row(conn, "SELECT password FROM users WHERE id=? AND deleted_at IS NULL", (user_id,))
            try:
                password_matches = bool(user) and bcrypt.checkpw(current_password.encode(), user["password"].encode())
            except ValueError:
                password_matches = False
            if not password_matches:
                raise HTTPException(400, "current password is incorrect")
            updates.append("password=?")
            args.append(bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode())
        try:
            conn.execute(
                f"UPDATE users SET {', '.join(updates)}, updated_at=? WHERE id=? AND deleted_at IS NULL",
                (*args, now(), user_id),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "username already exists") from exc
        user = user_profile(conn, user_id)
    return {"user": user_json(user)}


@router.delete("/me", status_code=204)
def delete_me(user_id: int = Depends(current_user_id)) -> None:
    with db() as conn:
        conn.execute("UPDATE users SET deleted_at=?, updated_at=? WHERE id=? AND deleted_at IS NULL", (now(), now(), user_id))
