"""Runtime policy settings edited from the admin center.

Each setting has a typed accessor here so callers never parse the stored string themselves
and an unset or corrupted row falls back to the documented default.
"""

from __future__ import annotations

from sqlmodel import Session

from app.models import SystemSetting
from app.utils.common import now


GENERATION_RETENTION_KEY = "generation_retention_days"
GENERATION_RETENTION_DEFAULT_DAYS = 0
GENERATION_RETENTION_MAX_DAYS = 3650


def _read(session: Session, key: str) -> SystemSetting | None:
    return session.get(SystemSetting, key)


def _write(session: Session, key: str, value: str, user_id: int | None) -> SystemSetting:
    setting = _read(session, key) or SystemSetting(key=key)
    setting.value = value
    setting.updated_at = now()
    setting.updated_by_user_id = user_id
    session.add(setting)
    session.flush()
    return setting


def normalize_retention_days(value: object) -> int:
    """Whole days; 0 disables automatic cleanup."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("retentionDays must be an integer number of days")
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("retentionDays must be an integer number of days") from exc
    if isinstance(value, float) and value != days:
        raise ValueError("retentionDays must be a whole number of days")
    if days < 0 or days > GENERATION_RETENTION_MAX_DAYS:
        raise ValueError(f"retentionDays must be between 0 and {GENERATION_RETENTION_MAX_DAYS}")
    return days


def generation_retention_days(session: Session) -> int:
    setting = _read(session, GENERATION_RETENTION_KEY)
    if setting is None:
        return GENERATION_RETENTION_DEFAULT_DAYS
    try:
        return normalize_retention_days(setting.value)
    except ValueError:
        return GENERATION_RETENTION_DEFAULT_DAYS


def generation_retention_json(session: Session) -> dict[str, object]:
    setting = _read(session, GENERATION_RETENTION_KEY)
    return {
        "retentionDays": generation_retention_days(session),
        "updatedAt": setting.updated_at if setting else None,
    }


def set_generation_retention_days(session: Session, days: int, user_id: int | None) -> dict[str, object]:
    _write(session, GENERATION_RETENTION_KEY, str(normalize_retention_days(days)), user_id)
    return generation_retention_json(session)
