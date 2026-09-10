from __future__ import annotations

import secrets
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix.strip() or 'id'}_{secrets.token_hex(8)}"


def pagination(total: int, page: int, page_size: int) -> dict[str, int]:
    return {"total": total, "page": page, "pageSize": page_size, "pageCount": max(1, (total + page_size - 1) // page_size)}
