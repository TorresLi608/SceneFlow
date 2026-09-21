from __future__ import annotations

from datetime import datetime
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
from app.services.crawl_service import crawl_web_page
from app.services.error_log_service import error_log_json, find_error_logs
from app.services.searxng_service import extract_search_step_summary, is_searxng_configured, search_searxng
from app.services.usage_service import aggregate_token_usage, record_usage, require_model_balance


def _current_time_context() -> str:
    """Return the current date and day-of-week for temporal anchoring in reasoning."""
    now = datetime.now()
    weekday_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return f"{now.strftime('%Y年%m月%d日')} {weekday_map[now.weekday()]}"


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
    "fetch_web_content": "提取网页正文",
    "generate_image": "生成图片",
    "generate_pdf": "生成 PDF",
    "generate_word_document": "生成 Word 文档",
    "search_error_logs": "查询错误日志",
    "web_search": "网络搜索",
}
TOOL_FAILURE_LABELS = {
    "fetch_web_content": "网页正文提取失败",
    "generate_image": "图片生成失败",
    "generate_pdf": "PDF 生成失败",
    "generate_word_document": "Word 文档生成失败",
    "search_error_logs": "错误日志查询失败",
    "web_search": "网络搜索失败",
}
MAX_FAILURE_REASON_CHARS = 200


@dataclass
class AgentResult:
    content: str
    usage: dict[str, int]


def _tool_detail(value: Any) -> str:
    if isinstance(value, dict):
        query = value.get("query")
        if query:
            return f"检索「{str(query)[:80]}」"
        url = value.get("url")
        if url:
            return f"提取「{str(url)[:80]}」"
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

    searched_cache: dict[str, str] = {}

    async def web_search(query: str) -> str:
        """Search the web for real-time information, facts, weather, news, or documentation.
        Parameter `query`: Clean, concise search keywords separated by spaces (e.g. '成都 实时天气', 'Python 3.12 新特性').
        Do NOT include punctuation, conversational sentences, or question marks ('?', '？')."""
        normalized_query = query.strip()
        if not normalized_query:
            raise ToolException("搜索关键词不能为空")
        if normalized_query in searched_cache:
            return searched_cache[normalized_query]
        # 单轮已完成过有效检索时直接复用已有结果，防止模型反复循环或并发调用网络搜索
        if searched_cache:
            first_cached = next(iter(searched_cache.values()))
            return first_cached
        result = await search_searxng(normalized_query)
        searched_cache[normalized_query] = result
        return result

    async def fetch_web_content(url: str) -> str:
        """Extract clean, structured Markdown article content from a specific web URL using Crawl4AI.
        Use when the user provides a specific web page URL to read/summarize, or when you need detailed text from a search result link."""
        return await crawl_web_page(url)

    tools = [
        StructuredTool.from_function(coroutine=generate_image, name="generate_image", description=generate_image.__doc__),
        StructuredTool.from_function(coroutine=generate_pdf, name="generate_pdf", description=generate_pdf.__doc__),
        StructuredTool.from_function(coroutine=generate_word_document, name="generate_word_document", description=generate_word_document.__doc__),
        StructuredTool.from_function(coroutine=fetch_web_content, name="fetch_web_content", description=fetch_web_content.__doc__),
    ]
    if is_searxng_configured():
        tools.append(StructuredTool.from_function(coroutine=web_search, name="web_search", description=web_search.__doc__))
    if can_read_error_logs:
        tools.append(StructuredTool.from_function(func=search_error_logs, name="search_error_logs", description=search_error_logs.__doc__))
    for item in tools:
        item.handle_tool_error = True
    return tools


