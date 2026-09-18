from __future__ import annotations

import json
from dataclasses import dataclass
import re
import time
from typing import Any, Literal

from langchain.agents import create_agent
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool, ToolException

from app.core.database import db
from app.models import User
from app.llms.registry import models
from app.llms.router import _content_text, _lc_messages, _openai_image_size, _reasoning_text
from app.services.artifact_service import save_document_artifact, save_image_artifact, tool_result
from app.services.error_log_service import error_log_json, find_error_logs
from app.services.usage_service import aggregate_token_usage, record_usage, require_model_balance


AGENT_SYSTEM_PROMPT = """You are SceneFlow Assistant. Answer clearly and concisely.
Match the user's language unless they ask for another language.
You can generate images, PDF files, and Word documents with tools.
- When the user asks for a file or image and has supplied enough information, call the matching tool instead of only describing how to make it.
- For PDF and Word tools, write the complete document content yourself. Use simple Markdown headings and lists; do not include the title again in the content.
- When generating images or documents with tools, do NOT manually copy long artifact URLs or raw image/document markdown in your response. The system will automatically attach the generated image or document to your reply. Simply describe your creative work or summarize the result concisely to the user.
- Never claim a file was generated unless the tool returned a successful result.
- If a tool fails, do not retry it more than once; tell the user briefly what failed and what they can do.
- Do not expose internal paths, API keys, tool arguments, or implementation details.
- When a super admin asks why a request failed, use the error-log tool before proposing a fix.
"""

TOOL_LABELS = {
    "generate_image": "生成图片",
    "generate_pdf": "生成 PDF",
    "generate_word_document": "生成 Word 文档",
    "search_error_logs": "查询错误日志",
}
TOOL_FAILURE_LABELS = {
    "generate_image": "图片生成失败",
    "generate_pdf": "PDF 生成失败",
    "generate_word_document": "Word 文档生成失败",
    "search_error_logs": "错误日志查询失败",
}
MAX_FAILURE_REASON_CHARS = 200


@dataclass
class AgentResult:
    content: str
    usage: dict[str, int]


def _tool_detail(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("title") or value.get("prompt") or "")[:120]
    content = getattr(value, "content", value)
    return str(content or "")[:160]


def create_chat_tools(session_id: str, image_config: dict[str, Any] | None, user_id: int | None = None) -> list[StructuredTool]:
    can_read_error_logs = False
    if user_id is not None:
        with db() as session:
            user = session.get(User, user_id)
            can_read_error_logs = bool(user and user.role == "superAdmin")

    async def generate_image(prompt: str, title: str = "生成图片", aspect_ratio: Literal["1:1", "3:2", "2:3", "16:9", "9:16"] = "1:1") -> str:
        """Generate an image and return a signed image URL plus Markdown. Use when the user asks to create, draw, render, or illustrate an image."""
        prompt = prompt.strip()
        if not prompt:
            raise ToolException("图片提示词不能为空")
        if len(prompt) > 4_000:
            raise ToolException("图片提示词过长，请精简后重试")
        if not image_config:
            raise ToolException("尚未配置图片生成模型，请先在设置中启用一个图片模型")
        try:
            started_at = time.monotonic()
            if user_id is not None:
                with db() as session:
                    require_model_balance(session, user_id, image_config)
            provider = image_config["provider"]
            size = aspect_ratio if provider in {"gemini", "qwen"} else _openai_image_size(aspect_ratio)
            quality = "2K" if provider == "gemini" else "medium"
            result = await models.generate_image(
                image_config["apiKey"],
                image_config["model"],
                prompt,
                size,
                quality,
                image_config.get("baseUrl", ""),
                provider,
            )
            if user_id is not None:
                record_usage(user_id, image_config, "agent_image", started_at, quantity=1)
            return tool_result(save_image_artifact(session_id, title.strip()[:160], result.data, result.format))
        except Exception as exc:
            # HTTPException (balance gate) stringifies as "402: ..."; keep only the user-facing detail.
            raise ToolException(str(getattr(exc, "detail", None) or exc)) from exc

    async def generate_pdf(title: str, content: str) -> str:
        """Create a polished PDF from a title and complete Markdown-like content. Use headings with #, ##, or ### and lists with - or numbered items."""
        try:
            return tool_result(save_document_artifact(session_id, "pdf", title, content))
        except Exception as exc:
            raise ToolException(str(exc)) from exc

    async def generate_word_document(title: str, content: str) -> str:
        """Create a polished Word DOCX file from a title and complete Markdown-like content. Use headings with #, ##, or ### and lists with - or numbered items."""
        try:
            return tool_result(save_document_artifact(session_id, "docx", title, content))
        except Exception as exc:
            raise ToolException(str(exc)) from exc

    def search_error_logs(search: str = "", request_id: str = "", project_id: str = "", error_code: str = "") -> str:
        """Search redacted server failures by text, request ID, project ID, or error code. Available to super admins for diagnosis only."""
        with db() as session:
            user = session.get(User, user_id) if user_id is not None else None
            if not user or user.role != "superAdmin":
                raise ToolException("error logs are only available to super admins")
            _, logs = find_error_logs(
                session,
                search=search,
                request_id=request_id,
                project_id=project_id,
                error_code=error_code,
                page_size=10,
            )
        return json.dumps([error_log_json(item) for item in logs], ensure_ascii=False)

    tools = [
        StructuredTool.from_function(coroutine=generate_image, name="generate_image", description=generate_image.__doc__),
        StructuredTool.from_function(coroutine=generate_pdf, name="generate_pdf", description=generate_pdf.__doc__),
        StructuredTool.from_function(coroutine=generate_word_document, name="generate_word_document", description=generate_word_document.__doc__),
    ]
    if can_read_error_logs:
        tools.append(StructuredTool.from_function(func=search_error_logs, name="search_error_logs", description=search_error_logs.__doc__))
    for item in tools:
        item.handle_tool_error = True
    return tools


