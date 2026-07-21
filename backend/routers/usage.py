from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from database import db
from security import current_user_id
from services.usage_service import usage_logs


router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/logs")
def get_usage_logs(
    feature: str = Query("all", max_length=40),
    days: int = Query(30, ge=1, le=365),
    source: str = Query("all", pattern="^(all|official|user)$"),
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    with db() as conn:
        return usage_logs(conn, user_id, feature, days, source)
