"""Account-level history for the standalone image and video panels.

Files land under the private artifact root by kind and user; rows keep the relative path.
Listing signs a fresh link per row, so history survives the 30-day link TTL and a JWT
rotation, which a localStorage copy of the signed URL never did.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import GenerationRecord
from app.services.artifact_service import remove_stored_artifacts, store_artifact
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
