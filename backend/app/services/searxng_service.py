from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from langchain_core.tools import ToolException

from app.core import config

logger = logging.getLogger(__name__)

SEARCH_TIMEOUT_SECONDS = 10.0
DEFAULT_SEARCH_RESULT_COUNT = max(1, min(10, getattr(config, "SEARXNG_RESULT_COUNT", 4)))
DEFAULT_MAX_SNIPPET_CHARS = max(50, min(1000, getattr(config, "SEARXNG_MAX_SNIPPET_CHARS", 180)))
DEFAULT_MAX_TOTAL_CHARS = max(200, min(5000, getattr(config, "SEARXNG_MAX_TOTAL_CHARS", 900)))
DEFAULT_SEARCH_ENGINES = "vuhuv,naver,abcnyheter,encyclosearch,sogou wechat,yandex,bing"
# Tool text returned (not raised) when a turn exhausts its search budget; the model must
# answer from what it already has instead of looping on new queries.
SEARCH_LIMIT_NOTICE_MARKER = "本轮网络搜索次数已达上限"


def search_limit_notice(limit: int) -> str:
    return f"{SEARCH_LIMIT_NOTICE_MARKER}（{limit} 次），请直接基于已获取的搜索结果作答；如仍无法回答，请如实告知用户。"


def is_searxng_configured() -> bool:
    """Check if the SearXNG search service base URL is configured."""
    return bool(config.SEARXNG_BASE_URL)


def sanitize_query(query: str) -> str:
    """Sanitize raw search query by stripping noise punctuation, question marks, and collapsing spaces."""
    cleaned = re.sub(r"[?？!！\"'“”‘’\*\^~]", " ", query)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or query.strip()


def normalize_engine_names(raw_engines: str) -> str:
    """Normalize engine names and aliases (e.g., 'wechat', 'weixin' -> 'sogou wechat')."""
    if not raw_engines:
        return ""
    parts = [p.strip() for p in raw_engines.split(",") if p.strip()]
    normalized: list[str] = []
    for p in parts:
        lower = p.lower()
        if lower in {"wechat", "weixin", "wx"}:
            normalized.append("sogou wechat")
        else:
            normalized.append(p)
    return ",".join(normalized)


