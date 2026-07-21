from __future__ import annotations

from typing import Any

from fastapi import WebSocket


clients: dict[str, set[WebSocket]] = {}


async def broadcast(project_id: str, payload: dict[str, Any]) -> None:
    dead = []
    for ws in clients.get(project_id, set()).copy():
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.get(project_id, set()).discard(ws)
    if not clients.get(project_id):
        clients.pop(project_id, None)
