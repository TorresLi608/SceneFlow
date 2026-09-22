from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import ipaddress
import logging
import re
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
from langchain_core.tools import ToolException

from app.core import config

logger = logging.getLogger(__name__)

CRAWL_TIMEOUT_SECONDS = 15.0
# Upper bound for one fetch_web_content call across every extraction stage, so a slow
# Crawl4AI service plus the built-in fallback cannot keep the chat turn hanging.
CRAWL_TOTAL_TIMEOUT_SECONDS = 30.0
DNS_TIMEOUT_SECONDS = 5.0
MAX_REDIRECTS = 5
# The built-in fetcher reads at most this many bytes; anything larger is truncated before parsing.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_CRAWL_MAX_CHARS = config.CRAWL4AI_MAX_CHARS

_BLOCKED_HOSTNAMES = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "local"}
_BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".home.arpa")
_TEXTUAL_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml")
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for loopback, private, link-local, multicast, reserved, or otherwise non-global addresses."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return _is_blocked_ip(ip.ipv4_mapped)
        if ip.sixtofour is not None:
            return _is_blocked_ip(ip.sixtofour)
    return (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _literal_ip(hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        return None


def _url_hostname(url: str) -> str:
    return (urlparse(url.strip()).hostname or "").strip().lower().rstrip(".")


def is_safe_public_url(url: str) -> bool:
    """String-level SSRF check: HTTP(S) only, no credentials, no local names, no non-public literal IPs.

    This does not resolve DNS; `assert_public_url` adds that check before any request is made.
    """
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.username or parsed.password:
        return False
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname or hostname in _BLOCKED_HOSTNAMES or hostname.endswith(_BLOCKED_HOST_SUFFIXES):
        return False
    literal = _literal_ip(hostname)
    if literal is not None and _is_blocked_ip(literal):
        return False
    # Numeric hostnames that are not valid IP literals ("0177.0.0.1", "2130706433", "0x7f.1")
    # are parsed as IPv4 by some resolvers (glibc octal/decimal forms) and are never real DNS names.
    if literal is None and re.fullmatch(r"(?:\d+|0x[0-9a-f]+)", hostname.rsplit(".", 1)[-1]):
        return False
    return True


async def _resolve_host(hostname: str, port: int) -> list[str]:
    """Resolve a hostname to every address the system resolver returns (patched in tests)."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


async def assert_public_url(url: str) -> None:
    """Raise ToolException unless `url` is an HTTP(S) URL whose host resolves only to public addresses.

    Hostnames such as `127.0.0.1.nip.io` or octal literals like `0177.0.0.1` pass the string check but
    resolve to loopback, so every address returned by DNS is validated before a request is sent.
    The remaining gap is DNS rebinding between this check and the connection itself.
    """
    if not is_safe_public_url(url):
        raise ToolException(f"无法访问非公网或不合法的网页地址：「{url}」")
    parsed = urlparse(url.strip())
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if _literal_ip(hostname) is not None:
        return
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = await asyncio.wait_for(_resolve_host(hostname, port), timeout=DNS_TIMEOUT_SECONDS)
    except (TimeoutError, socket.gaierror, OSError) as exc:
        raise ToolException(f"无法解析网页域名：「{hostname}」") from exc
    if not addresses:
        raise ToolException(f"无法解析网页域名：「{hostname}」")
    for address in addresses:
        ip = _literal_ip(address)
        if ip is None or _is_blocked_ip(ip):
            raise ToolException(f"无法访问非公网或不合法的网页地址：「{url}」")


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
        logger.warning("HTMLParser encounter error: %s, falling back to regex clean", type(exc).__name__)

    title = parser.title or "网页正文"
    full_markdown = parser.get_markdown()

    if not full_markdown:
        clean_re = re.sub(r"<[^>]+>", " ", html_content)
        full_markdown = re.sub(r"\s+", " ", clean_re).strip()

    total_chars = len(full_markdown)
    if total_chars > max_chars:
        full_markdown = full_markdown[:max_chars].rstrip() + "..."

    return title, full_markdown, total_chars


def _decode_body(data: bytes, declared_charset: str | None) -> str:
    """Decode a response body using the header charset, then a <meta charset>, then UTF-8."""
    candidates: list[str] = []
    if declared_charset:
        candidates.append(declared_charset)
    match = re.search(rb"<meta[^>]+charset=[\"']?\s*([a-zA-Z0-9_\-]+)", data[:4096], re.IGNORECASE)
    if match:
        candidates.append(match.group(1).decode("ascii", "ignore"))
    candidates.append("utf-8")
    for name in candidates:
        codec = name.strip().lower()
        if codec in {"gb2312", "gbk"}:
            codec = "gb18030"
        try:
            return data.decode(codec)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _markdown_from_crawl4ai(target: dict[str, Any]) -> str:
    """Crawl4AI >= 0.5 serializes `markdown` as an object; older builds and `/md` return a string.

    A top-level `fit_markdown` (older builds) wins, then the object's fit/raw text, then `content`.
    """
    markdown = target.get("markdown")
    candidates: list[Any] = [target.get("fit_markdown")]
    if isinstance(markdown, dict):
        candidates.extend([markdown.get("fit_markdown"), markdown.get("raw_markdown")])
    else:
        candidates.append(markdown)
    candidates.append(target.get("content"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip() and not candidate.startswith("<property object"):
            return candidate.strip()
    return ""


def _title_from_crawl4ai(target: dict[str, Any], default: str) -> str:
    metadata = target.get("metadata")
    title = target.get("title") or (metadata.get("title") if isinstance(metadata, dict) else "")
    return str(title or default)


async def _crawl_via_crawl4ai_api(url: str, base_url: str, api_token: str) -> dict[str, Any] | None:
    """Send crawl request to configured Crawl4AI REST API."""
    request_url = f"{base_url.rstrip('/')}/crawl"
    headers = {
        "User-Agent": "SceneFlow-Assistant/1.0",
        "Accept": "application/json",
    }
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    payload = {"urls": [url]}

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
        logger.warning("Crawl4AI API request failed: %s", type(exc).__name__)
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
        logger.debug("Local crawl4ai SDK execution not available: %s", type(exc).__name__)
    return None


async def _crawl_via_builtin_fallback(url: str, max_chars: int) -> tuple[str, str, int]:
    """Built-in fetcher: manual redirect hops with a public-address check per hop, capped body size."""
    current = url
    async with httpx.AsyncClient(timeout=CRAWL_TIMEOUT_SECONDS, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await assert_public_url(current)
            async with client.stream("GET", current, headers=_BROWSER_HEADERS) as response:
                location = response.headers.get("location")
                if response.is_redirect and location:
                    current = str(response.url.join(location))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if content_type and not content_type.startswith(_TEXTUAL_CONTENT_TYPES):
                    raise ToolException("该链接不是网页文本内容，无法提取正文")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) >= MAX_RESPONSE_BYTES:
                        logger.info("Web page body exceeded %d bytes; truncated before parsing", MAX_RESPONSE_BYTES)
                        break
                html = _decode_body(bytes(body[:MAX_RESPONSE_BYTES]), response.charset_encoding)
                return html_to_clean_markdown(html, max_chars=max_chars)
    raise ToolException("网页重定向次数过多，已停止读取")


def extract_crawl_step_summary(content: str) -> str:
    """Short execution-panel text for a finished fetch_web_content call."""
    if not isinstance(content, str):
        return ""
    if "未能从网页" in content:
        return "未提取到有效文本"
    match = re.search(r"精简提取前\s*(\d+)\s*字符，原文约\s*(\d+)\s*字符", content)
    if match:
        return f"已提取前 {match.group(1)} 字符，原文约 {match.group(2)} 字符"
    match = re.search(r"全文提取完成，共\s*(\d+)\s*字符", content)
    if match:
        return f"已提取 {match.group(1)} 字符正文"
    if "网页深度提取" in content:
        return "提取完成"
    return ""


async def _extract(clean_url: str, max_chars: int) -> str:
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
                markdown_content = _markdown_from_crawl4ai(target_res)
                title = _title_from_crawl4ai(target_res, title)
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
        except ToolException:
            raise
        except httpx.TimeoutException as exc:
            logger.warning("Crawl fallback request timed out")
            raise ToolException(f"访问网页超时，无法读取正文：「{clean_url}」") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("Crawl fallback returned HTTP %s", exc.response.status_code)
            raise ToolException(f"网页返回异常状态 (HTTP {exc.response.status_code})：「{clean_url}」") from exc
        except Exception as exc:
            logger.warning("Crawl fallback failed: %s", type(exc).__name__)
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


async def crawl_web_page(url: str, max_chars: int = DEFAULT_CRAWL_MAX_CHARS) -> str:
    """Extract clean Markdown article content from a web page using Crawl4AI or resilient fallback."""
    clean_url = url.strip().strip("<>\"' ")
    if not clean_url:
        raise ToolException("网页 URL 不能为空")
    await assert_public_url(clean_url)

    try:
        async with asyncio.timeout(CRAWL_TOTAL_TIMEOUT_SECONDS):
            return await _extract(clean_url, max_chars)
    except TimeoutError as exc:
        logger.warning("Web page extraction exceeded the %.0fs total budget", CRAWL_TOTAL_TIMEOUT_SECONDS)
        raise ToolException(f"访问网页超时，无法读取正文：「{clean_url}」") from exc
