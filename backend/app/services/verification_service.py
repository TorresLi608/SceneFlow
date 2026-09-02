"""Email verification code service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import secrets

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import EmailVerification, User
from app.services.email_service import send_verification_email
from app.utils.common import now


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
VERIFICATION_CODE_EXPIRY_SECONDS = 300
VERIFICATION_CODE_COOLDOWN_SECONDS = 60


def validate_email_format(email: str) -> str:
    cleaned = email.strip().lower()
    if not cleaned or not EMAIL_REGEX.match(cleaned) or len(cleaned) > 254:
        raise HTTPException(400, "请输入有效的电子邮箱")
    return cleaned


def _expires_at(seconds: int = VERIFICATION_CODE_EXPIRY_SECONDS) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _is_within_cooldown(created_at_str: str, cooldown_seconds: int = VERIFICATION_CODE_COOLDOWN_SECONDS) -> bool:
    try:
        created_dt = datetime.fromisoformat(created_at_str)
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - created_dt).total_seconds() < cooldown_seconds
    except (ValueError, TypeError):
        return False


def _is_expired(expires_at_str: str) -> bool:
    try:
        expires_dt = datetime.fromisoformat(expires_at_str)
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= expires_dt
    except (ValueError, TypeError):
        return True


def send_registration_code(session: Session, email: str, ip_address: str | None = None) -> EmailVerification:
    cleaned_email = validate_email_format(email)

    # 1. 检查邮箱是否已被注册
    existing_user = session.exec(
        select(User.id).where(User.email == cleaned_email, User.deleted_at.is_(None))
    ).first()
    if existing_user:
        raise HTTPException(409, "该邮箱已被注册")

    # 2. 检查 60s 冷却限制
    latest = session.exec(
        select(EmailVerification)
        .where(EmailVerification.email == cleaned_email)
        .order_by(EmailVerification.created_at.desc())
    ).first()
    if latest and _is_within_cooldown(latest.created_at, VERIFICATION_CODE_COOLDOWN_SECONDS):
        raise HTTPException(429, "验证码发送过于频繁，请等待 60 秒后再试")

    # 3. 生成 6 位随机验证码
    code = f"{secrets.randbelow(900000) + 100000}"
    stamp = now()
    expires = _expires_at(VERIFICATION_CODE_EXPIRY_SECONDS)

    verification = EmailVerification(
        created_at=stamp,
        expires_at=expires,
        email=cleaned_email,
        code=code,
        ip_address=ip_address,
    )
    session.add(verification)
    session.flush()

    # 4. 发送邮件
    send_verification_email(cleaned_email, code)

    return verification


def verify_and_consume_code(session: Session, email: str, code: str) -> None:
    cleaned_email = validate_email_format(email)
    cleaned_code = str(code).strip()

    if not cleaned_code:
        raise HTTPException(400, "请输入验证码")

    # 查询最近一条未使用的验证码记录
    verification = session.exec(
        select(EmailVerification)
        .where(
            EmailVerification.email == cleaned_email,
            EmailVerification.code == cleaned_code,
            EmailVerification.used_at.is_(None),
        )
        .order_by(EmailVerification.created_at.desc())
    ).first()

    if not verification:
        raise HTTPException(400, "验证码错误或无效")

    if _is_expired(verification.expires_at):
        raise HTTPException(400, "验证码已过期，请重新获取")

    # 核销验证码
    verification.used_at = now()
    session.add(verification)
    session.flush()
