from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from database import db, row
from realtime import broadcast, clients
from security import user_id_from_token
from utils import now


router = APIRouter(tags=["websocket"])


@router.websocket("/ws/projects/{project_id}")
async def project_ws(websocket: WebSocket, project_id: str, token: str = "") -> None:
    token = token.strip()
    if not token:
        token = (websocket.headers.get("authorization") or "").replace("Bearer", "").strip()
    try:
        user_id = user_id_from_token(token)
    except Exception:
        await websocket.close(code=1008)
        return
    with db() as conn:
        project = row(conn, "SELECT user_id FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,))
        if project and project["user_id"] != user_id:
            await websocket.close(code=1008)
            return
    await websocket.accept()
    clients.setdefault(project_id, set()).add(websocket)
    await broadcast(project_id, {"type": "WS_CONNECTED", "projectId": project_id, "data": {"connectedAt": now()}})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        project_clients = clients.get(project_id)
        if project_clients:
            project_clients.discard(websocket)
            if not project_clients:
                clients.pop(project_id, None)
