from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from agent_service import run_chat_agent, stream_chat_agent
from artifact_service import artifact_from_token
from chat_service import begin_chat_turn, create_chat_session, delete_chat_session, list_chat_messages, list_chat_sessions, prepare_chat_turn, save_chat_message
from config_service import active_model_config
from context_graph import stream_context_messages
from database import db
from security import current_user_id
from serializers import chat_message_json
from usage_service import record_usage


router = APIRouter(prefix="/api/chat", tags=["chat"])


def _image_config(conn, user_id: int) -> dict[str, Any] | None:
    try:
        return active_model_config(conn, user_id, "image", "Agent 图片生成")
    except HTTPException:
        return None


@router.get("/artifacts/{token}")
def get_artifact(token: str) -> FileResponse:
    try:
        path, filename, media_type, inline = artifact_from_token(token)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline" if inline else "attachment",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/sessions")
def get_sessions(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        return {"sessions": list_chat_sessions(conn, user_id)}


@router.post("/sessions", status_code=201)
def post_session(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    config_id = payload.get("configId")
    official_config_id = payload.get("officialConfigId")
    with db() as conn:
        session = create_chat_session(
            conn,
            user_id,
            str(payload.get("title", "")),
            int(config_id) if config_id else None,
            int(official_config_id) if official_config_id else None,
        )
    return {"session": session}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user_id: int = Depends(current_user_id)) -> dict[str, bool]:
    with db() as conn:
        delete_chat_session(conn, session_id, user_id)
    return {"ok": True}


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        return {"messages": list_chat_messages(conn, session_id, user_id)}


@router.post("/sessions/{session_id}/messages")
async def post_message(session_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    content = str(payload.get("content", "")).strip()
    attachments = payload.get("attachments")
    config_id = payload.get("configId")
    official_config_id = payload.get("officialConfigId")
    with db() as conn:
        config, user_message, messages = await prepare_chat_turn(
            conn,
            session_id,
            user_id,
            content,
            attachments,
            int(config_id) if config_id else None,
            int(official_config_id) if official_config_id else None,
        )
        image_config = _image_config(conn, user_id)

    started_at = time.monotonic()
    try:
        result = await run_chat_agent(config, session_id, messages, image_config, user_id)
    except Exception as exc:
        raise HTTPException(502, "failed to chat: " + str(exc)) from exc

    with db() as conn:
        assistant_message = save_chat_message(conn, session_id, "assistant", result.content, config["provider"], config["model"])
    record_usage(user_id, config, "chat", started_at, result.usage)

    return {
        "userMessage": chat_message_json(user_message),
        "assistantMessage": chat_message_json(assistant_message),
    }


@router.post("/sessions/{session_id}/messages/stream")
async def stream_message(session_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> StreamingResponse:
    content = str(payload.get("content", "")).strip()
    attachments = payload.get("attachments")
    config_id = payload.get("configId")
    official_config_id = payload.get("officialConfigId")
    with db() as conn:
        config, user_message = begin_chat_turn(
            conn,
            session_id,
            user_id,
            content,
            attachments,
            int(config_id) if config_id else None,
            int(official_config_id) if official_config_id else None,
        )
        image_config = _image_config(conn, user_id)

    async def events():
        started_at = time.monotonic()
        yield json.dumps({"type": "userMessage", "message": chat_message_json(user_message)}, ensure_ascii=False) + "\n"
        answer = ""
        reasoning = ""
        messages: list[dict[str, str]] = []
        usage: dict[str, int] = {}
        try:
            with db() as conn:
                async for event in stream_context_messages(conn, session_id, config):
                    if event["type"] == "context_ready":
                        messages = event["messages"]
                        continue
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            yield json.dumps(
                {"type": "agent_step", "step": {"id": "agent_run", "label": "运行智能助手", "status": "running", "detail": config["model"]}},
                ensure_ascii=False,
            ) + "\n"
            async for chunk in stream_chat_agent(config, session_id, messages, image_config, user_id):
                if chunk["type"] == "agent_complete":
                    answer = chunk["content"] or answer
                    usage = chunk.get("usage") or {}
                    continue
                if chunk["type"] == "reasoning_delta":
                    reasoning += chunk["content"]
                elif chunk["type"] == "content_delta":
                    answer += chunk["content"]
                yield json.dumps(chunk, ensure_ascii=False) + "\n"
            yield json.dumps(
                {"type": "agent_step", "step": {"id": "agent_run", "label": "运行智能助手", "status": "done", "detail": "回复生成完成"}},
                ensure_ascii=False,
            ) + "\n"
            if not answer.strip():
                raise ValueError("empty content from agent")
            with db() as conn:
                assistant_message = save_chat_message(
                    conn,
                    session_id,
                    "assistant",
                    answer.strip(),
                    config["provider"],
                    config["model"],
                    reasoning.strip(),
                )
            record_usage(user_id, config, "chat", started_at, usage)
            yield json.dumps(
                {"type": "agent_step", "step": {"id": "save_message", "label": "保存回复", "status": "done", "detail": "已写入 SQLite"}},
                ensure_ascii=False,
            ) + "\n"
            yield json.dumps({"type": "assistantMessage", "message": chat_message_json(assistant_message)}, ensure_ascii=False) + "\n"
        except Exception as exc:
            yield json.dumps(
                {"type": "agent_step", "step": {"id": "runtime_error", "label": "执行失败", "status": "error", "detail": str(exc)[:180]}},
                ensure_ascii=False,
            ) + "\n"
            yield json.dumps({"type": "error", "error": "failed to chat: " + str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")
