from __future__ import annotations

import asyncio
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, patch

import httpx
from langchain_core.tools import ToolException

from app.core import config
from app.services import crawl_service

_RealAsyncClient = httpx.AsyncClient
PUBLIC_IP = "93.184.216.34"


def _mock_async_client(transport: httpx.MockTransport):
    return lambda **kwargs: _RealAsyncClient(transport=transport, **{k: v for k, v in kwargs.items() if k != "transport"})


def _public_dns():
    """Every hostname resolves to a public address; tests never touch the real resolver."""
    return patch.object(crawl_service, "_resolve_host", AsyncMock(return_value=[PUBLIC_IP]))


@contextmanager
def _builtin_only(transport: httpx.MockTransport, *extra):
    """Route the built-in fetcher through `transport` with public DNS; no Crawl4AI, no local SDK."""
    with ExitStack() as stack:
        stack.enter_context(patch.object(config, "CRAWL4AI_BASE_URL", ""))
        stack.enter_context(patch.object(crawl_service, "_crawl_via_local_crawl4ai", AsyncMock(return_value=None)))
        stack.enter_context(patch("httpx.AsyncClient", _mock_async_client(transport)))
        stack.enter_context(_public_dns())
        for context in extra:
            stack.enter_context(context)
        yield


def _expect_tool_error(coro, fragment: str) -> None:
    try:
        asyncio.run(coro)
        assert False, f"expected ToolException containing {fragment!r}"
    except ToolException as exc:
        assert fragment in str(exc), str(exc)


def test_is_safe_public_url() -> None:
    # 合法公网地址
    assert crawl_service.is_safe_public_url("https://example.com/article/1")
    assert crawl_service.is_safe_public_url("http://x.ai/news/grok-4-6")
    assert crawl_service.is_safe_public_url("https://baike.baidu.com/item/Grok")

    # 非法地址 / SSRF 敏感探测拦截
    assert not crawl_service.is_safe_public_url("http://localhost:8080/admin")
    assert not crawl_service.is_safe_public_url("http://127.0.0.1:8080")
    assert not crawl_service.is_safe_public_url("http://192.168.1.1/router")
    assert not crawl_service.is_safe_public_url("http://10.0.0.1/internal")
    assert not crawl_service.is_safe_public_url("http://172.16.0.5")
    assert not crawl_service.is_safe_public_url("http://169.254.169.254/latest/meta-data/")
    assert not crawl_service.is_safe_public_url("http://[::ffff:127.0.0.1]/")
    assert not crawl_service.is_safe_public_url("http://[::1]/")
    assert not crawl_service.is_safe_public_url("http://0.0.0.0:8080/")
    assert not crawl_service.is_safe_public_url("http://0177.0.0.1/")
    assert not crawl_service.is_safe_public_url("http://2130706433/")
    assert not crawl_service.is_safe_public_url("http://0x7f.0.0.1/")
    assert not crawl_service.is_safe_public_url("http://app.localhost/")
    assert not crawl_service.is_safe_public_url("http://user:pass@example.com/")
    assert not crawl_service.is_safe_public_url("file:///etc/passwd")
    assert not crawl_service.is_safe_public_url("ftp://ftp.example.com")
    assert not crawl_service.is_safe_public_url("javascript:alert(1)")


def test_assert_public_url_rejects_hostnames_resolving_to_internal_addresses() -> None:
    # 127.0.0.1.nip.io、localtest.me 等域名字符串合法，但 DNS 指向回环/内网
    for resolved in (["127.0.0.1"], ["10.1.2.3"], ["2001:db8::1", "93.184.216.34"], ["::ffff:192.168.0.1"]):
        with patch.object(crawl_service, "_resolve_host", AsyncMock(return_value=resolved)):
            _expect_tool_error(crawl_service.assert_public_url("http://127.0.0.1.nip.io/secret"), "非公网或不合法")

    with patch.object(crawl_service, "_resolve_host", AsyncMock(side_effect=OSError("name or service not known"))):
        _expect_tool_error(crawl_service.assert_public_url("http://does-not-exist.example/"), "无法解析")

    with _public_dns():
        asyncio.run(crawl_service.assert_public_url("https://example.com/ok"))


