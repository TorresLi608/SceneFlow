from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import HTTPException

from config_service import normalize_base_url, normalize_model, normalize_provider, validate_config_fields
from context_graph import build_context_messages
from database import row, rows
from model import pick_model
from security import decrypt
from serializers import chat_message_json, chat_session_json
from utils import new_id, now

CHAT_PURPOSES = ("script", "general")


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


def begin_chat_turn(
    conn: sqlite3.Connection,
    session_id: str,
    user_id: int,
    content: str,
    config_id: int | None,
    official_config_id: int | None = None,
) -> tuple[dict[str, Any], sqlite3.Row]:
    content = content.strip()
    if not content:
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
    user_message = save_chat_message(conn, session_id, "user", content, config["provider"], config["model"])
    return config, user_message


async def prepare_chat_turn(
    conn: sqlite3.Connection,
    session_id: str,
    user_id: int,
    content: str,
    config_id: int | None,
    official_config_id: int | None = None,
) -> tuple[dict[str, Any], sqlite3.Row, list[dict[str, str]]]:
    config, user_message = begin_chat_turn(conn, session_id, user_id, content, config_id, official_config_id)
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
) -> sqlite3.Row:
    message_id = new_id("msg")
    stamp = now()
    conn.execute(
        "INSERT INTO chat_messages (id, created_at, session_id, role, content, reasoning, provider, model_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (message_id, stamp, session_id, role, content, reasoning, provider, model),
    )
    conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (stamp, session_id))
    return row(conn, "SELECT * FROM chat_messages WHERE id=?", (message_id,))