def _agent(config: dict[str, Any], session_id: str, image_config: dict[str, Any] | None, user_id: int | None = None):
    model = models.chat_model(
        config["provider"],
        config["apiKey"],
        config["model"],
        config.get("baseUrl", ""),
        temperature=0.3,
        max_tokens=4096,
    )
    return create_agent(
        model=model,
        tools=create_chat_tools(session_id, image_config, user_id),
        system_prompt=AGENT_SYSTEM_PROMPT,
        name="sceneflow_assistant",
    )


def _final_answer(output: Any) -> str:
    messages = output.get("messages", []) if isinstance(output, dict) else []
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = _content_text(message.content).strip()
            if content:
                return content
    return ""


def _tool_status(output: Any) -> str:
    # `handle_tool_error=True` turns a ToolException into a ToolMessage with status "error"
    # instead of an on_tool_error event, so the status is the only reliable failure signal.
    return str(getattr(output, "status", "") or "success")


def _tool_payload(output: Any) -> dict[str, Any] | None:
    content = getattr(output, "content", output)
    if not isinstance(content, str):
        return None
    try:
        payload = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _tool_output_detail(output: Any) -> str:
    """Execution-panel text for a finished tool: the artifact name, never its signed URL."""
    payload = _tool_payload(output)
    if payload and payload.get("kind"):
        return str(payload.get("filename") or payload.get("title") or payload["kind"])[:160]
    return _tool_detail(output)


def _failure_reason(output: Any) -> str:
    reason = re.sub(r"\s+", " ", _content_text(getattr(output, "content", output))).strip()
    return reason[:MAX_FAILURE_REASON_CHARS] or "未知错误"


def _failure_notice(tool_name: str, output: Any) -> str:
    label = TOOL_FAILURE_LABELS.get(tool_name) or f"{TOOL_LABELS.get(tool_name, tool_name)}失败"
    return f"> ⚠️ {label}：{_failure_reason(output)}"


def _tool_messages(output: Any) -> list[Any]:
    messages = output.get("messages", []) if isinstance(output, dict) else []
    return [message for message in messages if getattr(message, "type", "") == "tool"]


def _artifact_markdowns(tool_messages: list[Any]) -> list[str]:
    markdowns: list[str] = []
    for message in tool_messages:
        if _tool_status(message) == "error":
            continue
        payload = _tool_payload(message)
        markdown = str(payload.get("markdown") or "").strip() if payload else ""
        if markdown and markdown not in markdowns:
            markdowns.append(markdown)
    return markdowns


def _failure_notices(tool_messages: list[Any]) -> list[str]:
    notices: list[str] = []
    for message in tool_messages:
        if _tool_status(message) != "error":
            continue
        notice = _failure_notice(str(getattr(message, "name", "") or ""), message)
        if notice not in notices:
            notices.append(notice)
    return notices


def _reconcile_tool_artifacts(answer: str, tool_messages: list[Any]) -> tuple[str, list[str]]:
    """Ensure artifacts are properly mounted without duplicate or broken URLs from model hallucination.

    If the model tried to copy a broken or hallucinated artifact link, replace it with the canonical
    markdown. If the artifact is missing entirely from the answer, return it in missing_blocks.
    """
    reconciled = answer
    missing_blocks: list[str] = []

    for message in tool_messages:
        if _tool_status(message) == "error":
            continue
        payload = _tool_payload(message)
        if not payload:
            continue
        markdown = str(payload.get("markdown") or "").strip()
        url = str(payload.get("url") or "").strip()
        if not markdown or not url:
            continue

        if markdown in reconciled or url in reconciled:
            continue

        title = str(payload.get("title") or payload.get("filename") or "").strip()
        replaced = False
        if title:
            pattern = re.compile(rf"!\[{re.escape(title)}\]\([^\)]+\)")
            if pattern.search(reconciled):
                reconciled = pattern.sub(markdown, reconciled, count=1)
                replaced = True

        if not replaced:
            missing_blocks.append(markdown)

    for message in tool_messages:
        if _tool_status(message) != "error":
            continue
        notice = _failure_notice(str(getattr(message, "name", "") or ""), message)
        if notice not in reconciled:
            missing_blocks.append(notice)

    return reconciled, missing_blocks