def _agent_system_prompt() -> str:
    prompt = AGENT_SYSTEM_PROMPT
    current_date = _current_time_context()
    prompt += f"\n- 当前现实世界日期：{current_date}。"
    prompt += (
        "\n- 你拥有通过 web_search 进行全网广度搜索，以及通过 fetch_web_content 深度提取具体网页正文（基于 Crawl4AI）的能力。"
        "\n  遵循以下【分析与搜索/正文提取协同】流程："
        "\n  1.【意图与时间分析】：先分析用户的核心需求。遇到'今天'、'最近'、'今年'等相对时间，必须结合上方当前现实世界日期准确定位，禁止凭空猜测年份或使用带问号的推测年份。"
        "\n  2.【搜索词优化重写 (Query Optimization)】：严禁将用户的口语长句或疑问句直接传给 web_search。必须提炼重构为适合搜索引擎的高纯度核心关键词（实体词+核心属性，空格分隔），去除所有口语修饰与疑问助词，绝对严禁包含问号（? 或 ？）或其它标点符号（例如：将'今天成都天气如何'重写提炼为'成都天气'或'成都 实时天气'）。"
        "\n  3.【深度正文提取 (Crawl4AI)】：当用户明确提供网页链接（URL）要求分析总结，或单凭搜索摘要不足以回答复杂长文/技术规范时，调用 fetch_web_content 读取该页面的纯净 Markdown 正文；"
        "\n  4.【严格防重与秒级响应】：单轮对话内严禁重复调用相同工具或循环抓取。一旦获取所需信息立即针对用户核心问题凝练、明确作答，避免冗长的背景铺垫，并在回复中以 Markdown 链接自然标注引用的网页来源。"
    )
    return prompt


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
        system_prompt=_agent_system_prompt(),
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
    content = getattr(output, "content", output)
    if isinstance(content, str):
        search_summary = extract_search_step_summary(content)
        if search_summary:
            return search_summary
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

    has_analyzed = False
    has_started_tools = False
    has_started_generation = False

    yield {
        "type": "agent_step",
        "step": {
            "id": "agent_analyze",
            "label": "意图分析",
            "status": "running",
            "detail": f"模型 {config['model']}",
        },
    }

    with get_usage_metadata_callback() as usage_callback:
        async for event in agent.astream_events(
            {"messages": _lc_messages(messages, config["provider"])},
            config={"recursion_limit": 12},
            version="v2",
        ):
            event_type = event["event"]
            if event_type == "on_chat_model_stream":
                if not has_analyzed:
                    has_analyzed = True
                    yield {
                        "type": "agent_step",
                        "step": {
                            "id": "agent_analyze",
                            "label": "意图分析",
                            "status": "done",
                            "detail": "分析完成",
                        },
                    }
                if has_started_tools and not has_started_generation:
                    has_started_generation = True
                    yield {
                        "type": "agent_step",
                        "step": {
                            "id": "agent_generate",
                            "label": "组织回答",
                            "status": "running",
                            "detail": "整合信息并输出",
                        },
                    }
                chunk = event["data"]["chunk"]
                reasoning = _reasoning_text(chunk.content, chunk.additional_kwargs)
                content = _content_text(chunk.content)
                if reasoning:
                    yield {"type": "reasoning_delta", "content": reasoning}
                if content:
                    streamed_content += content
                    yield {"type": "content_delta", "content": content}
            elif event_type == "on_tool_start":
                if not has_analyzed:
                    has_analyzed = True
                    yield {
                        "type": "agent_step",
                        "step": {
                            "id": "agent_analyze",
                            "label": "意图分析",
                            "status": "done",
                            "detail": "分析完成，调用工具",
                        },
                    }
                has_started_tools = True
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

    if not has_analyzed:
        yield {
            "type": "agent_step",
            "step": {
                "id": "agent_analyze",
                "label": "意图分析",
                "status": "done",
                "detail": "分析完成",
            },
        }
    if has_started_generation:
        yield {
            "type": "agent_step",
            "step": {
                "id": "agent_generate",
                "label": "组织回答",
                "status": "done",
                "detail": "回复生成完成",
            },
        }
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
