from __future__ import annotations

import secrets
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix.strip() or 'id'}_{secrets.token_hex(8)}"