def format_search_results(
    query: str,
    items: list[dict[str, Any]],
    max_snippet_chars: int = DEFAULT_MAX_SNIPPET_CHARS,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> str:
    """Format SearXNG search result items into concise Markdown text suitable for fast LLM digestion."""
    valid_items: list[dict[str, str]] = []
    noise_patterns = [
        "Please enable JavaScript",
        "请开启JavaScript",
        "Access Denied",
        "Attention Required! | Cloudflare",
        "Just a moment...",
        "Robot Check",
    ]
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        raw_content = str(item.get("content") or "").strip()

        # 清洗连续空白与特殊干扰字符
        content = re.sub(r"\s+", " ", raw_content).strip()
        if any(noise.lower() in content.lower() for noise in noise_patterns):
            continue
        if not title and not url and not content:
            continue

        # 裁剪单条 content 长度，避免单个网页过长占用过多 token
        if len(content) > max_snippet_chars:
            content = content[:max_snippet_chars].rstrip() + "..."

        # 标题同样做适当修剪，防止极端网页标题极长
        if len(title) > 80:
            title = title[:80].rstrip() + "..."

        valid_items.append({
            "title": title or "网页链接",
            "url": url,
            "content": content,
        })

    if not valid_items:
        return f"未检索到与「{query}」相关的网络搜索结果。"

    # 头部长度按最大条数估算，先裁剪条目再写头部，保证“共精选 N 条”与实际列出的条数一致
    header_budget = len(f"### 网页搜索结果（关键词：{query}，共精选 {len(valid_items)} 条）\n")
    entries: list[str] = []
    current_chars = header_budget

    for idx, item in enumerate(valid_items, start=1):
        title = item["title"]
        url = item["url"]
        content = item["content"]
        entry_lines = []
        if url:
            entry_lines.append(f"{idx}. [{title}]({url})")
        else:
            entry_lines.append(f"{idx}. **{title}**")
        if content:
            entry_lines.append(f"   {content}\n")
        else:
            entry_lines.append("")
        entry_text = "\n".join(entry_lines)

        # 严格控制总字符预算，保障大模型秒级首字响应与推理稳定性
        if current_chars + len(entry_text) > max_total_chars and idx > 2:
            break
        entries.append(entry_text)
        current_chars += len(entry_text)

    header = f"### 网页搜索结果（关键词：{query}，共精选 {len(entries)} 条）\n"
    return "\n".join([header, *entries]).strip()


def extract_search_step_summary(content: str) -> str:
    """Extract clean, short summary text for UI step display from web_search tool output."""
    if not isinstance(content, str):
        return ""
    if SEARCH_LIMIT_NOTICE_MARKER in content:
        return "已达本轮搜索上限"
    if "未检索到与" in content:
        return "未检索到匹配网页"
    match = re.search(r"共(?:找到|精选)\s*(\d+)\s*条", content)
    if match:
        label = "精选" if "共精选" in content else "相关"
        return f"检索到 {match.group(1)} 条{label}网页"
    if "网页搜索结果" in content:
        return "检索完成"
    return ""


async def _execute_searxng_request(
    client: httpx.AsyncClient,
    request_url: str,
    query: str,
    engines: str,
    token: str,
) -> dict[str, Any]:
    params: dict[str, str] = {
        "q": query,
        "format": "json",
        "categories": "general",
        "language": "zh",
    }
    if engines:
        params["engines"] = engines
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if token:
        # SearXNG reads private-engine tokens from the `tokens` request parameter
        # (`Preferences.parse_dict`); the bearer header only serves a reverse proxy in front of it.
        params["tokens"] = token
        headers["Authorization"] = f"Bearer {token}"

    response = await client.get(request_url, params=params, headers=headers)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


async def search_searxng(query: str, count: int = DEFAULT_SEARCH_RESULT_COUNT) -> str:
    """Execute a web search query against the configured SearXNG instance."""
    raw_query = query.strip()
    if not raw_query:
        raise ToolException("搜索关键词不能为空")

    clean_query = sanitize_query(raw_query)

    base_url = config.SEARXNG_BASE_URL
    if not base_url:
        raise ToolException("网络搜索服务尚未配置，请在后台环境中设置 SCENEFLOW_SEARXNG_BASE_URL")

    # 优先使用配置的引擎，若未配置则使用已在实例上验证可用的高可用引擎
    raw_engines = config.SEARXNG_ENGINES.strip()
    configured_engines = normalize_engine_names(raw_engines)
    engines_to_use = configured_engines or DEFAULT_SEARCH_ENGINES
    token = config.SEARXNG_ENGINE_TOKEN
    request_url = f"{base_url}/search"

    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
            data = await _execute_searxng_request(client, request_url, clean_query, engines_to_use, token)
            results = data.get("results")
            # 如果配置了特定引擎但返回为空，且有不可用引擎，尝试降级到高可用引擎
            if (not results or not isinstance(results, list)) and configured_engines and configured_engines != DEFAULT_SEARCH_ENGINES:
                unresponsive = data.get("unresponsive_engines")
                if unresponsive:
                    logger.info("Engines %s unresponsive, falling back to %s", configured_engines, DEFAULT_SEARCH_ENGINES)
                    fallback_data = await _execute_searxng_request(client, request_url, clean_query, DEFAULT_SEARCH_ENGINES, token)
                    if fallback_data.get("results"):
                        data = fallback_data
                        results = data.get("results")
    # Queries are user conversation content: log outcomes and sizes only, never the text.
    except httpx.TimeoutException as exc:
        logger.warning("SearXNG search timed out (query length %d)", len(clean_query))
        raise ToolException("网络搜索请求超时，请稍后重试") from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("SearXNG search returned HTTP %s", exc.response.status_code)
        raise ToolException(f"网络搜索服务响应异常 (HTTP {exc.response.status_code})") from exc
    except httpx.RequestError as exc:
        logger.warning("SearXNG search network error: %s", type(exc).__name__)
        raise ToolException(f"无法连接到网络搜索服务：{exc}") from exc
    except Exception as exc:
        logger.exception("Unexpected error during SearXNG search")
        raise ToolException(f"网络搜索解析失败：{exc}") from exc

    if not isinstance(results, list) or not results:
        return f"未检索到与「{clean_query}」相关的网络搜索结果。"

    trimmed = results[:max(1, count)]
    return format_search_results(clean_query, trimmed)


class SceneFlowSearxSearchWrapper:
    """Async-first SearXNG search wrapper aligned with LangChain's SearxSearchWrapper interface,

    enhanced with token authentication, resilient engine fallback, alias normalization, and token budget protection.
    """

    def __init__(
        self,
        searx_host: str = "",
        engines: str = "",
        token: str = "",
        k: int = DEFAULT_SEARCH_RESULT_COUNT,
    ):
        self.searx_host = (searx_host or config.SEARXNG_BASE_URL).rstrip("/")
        self.engines = engines or config.SEARXNG_ENGINES
        self.token = token or config.SEARXNG_ENGINE_TOKEN
        self.k = k

    async def aresults(
        self,
        query: str,
        num_results: int | None = None,
        engines: str | None = None,
    ) -> list[dict[str, str]]:
        """Return list of structured search result dictionaries [{title, link, snippet}]."""
        clean_query = sanitize_query(query)
        if not clean_query:
            return []

        base_url = self.searx_host
        if not base_url:
            raise ToolException("网络搜索服务尚未配置，请在后台环境中设置 SCENEFLOW_SEARXNG_BASE_URL")

        raw_engines = (engines if engines is not None else self.engines).strip()
        configured_engines = normalize_engine_names(raw_engines)
        engines_to_use = configured_engines or DEFAULT_SEARCH_ENGINES
        request_url = f"{base_url}/search"
        count = num_results or self.k

        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
            data = await _execute_searxng_request(client, request_url, clean_query, engines_to_use, self.token)
            results = data.get("results")
            if (not results or not isinstance(results, list)) and configured_engines and configured_engines != DEFAULT_SEARCH_ENGINES:
                unresponsive = data.get("unresponsive_engines")
                if unresponsive:
                    fallback_data = await _execute_searxng_request(client, request_url, clean_query, DEFAULT_SEARCH_ENGINES, self.token)
                    if fallback_data.get("results"):
                        results = fallback_data.get("results")

        if not isinstance(results, list) or not results:
            return []

        items: list[dict[str, str]] = []
        for r in results[:count]:
            if isinstance(r, dict):
                items.append({
                    "title": str(r.get("title") or "网页链接").strip(),
                    "link": str(r.get("url") or "").strip(),
                    "snippet": str(r.get("content") or "").strip(),
                })
        return items

    async def arun(self, query: str, num_results: int | None = None) -> str:
        """Execute search and return LLM-optimized Markdown summary."""
        count = num_results or self.k
        return await search_searxng(query, count=count)


async def search_candidate_urls(query: str, count: int = 3) -> list[str]:
    """Retrieve top candidate URLs from SearXNG for downstream deep extraction via Crawl4AI."""
    wrapper = SceneFlowSearxSearchWrapper(k=count)
    results = await wrapper.aresults(query, num_results=count)
    return [item["link"] for item in results if item.get("link")]

