"""Runtime policy settings edited from the admin center.

Each setting has a typed accessor here so callers never parse the stored string themselves
and an unset or corrupted row falls back to the documented default.
"""

from __future__ import annotations

from typing import Literal

from sqlmodel import Session

from app.models import GENERATION_RETENTION_MAX_DAYS, SystemSetting
from app.utils.common import now


# One retention window per standalone menu. A category is a menu rather than a media type
# on purpose: the AI drama workbench (storyboard frames, clips, project voices, exports)
# is never subject to a retention sweep, and naming windows after menus keeps that boundary
# visible to whoever adds the next one.
RetentionCategory = Literal["image", "video", "chat", "voice"]
RETENTION_CATEGORIES: tuple[RetentionCategory, ...] = ("image", "video", "chat", "voice")
GENERATION_RETENTION_DEFAULT_DAYS = 0


def retention_setting_key(category: str) -> str:
    if category not in RETENTION_CATEGORIES:
        raise ValueError(f"unknown retention category: {category}")
    return f"generation_retention_{category}_days"


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


def retention_days(session: Session, category: str) -> int:
    """The window for one category; unset or unreadable means keep forever."""
    setting = _read(session, retention_setting_key(category))
    if setting is None:
        return GENERATION_RETENTION_DEFAULT_DAYS
    try:
        return normalize_retention_days(setting.value)
    except ValueError:
        return GENERATION_RETENTION_DEFAULT_DAYS


def retention_policies_json(session: Session) -> dict[str, dict[str, object]]:
    policies: dict[str, dict[str, object]] = {}
    for category in RETENTION_CATEGORIES:
        setting = _read(session, retention_setting_key(category))
        policies[category] = {
            "retentionDays": retention_days(session, category),
            "updatedAt": setting.updated_at if setting else None,
        }
    return policies


def set_retention_days(session: Session, values: dict[str, object], user_id: int | None) -> dict[str, dict[str, object]]:
    """Write the given categories only; the others keep their window.

    Every value is validated before anything is written, so a bad entry cannot leave the
    policy half-applied.
    """
    normalized = {retention_setting_key(category): normalize_retention_days(days) for category, days in values.items()}
    for key, days in normalized.items():
        _write(session, key, str(days), user_id)
    return retention_policies_json(session)
