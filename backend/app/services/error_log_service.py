"""Persist the small, safe subset of a failed request needed for later diagnosis."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from fastapi import HTTPException, Request
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.core.database import db
from app.models import ErrorLog
from app.utils.common import new_id, now


logger = logging.getLogger(__name__)
ERROR_DETAIL_CHARS = 220


def safe_error_reason(exc: BaseException) -> str:
    """Extract diagnostic facts, never a raw provider body or arbitrary message.

    Error responses can echo chat content, keys and signed URLs. Only known
    parameter/model grammar is retained; other errors use type/status facts.
    """
    reason = ""
    fallback = type(exc).__name__
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        fallback = type(exc).__name__
        text = str(exc)[:8_000]
        parameter = r"`?(temperature|top_p|top_k|max_tokens|stream|tools)`?"
        unsupported = re.search(
            parameter + r" is not supported for ((?:claude|gemini|gpt)-[a-z0-9.-]{1,80}) at non-default values\.",
            text, re.IGNORECASE,
        )
        if unsupported:
            return f"`{unsupported[1]}` is not supported for {unsupported[2]} at non-default values."
        recursion = re.search(r"Recursion limit of (\d{1,6}) reached without hitting a stop condition", text)
        if recursion:
            return f"Agent step limit reached ({recursion[1]})"
        if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            reason = "upstream request timed out"
        elif isinstance(exc, (ConnectionError, httpx.RequestError)):
            reason = "upstream connection failed"
        elif not isinstance(exc, HTTPException):
            status = getattr(exc, "status_code", None)
            if status is None:
                status = getattr(getattr(exc, "response", None), "status_code", None)
            if isinstance(status, int) and 400 <= status <= 599:
                reason = f"upstream request failed (HTTP {status})"
        exc = exc.__cause__ or exc.__context__
    # Class names are local code identifiers; no arbitrary str(exc) fallback.
    return reason or fallback


def error_code_for(status_code: int, detail: Any) -> str:
    message = str(detail).lower()
    if status_code == 502 and "failed to break down script" in message:
        return "BREAKDOWN_INVALID_JSON" if "json object" in message else "BREAKDOWN_FAILED"
    return "PROVIDER_FAILURE" if status_code == 502 else "INTERNAL_ERROR"


def _route(request: Request) -> str:
    route = request.scope.get("route")
    return str(getattr(route, "path", request.url.path))[:240]


def record_http_error(
    request: Request, status_code: int, detail: Any, error_code: str | None = None,
    *, exception: BaseException | None = None,
) -> None:
    """Best-effort only: an observability write must never replace the original error."""
    if status_code < 500:
        return
    request_id = str(getattr(request.state, "request_id", ""))
    if not request_id:
        return
    try:
        params = request.path_params
        # Keep the operation and allowlisted diagnostic facts, never raw provider detail.
        message = str(detail).split("; model output:", 1)[0].split(": ", 1)[0].strip()[:ERROR_DETAIL_CHARS]
        if exception is not None:
            reason = safe_error_reason(exception)
            message = f"{message}: {reason}"[:ERROR_DETAIL_CHARS]
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
    start_at: str | None = None,
    end_before: str | None = None,
) -> tuple[int, list[ErrorLog]]:
    conditions = []
    if start_at is not None:
        conditions.append(ErrorLog.created_at >= start_at)
    if end_before is not None:
        conditions.append(ErrorLog.created_at < end_before)
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
