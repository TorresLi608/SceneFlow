from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from database import row, rows
from model_registry import models
from utils import now


MAX_CONTEXT_TOKENS = 1_000_000
RECENT_MESSAGES_TO_KEEP = 20


@dataclass
class ContextRuntime:
    conn: sqlite3.Connection
    session_id: str
    config: dict[str, Any]


class ContextState(TypedDict, total=False):
    summary: str
    history: list[sqlite3.Row]
    messages: list[dict[str, str]]


def estimate_tokens(text: str) -> int:
    ascii_chars = 0
    cjk_chars = 0
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            cjk_chars += 1
        else:
            ascii_chars += 1
    return cjk_chars + max(1, ascii_chars // 4)


def estimate_messages(messages: list[dict[str, str]]) -> int:
    return sum(estimate_tokens(message["role"]) + estimate_tokens(message["content"]) for message in messages)


def _message_rows_after(conn: sqlite3.Connection, session_id: str, created_after: str) -> list[sqlite3.Row]:
    if created_after:
        return rows(
            conn,
            "SELECT role, content, created_at FROM chat_messages WHERE session_id=? AND created_at>? ORDER BY created_at ASC",
            (session_id, created_after),
        )
    return rows(
        conn,
        "SELECT role, content, created_at FROM chat_messages WHERE session_id=? ORDER BY created_at ASC",
        (session_id,),
    )


def _as_messages(summary: str, history: list[sqlite3.Row]) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": "You are SceneFlow Assistant. Answer clearly and concisely."}]
    if summary.strip():
        messages.append(
            {
                "role": "system",
                "content": "Conversation memory summary. Treat this as prior context, not as a new user request:\n"
                + summary.strip(),
            }
        )
    messages.extend({"role": item["role"], "content": item["content"]} for item in history)
    return messages


def _format_history(summary: str, history: list[sqlite3.Row]) -> str:
    parts = []
    if summary.strip():
        parts.append("Existing summary:\n" + summary.strip())
    parts.extend(f"{item['role']}: {item['content']}" for item in history)
    return "\n\n".join(parts)


def _emit_step(runtime: Runtime[ContextRuntime], step: str, label: str, status: str, detail: str = "") -> None:
    runtime.stream_writer(
        {
            "type": "agent_step",
            "step": {
                "id": step,
                "label": label,
                "status": status,
                "detail": detail,
            },
        }
    )


async def _load_context(state: ContextState, runtime: Runtime[ContextRuntime]) -> ContextState:
    _emit_step(runtime, "load_context", "加载历史上下文", "running")
    conn = runtime.context.conn
    session = row(conn, "SELECT context_summary, context_summary_until FROM chat_sessions WHERE id=?", (runtime.context.session_id,))
    summary = (session["context_summary"] or "") if session else ""
    summary_until = (session["context_summary_until"] or "") if session else ""
    history = _message_rows_after(conn, runtime.context.session_id, summary_until)
    messages = _as_messages(summary, history)
    _emit_step(
        runtime,
        "load_context",
        "加载历史上下文",
        "done",
        f"{len(history)} 条历史，约 {estimate_messages(messages)} tokens",
    )
    return {**state, "summary": summary, "history": history, "messages": messages}


def _route_context(state: ContextState) -> Literal["compress", "done"]:
    if estimate_messages(state["messages"]) <= MAX_CONTEXT_TOKENS:
        return "done"
    return "compress" if len(state["history"]) > RECENT_MESSAGES_TO_KEEP else "done"


async def _compress_context(state: ContextState, runtime: Runtime[ContextRuntime]) -> ContextState:
    history = state["history"]
    old_messages = history[:-RECENT_MESSAGES_TO_KEEP]
    recent_messages = history[-RECENT_MESSAGES_TO_KEEP:]
    if not old_messages:
        return {**state, "history": recent_messages, "messages": _as_messages(state["summary"], recent_messages)}

    _emit_step(runtime, "compress_context", "压缩长期记忆", "running", "上下文超过 1M token 预算")
    summary = await models.summarize_context(
        runtime.context.config["provider"],
        runtime.context.config["apiKey"],
        runtime.context.config["model"],
        _format_history(state["summary"], old_messages),
        runtime.context.config.get("baseUrl", ""),
    )
    summary_until = old_messages[-1]["created_at"]
    runtime.context.conn.execute(
        "UPDATE chat_sessions SET context_summary=?, context_summary_until=?, updated_at=? WHERE id=?",
        (summary, summary_until, now(), runtime.context.session_id),
    )
    _emit_step(runtime, "compress_context", "压缩长期记忆", "done", f"保留最近 {len(recent_messages)} 条明细消息")
    return {**state, "summary": summary, "history": recent_messages, "messages": _as_messages(summary, recent_messages)}


def _build_graph():
    graph = StateGraph(ContextState, context_schema=ContextRuntime)
    graph.add_node("load", _load_context)
    graph.add_node("compress", _compress_context)
    graph.add_edge(START, "load")
    graph.add_conditional_edges("load", _route_context, {"compress": "compress", "done": END})
    graph.add_edge("compress", END)
    return graph.compile()


_CONTEXT_GRAPH = _build_graph()


async def build_context_messages(
    conn: sqlite3.Connection,
    session_id: str,
    config: dict[str, Any],
) -> list[dict[str, str]]:
    state = await _CONTEXT_GRAPH.ainvoke({}, context=ContextRuntime(conn, session_id, config))
    return state["messages"]


async def stream_context_messages(
    conn: sqlite3.Connection,
    session_id: str,
    config: dict[str, Any],
):
    final_state: ContextState = {}
    async for mode, chunk in _CONTEXT_GRAPH.astream(
        {},
        context=ContextRuntime(conn, session_id, config),
        stream_mode=["custom", "values"],
    ):
        if mode == "custom":
            yield chunk
        elif mode == "values":
            final_state = chunk
    yield {"type": "context_ready", "messages": final_state.get("messages", [])}


if __name__ == "__main__":
    assert estimate_tokens("你好") == 2
    assert estimate_tokens("hello world") >= 2
