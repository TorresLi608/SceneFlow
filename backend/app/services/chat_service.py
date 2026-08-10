from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import case, func, update
from sqlmodel import Session, select

from app.core.security import decrypt
from app.graph.graphs.context_graph import build_context_messages
from app.llms.router import pick_model
from app.models import ChatMessage, ChatSession, ModelConfig, UserOfficialConfigDefault
from app.schemas.serializers import chat_message_json, chat_session_json
from app.services.config_service import normalize_base_url, normalize_model, normalize_provider, validate_config_fields
from app.services.usage_service import require_model_balance
from app.utils.attachment_parser import attachment_text_part
from app.utils.common import new_id, now

CHAT_PURPOSES = ("script", "general")
MAX_CHAT_ATTACHMENTS = 5
MAX_CHAT_ATTACHMENT_CHARS = 8_000_000


def _row_chat_config(config: ModelConfig | None, config_id: int | None = None, official_config_id: int | None = None) -> dict[str, Any]:
    if not config:
        raise HTTPException(400, "智能问答未配置可用的默认模型。请先使用官方配置或添加自定义配置。")
    if config.purpose not in CHAT_PURPOSES:
        raise HTTPException(400, "chat only supports text configs")
    if not bool(config.is_enabled):
        raise HTTPException(400, "config is disabled")
    provider = normalize_provider(config.provider)
    base_url = normalize_base_url(config.base_url or "")
    model = pick_model(provider, normalize_model(provider, config.model_name or ""))
    validate_config_fields(config.purpose, provider, model, base_url)
    if not bool(config.is_verified):
        raise HTTPException(400, "config is not verified")
    api_key = decrypt(config.encrypted_key).strip()
    if not api_key:
        raise HTTPException(400, "config missing API key")
    return {"provider": provider, "model": model, "apiKey": api_key, "baseUrl": base_url, "configId": config_id, "officialConfigId": official_config_id}


def _active_chat_config(session: Session, user_id: int) -> dict[str, Any]:
    # Same precedence as app.services.config_service.active_model_config: explicit official
    # default > the user's own active config > the system-wide official default.
    config = session.exec(
        select(ModelConfig)
        .join(UserOfficialConfigDefault, UserOfficialConfigDefault.official_config_id == ModelConfig.id)
        .where(
            UserOfficialConfigDefault.user_id == user_id,
            UserOfficialConfigDefault.purpose.in_(CHAT_PURPOSES),
            ModelConfig.source == "official",
            ModelConfig.is_enabled.is_(True),
            ModelConfig.is_verified.is_(True),
            ModelConfig.deleted_at.is_(None),
        )
        .order_by(case((UserOfficialConfigDefault.purpose == "script", 0), else_=1))
        .limit(1)
    ).first()
    if config:
        return _row_chat_config(config, official_config_id=config.id)

    config = session.exec(
        select(ModelConfig)
        .where(
            ModelConfig.source == "user",
            ModelConfig.user_id == user_id,
            ModelConfig.purpose.in_(CHAT_PURPOSES),
            ModelConfig.is_active.is_(True),
            ModelConfig.is_enabled.is_(True),
            ModelConfig.deleted_at.is_(None),
        )
        .order_by(case((ModelConfig.purpose == "script", 0), else_=1), ModelConfig.updated_at.desc())
        .limit(1)
    ).first()
    if config:
        return _row_chat_config(config, config_id=config.id)

    config = session.exec(
        select(ModelConfig)
        .where(
            ModelConfig.source == "official",
            ModelConfig.purpose.in_(CHAT_PURPOSES),
            ModelConfig.is_active.is_(True),
            ModelConfig.is_enabled.is_(True),
            ModelConfig.is_verified.is_(True),
            ModelConfig.deleted_at.is_(None),
        )
        .order_by(case((ModelConfig.purpose == "script", 0), else_=1), ModelConfig.updated_at.desc())
        .limit(1)
    ).first()
    return _row_chat_config(config, official_config_id=config.id if config else None)


def chat_config(session: Session, user_id: int, config_id: int | None, official_config_id: int | None = None) -> dict[str, Any]:
    if official_config_id is not None:
        config = session.exec(
            select(ModelConfig).where(
                ModelConfig.id == official_config_id,
                ModelConfig.source == "official",
                ModelConfig.deleted_at.is_(None),
            )
        ).first()
        return _row_chat_config(config, official_config_id=official_config_id)

    if config_id is None:
        return _active_chat_config(session, user_id)

    config = session.exec(
        select(ModelConfig).where(
            ModelConfig.id == config_id,
            ModelConfig.source == "user",
            ModelConfig.user_id == user_id,
            ModelConfig.deleted_at.is_(None),
        )
    ).first()
    return _row_chat_config(config, config_id=config_id)


