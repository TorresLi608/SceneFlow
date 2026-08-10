from __future__ import annotations

import json
from typing import Any

from sqlalchemy import update
from sqlmodel import Session, select

from app.core.config import MAX_CONTEXT_TOKENS
from app.llms.registry import models
from app.models import ChatMessage, ChatSession
from app.utils.common import now


RECENT_MESSAGES_TO_KEEP = 20


def estimate_tokens(text: str) -> int:
    ascii_chars = 0
    cjk_chars = 0
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            cjk_chars += 1
        else:
            ascii_chars += 1
    return cjk_chars + max(1, ascii_chars // 4)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif item.get("type") in {"image", "image_url"}:
                    parts.append("[image attachment]")
                elif item.get("type") == "file":
                    parts.append("[file attachment]")
        return "\n".join(parts)
    return str(content or "")


def estimate_messages(messages: list[dict[str, Any]]) -> int:
    return sum(estimate_tokens(message["role"]) + estimate_tokens(_content_text(message["content"])) for message in messages)


def _message_rows_after(session: Session, session_id: str, created_after: str) -> list[ChatMessage]:
    conditions = [ChatMessage.session_id == session_id]
    if created_after:
        conditions.append(ChatMessage.created_at > created_after)
    return list(session.exec(select(ChatMessage).where(*conditions).order_by(ChatMessage.created_at.asc())).all())


def _attachment_parts(item: ChatMessage) -> list[dict[str, Any]]:
    if item.role != "user" or not item.attachments:
        return []
    try:
        attachments = json.loads(item.attachments)
    except json.JSONDecodeError:
        return []
    parts: list[dict[str, Any]] = []
    for attachment in attachments if isinstance(attachments, list) else []:
        if not isinstance(attachment, dict):
            continue
        for part in attachment.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                text = str(part.get("text") or "")
                if text:
                    parts.append({"type": "text", "text": text})
            elif part.get("type") == "image":
                image = str(part.get("image") or "")
                if image:
                    parts.append({"type": "image_url", "image_url": {"url": image}})
            elif part.get("type") == "file":
                name = str(part.get("filename") or attachment.get("name") or "file")
                mime_type = str(part.get("mimeType") or attachment.get("contentType") or "application/octet-stream")
                parts.append({"type": "text", "text": f"[Uploaded file: {name}, {mime_type}]"})
    return parts


def _message_content(item: ChatMessage) -> Any:
    content = item.content or ""
    parts = _attachment_parts(item)
    if not parts:
        return content
    result: list[dict[str, Any]] = []
    if content.strip():
        result.append({"type": "text", "text": content})
    result.extend(parts)
    return result


def _as_messages(summary: str, history: list[ChatMessage]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if summary.strip():
        messages.append(
            {
                "role": "system",
                "content": "Conversation memory summary. Treat this as prior context, not as a new user request:\n"
                + summary.strip(),
            }
        )
    messages.extend({"role": item.role, "content": _message_content(item)} for item in history)
    return messages


def _format_history(summary: str, history: list[ChatMessage]) -> str:
    parts = []
    if summary.strip():
        parts.append("Existing summary:\n" + summary.strip())
    parts.extend(f"{item.role}: {_content_text(_message_content(item))}" for item in history)
    return "\n\n".join(parts)


def _load_context(session: Session, session_id: str) -> tuple[str, list[ChatMessage], list[dict[str, Any]]]:
    chat = session.exec(select(ChatSession).where(ChatSession.id == session_id)).first()
    summary = (chat.context_summary or "") if chat else ""
    summary_until = (chat.context_summary_until or "") if chat else ""
    history = _message_rows_after(session, session_id, summary_until)
    return summary, history, _as_messages(summary, history)


async def _compress_context(
    session: Session,
    session_id: str,
    config: dict[str, Any],
    summary: str,
    history: list[ChatMessage],
) -> tuple[list[dict[str, Any]], int] | None:
    if estimate_messages(_as_messages(summary, history)) <= MAX_CONTEXT_TOKENS or len(history) <= RECENT_MESSAGES_TO_KEEP:
        return None
    old_messages = history[:-RECENT_MESSAGES_TO_KEEP]
    recent_messages = history[-RECENT_MESSAGES_TO_KEEP:]
    summary = await models.summarize_context(
        config["provider"],
        config["apiKey"],
        config["model"],
        _format_history(summary, old_messages),
        config.get("baseUrl", ""),
    )
    session.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id)
        .values(context_summary=summary, context_summary_until=old_messages[-1].created_at, updated_at=now()),
        execution_options={"synchronize_session": "fetch"},
    )
    return _as_messages(summary, recent_messages), len(recent_messages)


async def build_context_messages(
    session: Session,
    session_id: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    summary, history, messages = _load_context(session, session_id)
    compressed = await _compress_context(session, session_id, config, summary, history)
    return compressed[0] if compressed else messages


async def stream_context_messages(
    session: Session,
    session_id: str,
    config: dict[str, Any],
):
    yield _step("load_context", "加载历史上下文", "running")
    summary, history, messages = _load_context(session, session_id)
    yield _step(
        "load_context",
        "加载历史上下文",
        "done",
        f"{len(history)} 条历史，约 {estimate_messages(messages)} tokens",
    )
    if estimate_messages(messages) > MAX_CONTEXT_TOKENS and len(history) > RECENT_MESSAGES_TO_KEEP:
        yield _step("compress_context", "压缩长期记忆", "running", f"上下文超过 {MAX_CONTEXT_TOKENS} token 预算")
        compressed = await _compress_context(session, session_id, config, summary, history)
        if compressed:
            messages, recent_count = compressed
            yield _step("compress_context", "压缩长期记忆", "done", f"保留最近 {recent_count} 条明细消息")
    yield {"type": "context_ready", "messages": messages}


def _step(step: str, label: str, status: str, detail: str = "") -> dict[str, Any]:
    return {"type": "agent_step", "step": {"id": step, "label": label, "status": status, "detail": detail}}


if __name__ == "__main__":
    assert estimate_tokens("你好") == 2
    assert estimate_tokens("hello world") >= 2
