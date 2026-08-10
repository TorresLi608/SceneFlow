from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import select

from app.core.database import db
from app.core.realtime import broadcast, clients
from app.core.security import user_id_from_token
from app.models import Project
from app.utils.common import now


router = APIRouter(tags=["websocket"])


def protocol_token(value: str) -> tuple[str, str]:
    protocol = next((item.strip() for item in value.split(",") if item.strip().startswith("sceneflow-auth.")), "")
    return protocol.removeprefix("sceneflow-auth."), protocol


@router.websocket("/ws/projects/{project_id}")
async def project_ws(websocket: WebSocket, project_id: str) -> None:
    token, protocol = protocol_token(websocket.headers.get("sec-websocket-protocol") or "")
    if not token:
        token = (websocket.headers.get("authorization") or "").replace("Bearer", "").strip()
    try:
        user_id = user_id_from_token(token)
    except Exception:
        await websocket.close(code=1008)
        return
    with db() as session:
        owner_id = session.exec(
            select(Project.user_id).where(Project.id == project_id, Project.deleted_at.is_(None))
        ).first()
        if owner_id != user_id:
            await websocket.close(code=1008)
            return
    await websocket.accept(subprotocol=protocol or None)
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
