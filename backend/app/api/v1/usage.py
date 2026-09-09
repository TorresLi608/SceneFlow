from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.core.database import db
from app.api.deps import current_user_id
from app.services.usage_service import usage_logs
from app.utils.time_range import utc_time_bounds


router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/logs")
def get_usage_logs(
    feature: str = Query("all", max_length=40),
    days: int = Query(30, ge=1, le=365),
    source: str = Query("all", pattern="^(all|official|user)$"),
    user_id: int = Depends(current_user_id),
    start_time: Annotated[AwareDatetime | None, Query(alias="startTime")] = None,
    end_time: Annotated[AwareDatetime | None, Query(alias="endTime")] = None,
) -> dict[str, Any]:
    start_at, end_before = utc_time_bounds(start_time, end_time)
    with db() as session:
        return usage_logs(session, user_id, feature, days, source, start_at=start_at, end_before=end_before)
