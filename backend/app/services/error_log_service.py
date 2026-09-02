"""Persist the small, safe subset of a failed request needed for later diagnosis."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.core.database import db
from app.models import ErrorLog
from app.utils.common import new_id, now


logger = logging.getLogger(__name__)
ERROR_DETAIL_CHARS = 220


def error_code_for(status_code: int, detail: Any) -> str:
    message = str(detail).lower()
    if status_code == 502 and "failed to break down script" in message:
        return "BREAKDOWN_INVALID_JSON" if "json object" in message else "BREAKDOWN_FAILED"
    return "PROVIDER_FAILURE" if status_code == 502 else "INTERNAL_ERROR"


def _route(request: Request) -> str:
    route = request.scope.get("route")
    return str(getattr(route, "path", request.url.path))[:240]


def record_http_error(request: Request, status_code: int, detail: Any, error_code: str | None = None) -> None:
    """Best-effort only: an observability write must never replace the original error."""
    if status_code < 500:
        return
    request_id = str(getattr(request.state, "request_id", ""))
    if not request_id:
        return
    params = request.path_params
    # A provider can echo user content in its error body. The code identifies the failure;
    # the stored message deliberately retains only the operation before provider detail.
    message = str(detail).split("; model output:", 1)[0].split(": ", 1)[0].strip()[:ERROR_DETAIL_CHARS]
    try:
        with db() as session:
            session.add(
                ErrorLog(
                    id=new_id("error"),
                    created_at=now(),
                    request_id=request_id,
                    method=request.method,
                    route=_route(request),
                    status_code=status_code,
                    error_code=error_code or error_code_for(status_code, message),
                    message=message or "internal server error",
                    user_id=getattr(request.state, "user_id", None),
                    project_id=params.get("project_id"),
                    episode_id=params.get("episode_id"),
                )
            )
    except Exception:
        logger.exception("error log persistence failed request=%s", request_id)


def error_log_json(item: ErrorLog) -> dict[str, Any]:
    return {
        "id": item.id,
        "createdAt": item.created_at,
        "requestId": item.request_id,
        "method": item.method,
        "route": item.route,
        "statusCode": item.status_code,
        "errorCode": item.error_code,
        "message": item.message,
        "userId": item.user_id,
        "projectId": item.project_id,
        "episodeId": item.episode_id,
    }


def find_error_logs(
    session: Session,
    *,
    search: str = "",
    error_code: str = "",
    project_id: str = "",
    request_id: str = "",
    page: int = 1,
    page_size: int = 20,
) -> tuple[int, list[ErrorLog]]:
    conditions = []
    if search.strip():
        term = f"%{search.strip()}%"
        conditions.append(
            or_(
                ErrorLog.route.like(term),
                ErrorLog.message.like(term),
                ErrorLog.request_id.like(term),
                ErrorLog.error_code.like(term),
                ErrorLog.project_id.like(term),
            )
        )
    if error_code.strip():
        conditions.append(ErrorLog.error_code == error_code.strip())
    if project_id.strip():
        conditions.append(ErrorLog.project_id == project_id.strip())
    if request_id.strip():
        conditions.append(ErrorLog.request_id == request_id.strip())
    total = session.exec(select(func.count()).select_from(ErrorLog).where(*conditions)).one()
    logs = session.exec(
        select(ErrorLog)
        .where(*conditions)
        .order_by(ErrorLog.created_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return total, logs