def test_html_to_clean_markdown() -> None:
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>深度学习前沿进展</title>
        <script>console.log("ad script");</script>
        <style>.ad { display: none; }</style>
    </head>
    <body>
        <nav><a href="/">首页</a> | <a href="/about">关于我们</a></nav>
        <header><h1>网站头部标题</h1></header>
        <article>
            <h1>大模型推理加速实战</h1>
            <p>本文介绍如何利用投机采样优化 LLM 输出延迟。</p>
            <blockquote>核心思想是使用小模型提前预测草稿 token。</blockquote>
            <ul>
                <li>优势一：吞吐量提升 2-3 倍</li>
                <li>优势二：保持无损输出质量</li>
            </ul>
        </article>
        <footer><p>Copyright 2026</p></footer>
    </body>
    </html>
    """

    title, markdown, total_chars = crawl_service.html_to_clean_markdown(html, max_chars=500)
    assert title == "深度学习前沿进展"
    assert "大模型推理加速实战" in markdown
    assert "利用投机采样优化" in markdown
    assert "核心思想是使用小模型" in markdown
    assert "吞吐量提升" in markdown
    # 噪音标签应被彻底剔除
    assert "ad script" not in markdown
    assert "首页" not in markdown
    assert "Copyright" not in markdown


def test_crawl_via_crawl4ai_api() -> None:
    fake_api_response = {
        "results": [
            {
                "success": True,
                "title": "Grok 4.6 官方发布公告",
                "fit_markdown": "# Grok 4.6 发布\n\nSpaceXAI 今日正式推出 Grok 4.6 模型。",
                "markdown": "# 完整页面原始 Markdown",
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/crawl" in str(request.url)
        assert request.headers.get("authorization") == "Bearer test_token"
        assert "priority" not in request.content.decode()
        return httpx.Response(200, json=fake_api_response)

    transport = httpx.MockTransport(handler)
    with (
        patch.object(config, "CRAWL4AI_BASE_URL", "http://crawl4ai.local:11235"),
        patch.object(config, "CRAWL4AI_API_TOKEN", "test_token"),
        patch("httpx.AsyncClient", _mock_async_client(transport)),
        _public_dns(),
    ):
        result = asyncio.run(crawl_service.crawl_web_page("https://x.ai/news/grok-4-6"))

    assert "Grok 4.6 官方发布公告" in result
    assert "Crawl4AI 智能正文引擎" in result
    assert "SpaceXAI 今日正式推出 Grok 4.6 模型" in result


def test_crawl_via_crawl4ai_api_reads_markdown_object() -> None:
    # Crawl4AI >= 0.5 的 /crawl 把 markdown 序列化为对象（raw_markdown / fit_markdown），标题在 metadata 里
    fake_api_response = {
        "success": True,
        "results": [
            {
                "url": "https://example.com/a",
                "success": True,
                "markdown": {"raw_markdown": "# Raw title\n\nraw body", "fit_markdown": "", "markdown_with_citations": "", "references_markdown": ""},
                "metadata": {"title": "Example Article"},
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_api_response)

    with (
        patch.object(config, "CRAWL4AI_BASE_URL", "http://crawl4ai.local:11235"),
        patch.object(config, "CRAWL4AI_API_TOKEN", ""),
        patch("httpx.AsyncClient", _mock_async_client(httpx.MockTransport(handler))),
        _public_dns(),
    ):
        result = asyncio.run(crawl_service.crawl_web_page("https://example.com/a"))

    assert "网页深度提取：Example Article" in result
    assert "raw body" in result
    assert "{'raw_markdown'" not in result
    assert "Crawl4AI 智能正文引擎" in result

    fit_first = {"markdown": {"raw_markdown": "raw", "fit_markdown": "fit body"}}
    assert crawl_service._markdown_from_crawl4ai(fit_first) == "fit body"
    assert crawl_service._markdown_from_crawl4ai({"markdown": "plain string"}) == "plain string"
    assert crawl_service._markdown_from_crawl4ai({"markdown": None, "content": "legacy"}) == "legacy"
    assert crawl_service._title_from_crawl4ai({"metadata": None}, "默认") == "默认"


def test_crawl_via_builtin_fallback() -> None:
    fake_html = """
    <html>
    <head><title>成都天气预报官方发布</title></head>
    <body>
        <article>
            <p>成都市气象台发布最新预报：气温 25-28℃，多云间阴。</p>
        </article>
    </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=fake_html)

    with _builtin_only(httpx.MockTransport(handler)):
        result = asyncio.run(crawl_service.crawl_web_page("https://weather.example.com/chengdu"))

    assert "成都天气预报官方发布" in result
    assert "内置语义清洗引擎" in result
    assert "成都市气象台发布最新预报" in result


