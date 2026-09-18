"""Account-level history for the standalone image and video panels.

Files land under the private artifact root by kind and user; rows keep the relative path.
Listing signs a fresh link per row, so history survives the 30-day link TTL and a JWT
rotation, which a localStorage copy of the signed URL never did.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import delete
from sqlmodel import Session, select

from app.core.database import db
from app.models import GenerationRecord
from app.services.artifact_service import remove_stored_artifacts, store_artifact
from app.services.system_setting_service import generation_retention_days
from app.utils.common import new_id, now


logger = logging.getLogger(__name__)

GenerationKind = Literal["image", "video"]
HISTORY_LIMIT = 50
MAX_PROMPT_CHARS = 4_000
RETENTION_SWEEP_INTERVAL_SECONDS = 60 * 60


def save_generation_record(
    session: Session,
    user_id: int,
    kind: GenerationKind,
    data: bytes,
    filename: str,
    media_type: str,
    *,
    prompt: str,
    config: dict[str, Any],
    source: str,
    options: dict[str, Any] | None = None,
) -> GenerationRecord:
    path = store_artifact(f"{kind}s", str(user_id), filename, data)
    record = GenerationRecord(
        id=new_id(f"gen_{kind}"),
        created_at=now(),
        user_id=user_id,
        kind=kind,
        path=path,
        media_type=media_type,
        prompt=prompt.strip()[:MAX_PROMPT_CHARS],
        provider=str(config.get("provider") or ""),
        model_name=str(config.get("model") or ""),
        source=source,
        options_json=json.dumps({key: value for key, value in (options or {}).items() if value is not None}, ensure_ascii=False),
    )
    session.add(record)
    session.flush()
    return record


def list_generation_records(session: Session, user_id: int, kind: GenerationKind, limit: int = HISTORY_LIMIT) -> list[GenerationRecord]:
    limit = max(1, min(int(limit), HISTORY_LIMIT))
    statement = (
        select(GenerationRecord)
        .where(GenerationRecord.user_id == user_id, GenerationRecord.kind == kind, GenerationRecord.deleted_at.is_(None))
        .order_by(GenerationRecord.created_at.desc())
        .limit(limit)
    )
    return list(session.exec(statement).all())


def delete_generation_record(session: Session, user_id: int, kind: GenerationKind, record_id: str) -> None:
    record = session.exec(
        select(GenerationRecord).where(
            GenerationRecord.id == record_id,
            GenerationRecord.user_id == user_id,
            GenerationRecord.kind == kind,
            GenerationRecord.deleted_at.is_(None),
        )
    ).first()
    if not record:
        raise HTTPException(404, "history item not found")
    record.deleted_at = now()
    session.add(record)
    session.flush()
    # Nothing else references a standalone result, so the bytes go with the row.
    remove_stored_artifacts([record.path])


def expired_generation_count(session: Session, retention_days: int, current: datetime | None = None) -> int:
    """How many live rows the next sweep would remove at the given policy (0 = none)."""
    if retention_days <= 0:
        return 0
    cutoff = ((current or datetime.now(timezone.utc)) - timedelta(days=retention_days)).isoformat()
    rows = session.exec(select(GenerationRecord.id).where(GenerationRecord.deleted_at.is_(None), GenerationRecord.created_at < cutoff)).all()
    return len(rows)


def purge_expired_generation_records(session: Session, retention_days: int, current: datetime | None = None) -> int:
    """Hard-delete standalone results older than the retention window and remove their files.

    Timestamps are ISO-8601 UTC strings, so a string comparison against the cutoff orders
    correctly. Rows the user already soft-deleted lost their file at that time; they are
    dropped here too so the table does not grow without bound. Returns the number of rows
    removed. A policy of 0 days means "keep forever" and removes nothing.
    """
    if retention_days <= 0:
        return 0
    cutoff = ((current or datetime.now(timezone.utc)) - timedelta(days=retention_days)).isoformat()
    expired = session.exec(select(GenerationRecord).where(GenerationRecord.created_at < cutoff)).all()
    if not expired:
        return 0
    remove_stored_artifacts([record.path for record in expired if record.deleted_at is None])
    session.execute(delete(GenerationRecord).where(GenerationRecord.id.in_([record.id for record in expired])))
    return len(expired)


def run_retention_sweep() -> int:
    """One pass of the policy against the live database; safe to call from anywhere."""
    with db() as session:
        days = generation_retention_days(session)
        removed = purge_expired_generation_records(session, days)
    if removed:
        logger.info("generation retention sweep removed %s records older than %s days", removed, days)
    return removed


class RetentionSweeper:
    """Hourly background loop that applies the admin-configured retention policy.

    Runs inside the FastAPI process next to the job worker, so a single backend instance is
    assumed just as it is for renders. Each pass re-reads the setting, so an admin change
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
