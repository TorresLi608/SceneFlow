"""Admin-configured retention for the four standalone menus.

Each menu keeps its own window in `system_settings` (see `system_setting_service`) and the
hourly sweeper applies all four. What expires, and the clock it expires on:

| category | rows                                     | files                               | clock         |
|----------|------------------------------------------|-------------------------------------|---------------|
| image    | `generation_records` with kind `image`   | the stored image                    | created_at    |
| video    | `generation_records` with kind `video`   | the stored clip                     | created_at    |
| chat     | `chat_sessions` and their `chat_messages`| `chat/<session id>/` tool artifacts | last activity |
| voice    | `user_voices`, drafts and saved alike    | the audition WAV                    | created_at    |

Nothing under a project is ever touched. Storyboard frames, shot clips, project voices,
assets, tone sheets, and exports belong to the AI drama workbench and have no retention
policy; keep it that way. A category here is a standalone menu, never a media type.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Callable

from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.core.database import db
from app.models import ChatMessage, ChatSession, GenerationRecord, UserVoice
from app.services.artifact_service import remove_artifact_scope, remove_stored_artifacts
from app.services.system_setting_service import RETENTION_CATEGORIES, retention_days


logger = logging.getLogger(__name__)

RETENTION_SWEEP_INTERVAL_SECONDS = 60 * 60
# SQLite caps the number of bound parameters per statement; a first sweep over a long
# backlog can exceed it if every id lands in one IN list.
DELETE_CHUNK = 500


def _cutoff(retention_days: int, current: datetime | None) -> str:
    # Timestamps are ISO-8601 UTC strings, so a string comparison against the cutoff orders correctly.
    return ((current or datetime.now(timezone.utc)) - timedelta(days=retention_days)).isoformat()


def _delete_where_in(session: Session, model: type, column, ids: list[str]) -> None:
    for start in range(0, len(ids), DELETE_CHUNK):
        session.execute(delete(model).where(column.in_(ids[start : start + DELETE_CHUNK])))


def expired_generation_count(session: Session, kind: str, retention_days: int, current: datetime | None = None) -> int:
    """How many live image/video rows the next sweep would remove at the given window (0 = none)."""
    if retention_days <= 0:
        return 0
    cutoff = _cutoff(retention_days, current)
    return session.exec(
        select(func.count())
        .select_from(GenerationRecord)
        .where(GenerationRecord.kind == kind, GenerationRecord.deleted_at.is_(None), GenerationRecord.created_at < cutoff)
    ).one()


def purge_expired_generation_records(session: Session, kind: str, retention_days: int, current: datetime | None = None) -> int:
    """Hard-delete one kind of standalone result older than the window and remove its files.

    Rows the user already soft-deleted lost their file at that time; they are dropped here
    too so the table does not grow without bound. Returns the number of rows removed. A
    window of 0 days means "keep forever" and removes nothing.
    """
    if retention_days <= 0:
        return 0
    cutoff = _cutoff(retention_days, current)
    expired = session.exec(select(GenerationRecord).where(GenerationRecord.kind == kind, GenerationRecord.created_at < cutoff)).all()
    if not expired:
        return 0
    # Files first: if the row delete then fails, the next pass still finds the row and
    # finishes the job, whereas a row deleted ahead of its file leaves the file orphaned forever.
    remove_stored_artifacts([record.path for record in expired if record.deleted_at is None])
    _delete_where_in(session, GenerationRecord, GenerationRecord.id, [record.id for record in expired])
    return len(expired)


def _chat_last_activity():
    # `updated_at` moves on every saved message, so an old conversation that is still in
    # use never expires; `created_at` only covers legacy rows that never got a timestamp.
    return func.coalesce(ChatSession.updated_at, ChatSession.created_at)


def expired_chat_session_count(session: Session, retention_days: int, current: datetime | None = None) -> int:
    if retention_days <= 0:
        return 0
    cutoff = _cutoff(retention_days, current)
    return session.exec(
        select(func.count()).select_from(ChatSession).where(ChatSession.deleted_at.is_(None), _chat_last_activity() < cutoff)
    ).one()


def purge_expired_chat_sessions(session: Session, retention_days: int, current: datetime | None = None) -> int:
    """Hard-delete sessions idle for longer than the window, with their messages and tool artifacts.

    Sessions the user already removed are only soft-deleted, so their messages and any
    generated images or documents are still on disk; they go here once they age out too.
    """
    if retention_days <= 0:
        return 0
    cutoff = _cutoff(retention_days, current)
    expired = list(session.exec(select(ChatSession.id).where(_chat_last_activity() < cutoff)).all())
    if not expired:
        return 0
    for session_id in expired:
        remove_artifact_scope("chat", session_id)
    # Messages cascade from the session under `PRAGMA foreign_keys = ON`, but a database
    # that was ever opened without the pragma may hold rows the cascade will not reach.
    _delete_where_in(session, ChatMessage, ChatMessage.session_id, expired)
    _delete_where_in(session, ChatSession, ChatSession.id, expired)
    return len(expired)


def expired_user_voice_count(session: Session, retention_days: int, current: datetime | None = None) -> int:
    if retention_days <= 0:
        return 0
    cutoff = _cutoff(retention_days, current)
    return session.exec(
        select(func.count()).select_from(UserVoice).where(UserVoice.deleted_at.is_(None), UserVoice.created_at < cutoff)
    ).one()


def purge_expired_user_voices(session: Session, retention_days: int, current: datetime | None = None) -> int:
    """Hard-delete standalone voices older than the window along with their audition audio.

    Drafts the user never saved and voices they later deleted both keep their WAV on disk
    until now, so the file goes for every expired row, not only the live ones. The provider
    side voice id is not revoked; nothing in this app calls it once the row is gone.
    """
    if retention_days <= 0:
        return 0
    cutoff = _cutoff(retention_days, current)
    expired = session.exec(select(UserVoice).where(UserVoice.created_at < cutoff)).all()
    if not expired:
        return 0
    remove_stored_artifacts([voice.preview_audio_path for voice in expired if voice.preview_audio_path])
    _delete_where_in(session, UserVoice, UserVoice.id, [voice.id for voice in expired])
    return len(expired)


Sweep = Callable[[Session, int, datetime | None], int]

_COUNTERS: dict[str, Sweep] = {
    "image": lambda session, days, current: expired_generation_count(session, "image", days, current),
    "video": lambda session, days, current: expired_generation_count(session, "video", days, current),
    "chat": expired_chat_session_count,
    "voice": expired_user_voice_count,
}
_PURGERS: dict[str, Sweep] = {
    "image": lambda session, days, current: purge_expired_generation_records(session, "image", days, current),
    "video": lambda session, days, current: purge_expired_generation_records(session, "video", days, current),
    "chat": purge_expired_chat_sessions,
    "voice": purge_expired_user_voices,
}
assert set(_COUNTERS) == set(_PURGERS) == set(RETENTION_CATEGORIES)


def expired_counts(session: Session, current: datetime | None = None) -> dict[str, int]:
    """Per category, how many live rows the next sweep would remove under the saved windows."""
    return {category: _COUNTERS[category](session, retention_days(session, category), current) for category in RETENTION_CATEGORIES}


def run_retention_sweep() -> dict[str, int]:
    """One pass of every window against the live database; safe to call from anywhere.

    Each category commits on its own so a failure in one leaves the others' work in place.
    Returns the rows removed per category.
    """
    removed: dict[str, int] = {}
    for category in RETENTION_CATEGORIES:
        with db() as session:
            days = retention_days(session, category)
            removed[category] = _PURGERS[category](session, days, None)
        if removed[category]:
            logger.info("retention sweep category=%s removed=%s window_days=%s", category, removed[category], days)
    return removed


class RetentionSweeper:
    """Hourly background loop that applies the admin-configured retention windows.

    Runs inside the FastAPI process next to the job worker, so a single backend instance is
    assumed just as it is for renders. Each pass re-reads the settings, so an admin change
    takes effect on the next tick without a restart.
    """

    def __init__(self, interval_seconds: float = RETENTION_SWEEP_INTERVAL_SECONDS) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="generation-retention-sweeper")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(run_retention_sweep)
            except Exception:  # noqa: BLE001 -- a failed pass must not end the loop
                logger.exception("generation retention sweep failed")
            await asyncio.sleep(self.interval_seconds)


retention_sweeper = RetentionSweeper()
