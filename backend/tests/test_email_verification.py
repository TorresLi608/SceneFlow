"""Tests for email verification code generation, expiration, cooldown, and registration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.admin import create_invitation_code
from app.core import database
from app.core.database import db, init_db
from app.models import EmailVerification, User
from app.services.verification_service import (
    send_registration_code,
    verify_and_consume_code,
)
from sqlmodel import select


def test_email_verification_flow_and_cooldown() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "test_email.db"
        try:
            init_db()

            # 1. 正常发送验证码
            with db() as session:
                verification = send_registration_code(session, "user1@example.com")
                assert len(verification.code) == 6
                assert verification.code.isdigit()
                assert verification.used_at is None

            # 2. 60秒内重复发送触发 429
            with db() as session:
                try:
                    send_registration_code(session, "user1@example.com")
                    raise AssertionError("should raise 429 on cooldown")
                except HTTPException as exc:
                    assert exc.status_code == 429
                    assert "60" in exc.detail

            # 3. 错误验证码拒绝
            with db() as session:
                try:
                    verify_and_consume_code(session, "user1@example.com", "000000")
                    raise AssertionError("invalid code should fail")
                except HTTPException as exc:
                    assert exc.status_code == 400

            # 4. 正确验证码核销成功
            with db() as session:
                verify_and_consume_code(session, "user1@example.com", verification.code)
                consumed = session.get(EmailVerification, verification.id)
                assert consumed is not None
                assert consumed.used_at is not None

            # 5. 已使用的验证码无法重复使用
            with db() as session:
                try:
                    verify_and_consume_code(session, "user1@example.com", verification.code)
                    raise AssertionError("used code cannot be reused")
                except HTTPException as exc:
                    assert exc.status_code == 400
        finally:
            database.DB_PATH = original_path


def test_email_verification_expired_code() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "test_email_expired.db"
        try:
            init_db()

            with db() as session:
                # 构造一个 6 分钟前创建、已过期的验证码
                expired_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
                created_time = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
                v = EmailVerification(
                    created_at=created_time,
                    expires_at=expired_time,
                    email="expired@example.com",
                    code="123456",
                )
                session.add(v)
                session.flush()

            with db() as session:
                try:
                    verify_and_consume_code(session, "expired@example.com", "123456")
                    raise AssertionError("expired code should be rejected")
                except HTTPException as exc:
                    assert exc.status_code == 400
                    assert "已过期" in exc.detail
        finally:
            database.DB_PATH = original_path


def test_email_registration_via_api() -> None:
    from app.main import app

    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "test_email_api.db"
        try:
            init_db()
            invitation = create_invitation_code({"days": 7}, 1)["invitationCode"]

            with TestClient(app) as client:
                # 1. 获取验证码
                res = client.post("/api/auth/send-verification-code", json={"email": "newuser@example.com"})
                assert res.status_code == 200
                assert res.json()["success"] is True

                # 查询获取数据库中的验证码
                with db() as session:
                    v = session.exec(
                        select(EmailVerification).where(EmailVerification.email == "newuser@example.com")
                    ).first()
                    assert v is not None
                    code = v.code

                # 2. 注册新用户
                reg_res = client.post(
                    "/api/auth/register",
                    json={
                        "username": "newuser",
                        "nickname": "新用户",
                        "email": "newuser@example.com",
                        "verificationCode": code,
                        "password": "securepassword123",
                        "invitationCode": invitation["code"],
                    },
                )
                assert reg_res.status_code == 201, reg_res.text
                data = reg_res.json()
                assert data["user"]["email"] == "newuser@example.com"
                assert data["user"]["username"] == "newuser"
                assert "token" in data

                # 3. 重复邮箱再次请求验证码被拦截
                dup_code_res = client.post("/api/auth/send-verification-code", json={"email": "newuser@example.com"})
                assert dup_code_res.status_code == 409
                assert "已被注册" in (dup_code_res.json().get("error") or "")
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_email_verification_flow_and_cooldown()
    test_email_verification_expired_code()
    test_email_registration_via_api()
    print("test_email_verification ok")
