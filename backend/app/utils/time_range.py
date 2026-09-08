from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException


def utc_time_bounds(start_time: datetime | None, end_time: datetime | None) -> tuple[str | None, str | None]:
    """Convert an inclusive, second-precision range to UTC storage bounds."""
    if start_time is None and end_time is None:
        return None, None
    if start_time is None or end_time is None:
        raise HTTPException(422, "startTime and endTime must be provided together")
    if start_time > end_time:
        raise HTTPException(422, "startTime must not be after endTime")
    try:
        start = start_time.astimezone(timezone.utc).replace(microsecond=0)
        # Use an exclusive next second so records with fractional seconds are included.
        end = end_time.astimezone(timezone.utc).replace(microsecond=0) + timedelta(seconds=1)
    except OverflowError as exc:
        raise HTTPException(422, "time range is out of bounds") from exc
    return start.isoformat(), end.isoformat()
