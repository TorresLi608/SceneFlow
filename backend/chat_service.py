from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import HTTPException

from config_service import active_model_config, normalize_base_url, normalize_model, normalize_provider, official_model_config, validate_config_fields
from database import row, rows
from model import pick_model
from security import decrypt
from serializers import chat_message_json, chat_session_json
from utils import new_id, now

SYSTEM_PROMPT = "You are SceneFlow Assistant. Answer clearly and concisely."


def chat_config(conn: sqlite3.Connection, user_id: int, config_id: int | None, official_config_id: int | None = None) -> dict[str, Any]:
    if official_config_id is not None:
        config = official_model_config(conn, official_config_id, "script", "智能问答")
        return {**config, "configId": None, "officialConfigId": official_config_id}

    if config_id is None:
        config = active_model_config(conn, user_id, "script", "智能问答")
        return {**config, "configId": None, "officialConfigId": None}

    config = row(conn, "SELECT * FROM user_configs WHERE id=? AND user_id=? AND deleted_at IS NULL", (config_id, user_id))
    if not config:
        raise HTTPException(404, "config not found")
    if config["purpose"] != "script":
        raise HTTPException(400, "chat only supports script/prompt configs")
    provider = normalize_provider(config["provider"])
    base_url = normalize_base_url(config["base_url"] or "")
    model = pick_model(provider, normalize_model(provider, config["model_name"] or ""))
    validate_config_fields("script", provider, model, base_url)
    if not bool(config["is_verified"]):
        raise HTTPException(400, "config is not verified")
    api_key = decrypt(config["encrypted_key"]).strip()
    if not api_key:
        raise HTTPException(400, "config missing API key")
    return {"provider": provider, "model": model, "apiKey": api_key, "baseUrl": base_url, "configId": config_id, "officialConfigId": None}


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


def prepare_chat_turn(
    conn: sqlite3.Connection,
    session_id: str,
    user_id: int,
    content: str,
    config_id: int | None,
    official_config_id: int | None = None,
) -> tuple[dict[str, Any], sqlite3.Row, list[dict[str, str]]]:
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
    history = rows(
        conn,
        "SELECT role, content FROM (SELECT role, content, created_at FROM chat_messages WHERE session_id=? ORDER BY created_at DESC LIMIT 40) ORDER BY created_at ASC",
        (session_id,),
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend({"role": message["role"], "content": message["content"]} for message in history)
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