def _missing_tool_outcomes(tool_messages: list[Any], answer: str) -> list[str]:
    _, missing = _reconcile_tool_artifacts(answer, tool_messages)
    return missing


def _answer_with_artifacts(output: Any, tool_messages: list[Any] | None = None) -> str:
    raw_answer = _final_answer(output)
    messages = _tool_messages(output) if tool_messages is None else tool_messages
    answer, missing = _reconcile_tool_artifacts(raw_answer, messages)
    if missing:
        answer = (answer + "\n\n" if answer else "") + "\n\n".join(missing)
    return answer


async def run_chat_agent(
    config: dict[str, Any],
    session_id: str,
    messages: list[dict[str, Any]],
    image_config: dict[str, Any] | None,
    user_id: int | None = None,
) -> AgentResult:
    agent = _agent(config, session_id, image_config, user_id)
    with get_usage_metadata_callback() as usage_callback:
        output = await agent.ainvoke(
            {"messages": _lc_messages(messages, config["provider"])},
            config={"recursion_limit": 12},
        )
    answer = _answer_with_artifacts(output)
    if not answer:
        raise ValueError("empty content from agent")
    usage = aggregate_token_usage(usage_callback.usage_metadata)
    if not any(usage.values()):
        usage = aggregate_token_usage(
            {str(index): message.usage_metadata for index, message in enumerate(output.get("messages", [])) if isinstance(message, AIMessage) and message.usage_metadata}
        )
    return AgentResult(answer, usage)


async def stream_chat_agent(
    config: dict[str, Any],
    session_id: str,
    messages: list[dict[str, Any]],
    image_config: dict[str, Any] | None,
    user_id: int | None = None,
):
    agent = _agent(config, session_id, image_config, user_id)
    final_output: Any = None
    streamed_content = ""
    tool_outputs: list[Any] = []
    with get_usage_metadata_callback() as usage_callback:
        async for event in agent.astream_events(
            {"messages": _lc_messages(messages, config["provider"])},
            config={"recursion_limit": 12},
            version="v2",
        ):
            event_type = event["event"]
            if event_type == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                reasoning = _reasoning_text(chunk.content, chunk.additional_kwargs)
                content = _content_text(chunk.content)
                if reasoning:
                    yield {"type": "reasoning_delta", "content": reasoning}
                if content:
                    streamed_content += content
                    yield {"type": "content_delta", "content": content}
            elif event_type == "on_tool_start":
                yield {
                    "type": "agent_step",
                    "step": {
                        "id": "tool_" + event["run_id"],
                        "label": TOOL_LABELS.get(event["name"], event["name"]),
                        "status": "running",
                        "detail": _tool_detail(event["data"].get("input")),
                    },
                }
            elif event_type == "on_tool_end":
                output = event["data"].get("output")
                tool_outputs.append(output)
                failed = _tool_status(output) == "error"
                yield {
                    "type": "agent_step",
                    "step": {
                        "id": "tool_" + event["run_id"],
                        "label": TOOL_LABELS.get(event["name"], event["name"]),
                        "status": "error" if failed else "done",
                        "detail": _failure_reason(output)[:160] if failed else _tool_output_detail(output),
                    },
                }
            elif event_type == "on_tool_error":
                yield {
                    "type": "agent_step",
                    "step": {
                        "id": "tool_" + event["run_id"],
                        "label": TOOL_LABELS.get(event["name"], event["name"]),
                        "status": "error",
                        "detail": str(event["data"].get("error") or "tool failed")[:160],
                    },
                }
            elif event_type == "on_chain_end" and not event["parent_ids"]:
                final_output = event["data"].get("output")
    # Tool outcomes come from the observed tool events, so they survive a run whose root
    # on_chain_end never arrived (a stop or a provider failure after the tool finished).
    tool_messages = tool_outputs or _tool_messages(final_output)
    answer = _answer_with_artifacts(final_output, tool_messages)
    missing = _missing_tool_outcomes(tool_messages, streamed_content)
    if missing:
        yield {"type": "content_delta", "content": ("\n\n" if streamed_content else "") + "\n\n".join(missing)}
    usage = aggregate_token_usage(usage_callback.usage_metadata)
    if not any(usage.values()) and isinstance(final_output, dict):
        usage = aggregate_token_usage(
            {str(index): message.usage_metadata for index, message in enumerate(final_output.get("messages", [])) if isinstance(message, AIMessage) and message.usage_metadata}
        )
    yield {"type": "agent_complete", "content": answer, "usage": usage}
