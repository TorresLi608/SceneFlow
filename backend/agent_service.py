from __future__ import annotations

import json
from typing import Any, Literal

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool, ToolException

from artifact_service import save_document_artifact, save_image_artifact, tool_result
from model import _content_text, _lc_messages, _openai_image_size
from model_registry import models


AGENT_SYSTEM_PROMPT = """You are SceneFlow Assistant. Answer clearly and concisely.
You can generate images, PDF files, and Word documents with tools.
- When the user asks for a file or image and has supplied enough information, call the matching tool instead of only describing how to make it.
- For PDF and Word tools, write the complete document content yourself. Use simple Markdown headings and lists; do not include the title again in the content.
- After a successful tool call, include the exact Markdown link or image Markdown returned by the tool.
- Never claim a file was generated unless the tool returned a successful result.
- Do not expose internal paths, API keys, tool arguments, or implementation details.
"""

TOOL_LABELS = {
    "generate_image": "生成图片",
    "generate_pdf": "生成 PDF",
    "generate_word_document": "生成 Word 文档",
}


def _tool_detail(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("title") or value.get("prompt") or "")[:120]
    content = getattr(value, "content", value)
    return str(content or "")[:160]


def create_chat_tools(session_id: str, image_config: dict[str, Any] | None) -> list[StructuredTool]:
    async def generate_image(prompt: str, title: str = "生成图片", aspect_ratio: Literal["1:1", "3:2", "2:3", "16:9", "9:16"] = "1:1") -> str:
        """Generate an image and return a signed image URL plus Markdown. Use when the user asks to create, draw, render, or illustrate an image."""
        prompt = prompt.strip()
        if not prompt:
            raise ToolException("image prompt is required")
        if len(prompt) > 4_000:
            raise ToolException("image prompt is too long")
        if not image_config:
            raise ToolException("image generation is not configured; ask the user to enable an image model in Settings")
        try:
            provider = image_config["provider"]
            size = aspect_ratio if provider == "gemini" else _openai_image_size(aspect_ratio)
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
            return tool_result(save_image_artifact(session_id, title.strip()[:160], result.data, result.format))
        except Exception as exc:
            raise ToolException(str(exc)) from exc

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

    tools = [
        StructuredTool.from_function(coroutine=generate_image, name="generate_image", description=generate_image.__doc__),
        StructuredTool.from_function(coroutine=generate_pdf, name="generate_pdf", description=generate_pdf.__doc__),
        StructuredTool.from_function(coroutine=generate_word_document, name="generate_word_document", description=generate_word_document.__doc__),
    ]
    for item in tools:
        item.handle_tool_error = True
    return tools


def _agent(config: dict[str, Any], session_id: str, image_config: dict[str, Any] | None):
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
        tools=create_chat_tools(session_id, image_config),
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


def _artifact_markdowns(output: Any) -> list[str]:
    messages = output.get("messages", []) if isinstance(output, dict) else []
    markdowns: list[str] = []
    for message in messages:
        if getattr(message, "type", "") != "tool":
            continue
        try:
            payload = json.loads(str(message.content))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        markdown = str(payload.get("markdown") or "").strip() if isinstance(payload, dict) else ""
        if markdown and markdown not in markdowns:
            markdowns.append(markdown)
    return markdowns


def _answer_with_artifacts(output: Any) -> str:
    answer = _final_answer(output)
    missing = [markdown for markdown in _artifact_markdowns(output) if markdown not in answer]
    if missing:
        answer = (answer + "\n\n" if answer else "") + "\n\n".join(missing)
    return answer


async def run_chat_agent(
    config: dict[str, Any],
    session_id: str,
    messages: list[dict[str, Any]],
    image_config: dict[str, Any] | None,
) -> str:
    agent = _agent(config, session_id, image_config)
    output = await agent.ainvoke(
        {"messages": _lc_messages(messages, config["provider"])},
        config={"recursion_limit": 12},
    )
    answer = _answer_with_artifacts(output)
    if not answer:
        raise ValueError("empty content from agent")
    return answer


async def stream_chat_agent(
    config: dict[str, Any],
    session_id: str,
    messages: list[dict[str, Any]],
    image_config: dict[str, Any] | None,
):
    agent = _agent(config, session_id, image_config)
    final_output: Any = None
    streamed_content = ""
    async for event in agent.astream_events(
        {"messages": _lc_messages(messages, config["provider"])},
        config={"recursion_limit": 12},
        version="v2",
    ):
        event_type = event["event"]
        if event_type == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            reasoning = str(chunk.additional_kwargs.get("reasoning_content") or chunk.additional_kwargs.get("reasoning") or "")
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
            yield {
                "type": "agent_step",
                "step": {
                    "id": "tool_" + event["run_id"],
                    "label": TOOL_LABELS.get(event["name"], event["name"]),
                    "status": "done",
                    "detail": _tool_detail(event["data"].get("output")),
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
    answer = _answer_with_artifacts(final_output)
    missing = [markdown for markdown in _artifact_markdowns(final_output) if markdown not in streamed_content]
    if missing:
        yield {"type": "content_delta", "content": ("\n\n" if streamed_content else "") + "\n\n".join(missing)}
    yield {"type": "agent_complete", "content": answer}