def list_chat_sessions(session: Session, user_id: int) -> list[dict[str, Any]]:
    chats = session.exec(
        select(ChatSession)
        .where(ChatSession.user_id == user_id, ChatSession.deleted_at.is_(None))
        .order_by(ChatSession.updated_at.desc())
    ).all()
    return [chat_session_json(chat) for chat in chats]


def create_chat_session(session: Session, user_id: int, title: str, config_id: int | None, official_config_id: int | None = None) -> dict[str, Any]:
    config = chat_config(session, user_id, config_id, official_config_id)
    stamp = now()
    chat = ChatSession(
        id=new_id("chat"),
        created_at=stamp,
        updated_at=stamp,
        user_id=user_id,
        title=(title.strip() or "新对话")[:80],
        config_id=config["configId"],
        official_config_id=config["officialConfigId"],
        provider=config["provider"],
        model_name=config["model"],
    )
    session.add(chat)
    session.flush()
    return chat_session_json(chat)


def require_session(session: Session, session_id: str, user_id: int) -> ChatSession:
    chat = session.exec(select(ChatSession).where(ChatSession.id == session_id, ChatSession.deleted_at.is_(None))).first()
    if not chat:
        raise HTTPException(404, "chat session not found")
    if chat.user_id != user_id:
        raise HTTPException(403, "chat session does not belong to current user")
    return chat


def list_chat_messages(session: Session, session_id: str, user_id: int) -> list[dict[str, Any]]:
    require_session(session, session_id, user_id)
    messages = session.exec(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
    ).all()
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


def delete_chat_session(session: Session, session_id: str, user_id: int) -> None:
    chat = require_session(session, session_id, user_id)
    stamp = now()
    chat.deleted_at = stamp
    chat.updated_at = stamp
    session.add(chat)


def begin_chat_turn(
    session: Session,
    session_id: str,
    user_id: int,
    content: str,
    attachments: Any,
    config_id: int | None,
    official_config_id: int | None = None,
) -> tuple[dict[str, Any], ChatMessage]:
    content = content.strip()
    normalized_attachments = normalize_chat_attachments(attachments)
    if not content and not normalized_attachments:
        raise HTTPException(400, "content is required")
    if len(content) > 12000:
        raise HTTPException(400, "content is too long")

    chat = require_session(session, session_id, user_id)
    config = chat_config(
        session,
        user_id,
        config_id if config_id else chat.config_id,
        official_config_id if official_config_id else chat.official_config_id,
    )
    require_model_balance(session, user_id, config)
    user_message = save_chat_message(session, session_id, "user", content, config["provider"], config["model"], attachments=normalized_attachments)
    if content:
        # A single conditional statement so the title is only claimed by the very first user message.
        user_message_count = (
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.session_id == session_id, ChatMessage.role == "user")
            .scalar_subquery()
        )
        session.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id, user_message_count == 1)
            .values(title=" ".join(content.split())[:80]),
            execution_options={"synchronize_session": "fetch"},
        )
    return config, user_message


async def prepare_chat_turn(
    session: Session,
    session_id: str,
    user_id: int,
    content: str,
    attachments: Any,
    config_id: int | None,
    official_config_id: int | None = None,
) -> tuple[dict[str, Any], ChatMessage, list[dict[str, Any]]]:
    config, user_message = begin_chat_turn(session, session_id, user_id, content, attachments, config_id, official_config_id)
    messages = await build_context_messages(session, session_id, config)
    return config, user_message, messages


def save_chat_message(
    session: Session,
    session_id: str,
    role: str,
    content: str,
    provider: str = "",
    model: str = "",
    reasoning: str = "",
    attachments: list[dict[str, Any]] | None = None,
) -> ChatMessage:
    stamp = now()
    message = ChatMessage(
        id=new_id("msg"),
        created_at=stamp,
        session_id=session_id,
        role=role,
        content=content,
        attachments=json.dumps(attachments or [], ensure_ascii=False),
        reasoning=reasoning,
        provider=provider,
        model_name=model,
    )
    session.add(message)
    session.flush()
    session.execute(
        update(ChatSession).where(ChatSession.id == session_id).values(updated_at=stamp),
        execution_options={"synchronize_session": "fetch"},
    )
    return message


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
