"""Account-level history for the standalone image and video panels.

Files land under the private artifact root by kind and user; rows keep the relative path.
Listing signs a fresh link per row, so history survives the 30-day link TTL and a JWT
rotation, which a localStorage copy of the signed URL never did. Expiry under the admin
retention windows lives in `retention_service`.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlmodel import Session, select

from app.models import GenerationRecord
from app.services.artifact_service import remove_stored_artifacts, store_artifact
from app.services.image_thumbnail_service import image_thumbnail_path, store_image_thumbnail
from app.utils.common import new_id, now


GenerationKind = Literal["image", "video"]
HISTORY_LIMIT = 50
MAX_PROMPT_CHARS = 4_000


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
    thumbnail: bytes | None = None,
) -> GenerationRecord:
    path = store_artifact(f"{kind}s", str(user_id), filename, data)
    if kind == "image" and thumbnail is not None:
        store_image_thumbnail(path, thumbnail)
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


def generation_record_paths(record: GenerationRecord) -> list[str]:
    return [record.path, image_thumbnail_path(record.path)] if record.kind == "image" else [record.path]


def list_image_history_page(session: Session, user_id: int, limit: int, cursor: str | None) -> tuple[list[GenerationRecord], str | None]:
    # Include ID as a tie breaker so equal timestamps and deleted cursor rows never skip results.
    created = func.coalesce(GenerationRecord.created_at, "")
    statement = select(GenerationRecord).where(
        GenerationRecord.user_id == user_id,
        GenerationRecord.kind == "image",
        GenerationRecord.deleted_at.is_(None),
    )
    if cursor is not None:
        try:
            position = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
            if not isinstance(position, list) or len(position) != 2 or not all(isinstance(value, str) for value in position) or not position[1]:
                raise ValueError("invalid cursor position")
            stamp, record_id = position
            # JSON can contain lone surrogates that SQLite cannot encode as text.
            stamp.encode("utf-8")
            record_id.encode("utf-8")
        except ValueError as exc:
            raise HTTPException(400, "invalid history cursor") from exc
        statement = statement.where(or_(created < stamp, and_(created == stamp, GenerationRecord.id < record_id)))
    rows = list(session.exec(statement.order_by(created.desc(), GenerationRecord.id.desc()).limit(limit + 1)).all())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = base64.urlsafe_b64encode(json.dumps([last.created_at or "", last.id]).encode()).decode().rstrip("=")
    return items, next_cursor


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
    remove_stored_artifacts(generation_record_paths(record))
