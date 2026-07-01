from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from chat_service import chat_config, create_chat_session, list_chat_messages, list_chat_sessions, require_session, save_chat_message
from database import db, rows
from model_registry import models
from security import current_user_id
from serializers import chat_message_json


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/sessions")
def get_sessions(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        return {"sessions": list_chat_sessions(conn, user_id)}


@router.post("/sessions", status_code=201)
def post_session(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    config_id = payload.get("configId")
    with db() as conn:
        session = create_chat_session(conn, user_id, str(payload.get("title", "")), int(config_id) if config_id else None)
    return {"session": session}


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        return {"messages": list_chat_messages(conn, session_id, user_id)}


@router.post("/sessions/{session_id}/messages")
async def post_message(session_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(400, "content is required")
    if len(content) > 12000:
        raise HTTPException(400, "content is too long")

    config_id = payload.get("configId")
    with db() as conn:
        session = require_session(conn, session_id, user_id)
        config = chat_config(conn, user_id, int(config_id) if config_id else session["config_id"])
        user_message = save_chat_message(conn, session_id, "user", content, config["provider"], config["model"])
        history = rows(conn, "SELECT role, content FROM chat_messages WHERE session_id=? ORDER BY created_at ASC LIMIT 40", (session_id,))

    messages = [{"role": "system", "content": "You are SceneFlow Assistant. Answer clearly and concisely."}]
    messages.extend({"role": message["role"], "content": message["content"]} for message in history)

    try:
        answer = await models.chat(config["provider"], config["apiKey"], config["model"], messages)
    except Exception as exc:
        raise HTTPException(502, "failed to chat: " + str(exc)) from exc

    with db() as conn:
        assistant_message = save_chat_message(conn, session_id, "assistant", answer, config["provider"], config["model"])

    return {
        "userMessage": chat_message_json(user_message),
        "assistantMessage": chat_message_json(assistant_message),
    }


@router.post("/sessions/{session_id}/messages/stream")
async def stream_message(session_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> StreamingResponse:
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(400, "content is required")
    if len(content) > 12000:
        raise HTTPException(400, "content is too long")

    config_id = payload.get("configId")
    with db() as conn:
        session = require_session(conn, session_id, user_id)
        config = chat_config(conn, user_id, int(config_id) if config_id else session["config_id"])
        user_message = save_chat_message(conn, session_id, "user", content, config["provider"], config["model"])
        history = rows(conn, "SELECT role, content FROM chat_messages WHERE session_id=? ORDER BY created_at ASC LIMIT 40", (session_id,))

    messages = [{"role": "system", "content": "You are SceneFlow Assistant. Answer clearly and concisely."}]
    messages.extend({"role": message["role"], "content": message["content"]} for message in history)

    async def events():
        yield json.dumps({"type": "userMessage", "message": chat_message_json(user_message)}, ensure_ascii=False) + "\n"
        answer = ""
        reasoning = ""
        try:
            async for chunk in models.chat_stream(config["provider"], config["apiKey"], config["model"], messages):
                if chunk["type"] == "reasoning_delta":
                    reasoning += chunk["content"]
                elif chunk["type"] == "content_delta":
                    answer += chunk["content"]
                yield json.dumps(chunk, ensure_ascii=False) + "\n"
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
            yield json.dumps({"type": "assistantMessage", "message": chat_message_json(assistant_message)}, ensure_ascii=False) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "error": "failed to chat: " + str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")
