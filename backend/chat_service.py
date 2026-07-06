from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import HTTPException

from attachment_parser import attachment_text_part
from config_service import normalize_base_url, normalize_model, normalize_provider, validate_config_fields
from context_graph import build_context_messages
from database import row, rows
from model import pick_model
from security import decrypt
from serializers import chat_message_json, chat_session_json
from utils import new_id, now

CHAT_PURPOSES = ("script", "general")
MAX_CHAT_ATTACHMENTS = 5
MAX_CHAT_ATTACHMENT_CHARS = 8_000_000


def _row_chat_config(config: sqlite3.Row | None, config_id: int | None = None, official_config_id: int | None = None) -> dict[str, Any]:
    if not config:
        raise HTTPException(400, "智能问答未配置可用的默认模型。请先使用官方配置或添加自定义配置。")
    if config["purpose"] not in CHAT_PURPOSES:
        raise HTTPException(400, "chat only supports text configs")
    if not bool(config["is_enabled"]):
        raise HTTPException(400, "config is disabled")
    provider = normalize_provider(config["provider"])
    base_url = normalize_base_url(config["base_url"] or "")
    model = pick_model(provider, normalize_model(provider, config["model_name"] or ""))
    validate_config_fields(config["purpose"], provider, model, base_url)
    if not bool(config["is_verified"]):
        raise HTTPException(400, "config is not verified")
    api_key = decrypt(config["encrypted_key"]).strip()
    if not api_key:
        raise HTTPException(400, "config missing API key")
    return {"provider": provider, "model": model, "apiKey": api_key, "baseUrl": base_url, "configId": config_id, "officialConfigId": official_config_id}