def test_crawl_follows_public_redirects_but_rejects_internal_targets() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "public.example.com":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:8080/internal"})
        if request.url.host == "start.example.com":
            return httpx.Response(301, headers={"Location": "/final"}) if request.url.path == "/" else httpx.Response(200, text="<html><head><title>Final</title></head><body><p>landed</p></body></html>")
        return httpx.Response(200, text="<html><head><title>INTERNAL</title></head><body><p>secret internal data</p></body></html>")

    transport = httpx.MockTransport(handler)
    with _builtin_only(transport):
        _expect_tool_error(crawl_service.crawl_web_page("http://public.example.com/article"), "非公网或不合法")
    assert seen == ["http://public.example.com/article"], seen

    seen.clear()
    with _builtin_only(transport):
        result = asyncio.run(crawl_service.crawl_web_page("http://start.example.com/"))
    assert seen == ["http://start.example.com/", "http://start.example.com/final"], seen
    assert "landed" in result

    def loop_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://loop.example.com/again"})

    with _builtin_only(httpx.MockTransport(loop_handler)):
        _expect_tool_error(crawl_service.crawl_web_page("http://loop.example.com/"), "重定向次数过多")


def test_crawl_builtin_fallback_caps_body_and_rejects_binary_content() -> None:
    big_html = "<html><head><title>Huge</title></head><body><p>" + ("正文" * 5000) + "</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/binary":
            return httpx.Response(200, content=b"\x89PNG" * 10, headers={"content-type": "image/png"})
        return httpx.Response(200, text=big_html)

    transport = httpx.MockTransport(handler)
    with _builtin_only(transport, patch.object(crawl_service, "MAX_RESPONSE_BYTES", 2048)):
        result = asyncio.run(crawl_service.crawl_web_page("https://example.com/huge", max_chars=5000))
        _expect_tool_error(crawl_service.crawl_web_page("https://example.com/binary"), "不是网页文本内容")

    # 只读取了前 2 KB，正文被截断但仍然可用，不会把整页读进内存
    assert "网页深度提取：Huge" in result
    assert result.count("正文") < 5000


def test_crawl_builtin_fallback_decodes_declared_charsets() -> None:
    gbk_html = "<html><head><meta charset=\"gb2312\"><title>编码测试</title></head><body><p>中文正文内容</p></body></html>".encode("gb18030")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=gbk_html, headers={"content-type": "text/html"})

    with _builtin_only(httpx.MockTransport(handler)):
        result = asyncio.run(crawl_service.crawl_web_page("https://example.com/gbk"))
    assert "编码测试" in result
    assert "中文正文内容" in result


def test_crawl_unsafe_url_rejection() -> None:
    _expect_tool_error(crawl_service.crawl_web_page("http://127.0.0.1:8080/sensitive"), "非公网或不合法")


def test_crawl_total_timeout() -> None:
    async def slow_extract(url: str, max_chars: int) -> str:
        await asyncio.sleep(1)
        return "never"

    with (
        _public_dns(),
        patch.object(crawl_service, "CRAWL_TOTAL_TIMEOUT_SECONDS", 0.05),
        patch.object(crawl_service, "_extract", slow_extract),
    ):
        _expect_tool_error(crawl_service.crawl_web_page("https://example.com/slow"), "超时")


def test_crawl_budget_truncation() -> None:
    fake_html = f"""
    <html>
    <head><title>长文章测试</title></head>
    <body>
        <article>
            <p>{'重要内容' * 300}</p>
        </article>
    </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=fake_html)

    with _builtin_only(httpx.MockTransport(handler)):
        result = asyncio.run(crawl_service.crawl_web_page("https://example.com/long-article", max_chars=200))

    assert "已按上下文安全预算精简提取前 200 字符" in result
    assert "..." in result


def test_extract_crawl_step_summary() -> None:
    assert crawl_service.extract_crawl_step_summary("### 网页深度提取：T\n- **提取引擎**：内置语义清洗引擎 （全文提取完成，共 1200 字符）") == "已提取 1200 字符正文"
    assert crawl_service.extract_crawl_step_summary("（已按上下文安全预算精简提取前 2000 字符，原文约 8000 字符）") == "已提取前 2000 字符，原文约 8000 字符"
    assert crawl_service.extract_crawl_step_summary("未能从网页「https://e.com」中提取到有效文本内容。") == "未提取到有效文本"
    assert crawl_service.extract_crawl_step_summary("普通文本") == ""


if __name__ == "__main__":
    test_is_safe_public_url()
    test_assert_public_url_rejects_hostnames_resolving_to_internal_addresses()
    test_html_to_clean_markdown()
    test_crawl_via_crawl4ai_api()
    test_crawl_via_crawl4ai_api_reads_markdown_object()
    test_crawl_via_builtin_fallback()
    test_crawl_follows_public_redirects_but_rejects_internal_targets()
    test_crawl_builtin_fallback_caps_body_and_rejects_binary_content()
    test_crawl_builtin_fallback_decodes_declared_charsets()
    test_crawl_unsafe_url_rejection()
    test_crawl_total_timeout()
    test_crawl_budget_truncation()
    test_extract_crawl_step_summary()
