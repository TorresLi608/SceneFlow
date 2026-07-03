from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from chat_service import begin_chat_turn, create_chat_session, list_chat_messages, list_chat_sessions, prepare_chat_turn, save_chat_message
from context_graph import stream_context_messages
from database import db
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


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        return {"messages": list_chat_messages(conn, session_id, user_id)}


@router.post("/sessions/{session_id}/messages")
async def post_message(session_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    content = str(payload.get("content", "")).strip()
    config_id = payload.get("configId")
    official_config_id = payload.get("officialConfigId")
    with db() as conn:
        config, user_message, messages = await prepare_chat_turn(
            conn,
            session_id,
            user_id,
            content,
            int(config_id) if config_id else None,
            int(official_config_id) if official_config_id else None,
        )

    try:
        answer = await models.chat(config["provider"], config["apiKey"], config["model"], messages, config.get("baseUrl", ""))
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
    config_id = payload.get("configId")
    official_config_id = payload.get("officialConfigId")
    with db() as conn:
        config, user_message = begin_chat_turn(
            conn,
            session_id,
            user_id,
            content,
            int(config_id) if config_id else None,
            int(official_config_id) if official_config_id else None,
        )

    async def events():
        yield json.dumps({"type": "userMessage", "message": chat_message_json(user_message)}, ensure_ascii=False) + "\n"
        answer = ""
        reasoning = ""
        messages: list[dict[str, str]] = []
        try:
            with db() as conn:
                async for event in stream_context_messages(conn, session_id, config):
                    if event["type"] == "context_ready":
                        messages = event["messages"]
                        continue
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            yield json.dumps(
                {"type": "agent_step", "step": {"id": "model_call", "label": "调用模型", "status": "running", "detail": config["model"]}},
                ensure_ascii=False,
            ) + "\n"
            async for chunk in models.chat_stream(config["provider"], config["apiKey"], config["model"], messages, config.get("baseUrl", "")):
                if chunk["type"] == "reasoning_delta":
                    reasoning += chunk["content"]
                elif chunk["type"] == "content_delta":
                    answer += chunk["content"]
                yield json.dumps(chunk, ensure_ascii=False) + "\n"
            yield json.dumps(
                {"type": "agent_step", "step": {"id": "model_call", "label": "调用模型", "status": "done", "detail": "回复生成完成"}},
                ensure_ascii=False,
            ) + "\n"
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