def _active_chat_config(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    config = row(
        conn,
        """SELECT * FROM user_configs
        WHERE user_id=? AND purpose IN ('script', 'general') AND is_active=1 AND is_enabled=1 AND deleted_at IS NULL
        ORDER BY CASE purpose WHEN 'script' THEN 0 ELSE 1 END, updated_at DESC LIMIT 1""",
        (user_id,),
    )
    if config:
        return _row_chat_config(config)

    config = row(
        conn,
        """SELECT official_model_configs.*
        FROM user_official_config_defaults
        JOIN official_model_configs ON official_model_configs.id=user_official_config_defaults.official_config_id
        WHERE user_official_config_defaults.user_id=?
          AND user_official_config_defaults.purpose IN ('script', 'general')
          AND official_model_configs.is_enabled=1
          AND official_model_configs.is_verified=1
          AND official_model_configs.deleted_at IS NULL
        ORDER BY CASE user_official_config_defaults.purpose WHEN 'script' THEN 0 ELSE 1 END LIMIT 1""",
        (user_id,),
    )
    if config:
        return _row_chat_config(config, official_config_id=config["id"])

    config = row(
        conn,
        """SELECT * FROM official_model_configs
        WHERE purpose IN ('script', 'general') AND is_active=1 AND is_enabled=1 AND is_verified=1 AND deleted_at IS NULL
        ORDER BY CASE purpose WHEN 'script' THEN 0 ELSE 1 END, updated_at DESC LIMIT 1""",
    )
    return _row_chat_config(config, official_config_id=config["id"] if config else None)


def chat_config(conn: sqlite3.Connection, user_id: int, config_id: int | None, official_config_id: int | None = None) -> dict[str, Any]:
    if official_config_id is not None:
        config = row(conn, "SELECT * FROM official_model_configs WHERE id=? AND deleted_at IS NULL", (official_config_id,))
        return _row_chat_config(config, official_config_id=official_config_id)

    if config_id is None:
        return _active_chat_config(conn, user_id)

    config = row(conn, "SELECT * FROM user_configs WHERE id=? AND user_id=? AND deleted_at IS NULL", (config_id, user_id))
    return _row_chat_config(config, config_id=config_id)


def list_chat_sessions(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    sessions = rows(
        conn,
        "SELECT * FROM chat_sessions WHERE user_id=? AND deleted_at IS NULL ORDER BY updated_at DESC",
        (user_id,),
    )
    return [chat_session_json(session) for session in sessions]


def create_chat_session(conn: sqlite3.Connection, user_id: int, title: str, config_id: int | None, official_config_id: int | None = None) -> dict[str, Any]:
    config = chat_config(conn, user_id, config_id, official_config_id)
    stamp = now()
    session_id = new_id("chat")
    conn.execute(
        """INSERT INTO chat_sessions
        (id, created_at, updated_at, user_id, title, config_id, official_config_id, provider, model_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, stamp, stamp, user_id, (title.strip() or "新对话")[:80], config["configId"], config["officialConfigId"], config["provider"], config["model"]),
    )
    session = row(conn, "SELECT * FROM chat_sessions WHERE id=?", (session_id,))
    return chat_session_json(session)


def require_session(conn: sqlite3.Connection, session_id: str, user_id: int) -> sqlite3.Row:
    session = row(conn, "SELECT * FROM chat_sessions WHERE id=? AND deleted_at IS NULL", (session_id,))
    if not session:
        raise HTTPException(404, "chat session not found")
    if session["user_id"] != user_id:
        raise HTTPException(403, "chat session does not belong to current user")
    return session


def list_chat_messages(conn: sqlite3.Connection, session_id: str, user_id: int) -> list[dict[str, Any]]:
    require_session(conn, session_id, user_id)
    messages = rows(conn, "SELECT * FROM chat_messages WHERE session_id=? ORDER BY created_at ASC", (session_id,))
    return [chat_message_json(message) for message in messages]


def normalize_chat_attachments(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HTTPException(400, "attachments must be an array")
    if len(value) > MAX_CHAT_ATTACHMENTS:
        raise HTTPException(400, f"最多只能上传 {MAX_CHAT_ATTACHMENTS} 个附件")

    total_chars = 0
    attachments: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise HTTPException(400, "invalid attachment")
        content = []
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type", "")).strip()
            if part_type == "text":
                text = str(part.get("text", ""))
                total_chars += len(text)
                content.append({"type": "text", "text": text})
            elif part_type == "image":
                image = str(part.get("image", ""))
                if not image.startswith("data:image/"):
                    raise HTTPException(400, "image attachments must be data URLs")
                total_chars += len(image)
                content.append({"type": "image", "image": image, "filename": str(part.get("filename") or item.get("name") or "image")[:160]})
            elif part_type == "file":
                data = str(part.get("data", ""))
                mime_type = str(part.get("mimeType", "application/octet-stream"))[:120]
                total_chars += len(data)
                filename = str(part.get("filename") or item.get("name") or "file")[:160]
                content.append({"type": "text", "text": attachment_text_part(data, mime_type, filename)})
            if total_chars > MAX_CHAT_ATTACHMENT_CHARS:
                raise HTTPException(400, "attachments are too large")
        if content:
            attachments.append(
                {
                    "id": str(item.get("id") or new_id("att"))[:120],
                    "type": str(item.get("type") or "file")[:40],
                    "name": str(item.get("name") or "attachment")[:160],
                    "contentType": str(item.get("contentType") or "")[:120],
                    "content": content,
                }
            )
    return attachments


def delete_chat_session(conn: sqlite3.Connection, session_id: str, user_id: int) -> None:
    require_session(conn, session_id, user_id)
    stamp = now()
    conn.execute("UPDATE chat_sessions SET deleted_at=?, updated_at=? WHERE id=?", (stamp, stamp, session_id))


def begin_chat_turn(
    conn: sqlite3.Connection,
    session_id: str,
    user_id: int,
    content: str,
    attachments: Any,
    config_id: int | None,
    official_config_id: int | None = None,
) -> tuple[dict[str, Any], sqlite3.Row]:
    content = content.strip()
    normalized_attachments = normalize_chat_attachments(attachments)
    if not content and not normalized_attachments:
        raise HTTPException(400, "content is required")
    if len(content) > 12000:
        raise HTTPException(400, "content is too long")

    session = require_session(conn, session_id, user_id)
    config = chat_config(
        conn,
        user_id,
        config_id if config_id else session["config_id"],
        official_config_id if official_config_id else session["official_config_id"],
    )
    user_message = save_chat_message(conn, session_id, "user", content, config["provider"], config["model"], attachments=normalized_attachments)
    return config, user_message


async def prepare_chat_turn(
    conn: sqlite3.Connection,
    session_id: str,
    user_id: int,
    content: str,
    attachments: Any,
    config_id: int | None,
    official_config_id: int | None = None,
) -> tuple[dict[str, Any], sqlite3.Row, list[dict[str, Any]]]:
    config, user_message = begin_chat_turn(conn, session_id, user_id, content, attachments, config_id, official_config_id)
    messages = await build_context_messages(conn, session_id, config)
    return config, user_message, messages


def save_chat_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str,
    provider: str = "",
    model: str = "",
    reasoning: str = "",
    attachments: list[dict[str, Any]] | None = None,
) -> sqlite3.Row:
    message_id = new_id("msg")
    stamp = now()
    conn.execute(
        "INSERT INTO chat_messages (id, created_at, session_id, role, content, attachments, reasoning, provider, model_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (message_id, stamp, session_id, role, content, json.dumps(attachments or [], ensure_ascii=False), reasoning, provider, model),
    )
    conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (stamp, session_id))
    return row(conn, "SELECT * FROM chat_messages WHERE id=?", (message_id,))


if __name__ == "__main__":
    sample = normalize_chat_attachments([{"name": "note.txt", "content": [{"type": "text", "text": "hello"}]}])
    assert sample[0]["content"][0]["text"] == "hello"
    file_sample = normalize_chat_attachments(
        [
            {
                "name": "code.py",
                "content": [{"type": "file", "data": "data:text/x-python;base64,cHJpbnQoJ2hpJyk=", "mimeType": "text/x-python", "filename": "code.py"}],
            }
        ]
    )
    assert "print('hi')" in file_sample[0]["content"][0]["text"]
