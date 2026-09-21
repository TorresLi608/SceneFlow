from __future__ import annotations

from html.parser import HTMLParser
import ipaddress
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from langchain_core.tools import ToolException

from app.core import config

logger = logging.getLogger(__name__)

CRAWL_TIMEOUT_SECONDS = 15.0
DEFAULT_CRAWL_MAX_CHARS = config.CRAWL4AI_MAX_CHARS


def is_safe_public_url(url: str) -> bool:
    """Verify that a URL is a valid public HTTP(S) link and not an internal network probe (SSRF defense)."""
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"}:
            return False
        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            return False
        if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1", "local"}:
            return False
        if hostname.endswith(".local") or hostname.endswith(".internal"):
            return False
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return False
        except ValueError:
            # Hostname is a domain name, not a raw IP address
            pass
        return True
    except Exception:
        return False


class _SemanticMarkdownParser(HTMLParser):
    """Zero-dependency HTML to clean Markdown extractor using Python standard library."""

    def __init__(self) -> None:
        super().__init__()
        self.ignored_tags = {
            "script", "style", "nav", "header", "footer", "noscript",
            "iframe", "svg", "form", "button", "aside", "select", "input",
        }
        self.ignore_depth = 0
        self.lines: list[str] = []
        self.current_line: list[str] = []
        self.title = ""
        self._in_title = False
        self._heading_level = 0
        self._in_code = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in self.ignored_tags:
            self.ignore_depth += 1
            return
        if self.ignore_depth > 0:
            return

        if t == "title":
            self._in_title = True
        elif t in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
            self._heading_level = int(t[1])
        elif t in {"p", "blockquote", "tr"}:
            self._flush()
            if t == "blockquote":
                self.current_line.append("> ")
        elif t == "li":
            self._flush()
            self.current_line.append("- ")
        elif t == "pre":
            self._flush()
            self._in_code = True
            self.lines.append("```")
        elif t == "br":
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in self.ignored_tags:
            if self.ignore_depth > 0:
                self.ignore_depth -= 1
            return
        if self.ignore_depth > 0:
            return

        if t == "title":
            self._in_title = False
        elif t in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            if self._heading_level:
                content = "".join(self.current_line).strip()
                if content:
                    self.lines.append(f"{'#' * self._heading_level} {content}")
                self.current_line = []
                self._heading_level = 0
        elif t == "pre":
            self._flush()
            self.lines.append("```")
            self._in_code = False
        elif t in {"p", "blockquote", "li", "tr"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self.ignore_depth > 0:
            return
        if self._in_title and not self.title:
            self.title = data.strip()
            return
        if self._in_code:
            self.current_line.append(data)
            return

        text = data.replace("\r", " ").replace("\n", " ")
        if text.strip():
            self.current_line.append(text)

    def _flush(self) -> None:
        if self.current_line:
            s = "".join(self.current_line).strip()
            if s:
                self.lines.append(s)
            self.current_line = []

    def get_markdown(self) -> str:
        self._flush()
        text = "\n\n".join(self.lines)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_clean_markdown(html_content: str, max_chars: int = DEFAULT_CRAWL_MAX_CHARS) -> tuple[str, str, int]:
    """Extract clean, structured Markdown from HTML without external dependencies."""
    parser = _SemanticMarkdownParser()
    try:
        parser.feed(html_content)
    except Exception as exc:
        logger.warning("HTMLParser encounter error: %s, falling back to regex clean", exc)

    title = parser.title or "网页正文"
    full_markdown = parser.get_markdown()

    if not full_markdown:
        clean_re = re.sub(r"<[^>]+>", " ", html_content)
        full_markdown = re.sub(r"\s+", " ", clean_re).strip()

    total_chars = len(full_markdown)
    if total_chars > max_chars:
        full_markdown = full_markdown[:max_chars].rstrip() + "..."

    return title, full_markdown, total_chars


async def _crawl_via_crawl4ai_api(url: str, base_url: str, api_token: str) -> dict[str, Any] | None:
    """Send crawl request to configured Crawl4AI REST API."""
    request_url = f"{base_url.rstrip('/')}/crawl"
    headers = {
        "User-Agent": "SceneFlow-Assistant/1.0",
        "Accept": "application/json",
    }
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    payload = {
        "urls": [url],
        "priority": 10,
    }

    try:
        async with httpx.AsyncClient(timeout=CRAWL_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.post(request_url, json=payload, headers=headers)
            if response.status_code == 404:
                alt_url = f"{base_url.rstrip('/')}/md"
                alt_res = await client.post(alt_url, json={"url": url}, headers=headers)
                if alt_res.status_code == 200:
                    data = alt_res.json()
                    return data if isinstance(data, dict) else {}
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Crawl4AI API request to %s failed: %s", request_url, exc)
        return None


async def _crawl_via_local_crawl4ai(url: str) -> str | None:
    """Attempt extraction using local crawl4ai Python library if available."""
    try:
        import importlib
        crawl4ai_mod = importlib.import_module("crawl4ai")
        crawler_cls = getattr(crawl4ai_mod, "AsyncWebCrawler", None)
        if crawler_cls is not None:
            async with crawler_cls() as crawler:
                result = await crawler.arun(url=url)
                fit_md = getattr(result, "fit_markdown", None)
                raw_md = getattr(result, "markdown", None)
                return str(fit_md or raw_md or "")
    except Exception as exc:
        logger.debug("Local crawl4ai SDK execution not available: %s", exc)
    return None


async def _crawl_via_builtin_fallback(url: str, max_chars: int) -> tuple[str, str, int]:
    """Built-in lightweight fallback extractor using httpx and Python standard library HTML parser."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(timeout=CRAWL_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        html = response.text
        return html_to_clean_markdown(html, max_chars=max_chars)


async def crawl_web_page(url: str, max_chars: int = DEFAULT_CRAWL_MAX_CHARS) -> str:
    """Extract clean Markdown article content from a web page using Crawl4AI or resilient fallback."""
    clean_url = url.strip().strip("<>\"' ")
    if not clean_url:
        raise ToolException("网页 URL 不能为空")
    if not is_safe_public_url(clean_url):
        raise ToolException(f"无法访问非公网或不合法的网页地址：「{clean_url}」")

    base_url = config.CRAWL4AI_BASE_URL
    api_token = config.CRAWL4AI_API_TOKEN

    title = "网页正文"
    markdown_content = ""
    total_chars = 0
    engine_label = ""

    # 1. 优先尝试外部 Crawl4AI REST 服务
    if base_url:
        data = await _crawl_via_crawl4ai_api(clean_url, base_url, api_token)
        if data:
            results = data.get("results")
            target_res = results[0] if isinstance(results, list) and results else data
            if isinstance(target_res, dict):
                fit_md = target_res.get("fit_markdown") or ""
                raw_md = target_res.get("markdown") or target_res.get("content") or ""
                markdown_content = str(fit_md or raw_md).strip()
                title = str(target_res.get("title") or target_res.get("metadata", {}).get("title") or title)
                if markdown_content:
                    engine_label = "Crawl4AI 智能正文引擎"

    # 2. 尝试本地 crawl4ai Python SDK
    if not markdown_content:
        local_md = await _crawl_via_local_crawl4ai(clean_url)
        if local_md:
            markdown_content = local_md.strip()
            engine_label = "Crawl4AI 本地提取器"

    # 3. 兜底使用内置轻量提取器 (httpx + HTMLParser)
    if not markdown_content:
        try:
            fb_title, fb_md, fb_total = await _crawl_via_builtin_fallback(clean_url, max_chars)
            title = fb_title
            markdown_content = fb_md
            total_chars = fb_total
            engine_label = "内置语义清洗引擎"
        except httpx.TimeoutException as exc:
            logger.warning("Crawl fallback request timed out for %s", clean_url)
            raise ToolException(f"访问网页超时，无法读取正文：「{clean_url}」") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("Crawl fallback returned HTTP %s for %s", exc.response.status_code, clean_url)
            raise ToolException(f"网页返回异常状态 (HTTP {exc.response.status_code})：「{clean_url}」") from exc
        except Exception as exc:
            logger.warning("Crawl fallback failed for %s: %s", clean_url, exc)
            raise ToolException(f"无法读取该网页内容：{exc}") from exc

    if not markdown_content:
        return f"未能从网页「{clean_url}」中提取到有效文本内容。"

    if not total_chars:
        total_chars = len(markdown_content)

    if len(markdown_content) > max_chars:
        markdown_content = markdown_content[:max_chars].rstrip() + "..."
        truncation_note = f"（已按上下文安全预算精简提取前 {max_chars} 字符，原文约 {total_chars} 字符）"
    else:
        truncation_note = f"（全文提取完成，共 {total_chars} 字符）"

    output_lines = [
        f"### 网页深度提取：{title}",
        f"- **来源网址**：[{title}]({clean_url})",
        f"- **提取引擎**：{engine_label} {truncation_note}",
        "",
        "---",
        "",
        markdown_content,
    ]

    return "\n".join(output_lines)
