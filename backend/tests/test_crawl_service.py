from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
from langchain_core.tools import ToolException

from app.core import config
from app.services import crawl_service

_RealAsyncClient = httpx.AsyncClient


def _mock_async_client(transport: httpx.MockTransport):
    return lambda **kwargs: _RealAsyncClient(transport=transport, **{k: v for k, v in kwargs.items() if k != "transport"})


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
    assert not crawl_service.is_safe_public_url("file:///etc/passwd")
    assert not crawl_service.is_safe_public_url("ftp://ftp.example.com")
    assert not crawl_service.is_safe_public_url("javascript:alert(1)")


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
        return httpx.Response(200, json=fake_api_response)

    transport = httpx.MockTransport(handler)
    with (
        patch.object(config, "CRAWL4AI_BASE_URL", "http://crawl4ai.local:11235"),
        patch.object(config, "CRAWL4AI_API_TOKEN", "test_token"),
        patch("httpx.AsyncClient", _mock_async_client(transport)),
    ):
        result = asyncio.run(crawl_service.crawl_web_page("https://x.ai/news/grok-4-6"))

    assert "Grok 4.6 官方发布公告" in result
    assert "Crawl4AI 智能正文引擎" in result
    assert "SpaceXAI 今日正式推出 Grok 4.6 模型" in result


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

    transport = httpx.MockTransport(handler)
    with (
        patch.object(config, "CRAWL4AI_BASE_URL", ""),
        patch.object(crawl_service, "_crawl_via_local_crawl4ai", return_value=None),
        patch("httpx.AsyncClient", _mock_async_client(transport)),
    ):
        result = asyncio.run(crawl_service.crawl_web_page("https://weather.example.com/chengdu"))

    assert "成都天气预报官方发布" in result
    assert "内置语义清洗引擎" in result
    assert "成都市气象台发布最新预报" in result


def test_crawl_unsafe_url_rejection() -> None:
    try:
        asyncio.run(crawl_service.crawl_web_page("http://127.0.0.1:8080/sensitive"))
        assert False, "should have raised ToolException"
    except ToolException as exc:
        assert "非公网或不合法" in str(exc)


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

    transport = httpx.MockTransport(handler)
    with (
        patch.object(config, "CRAWL4AI_BASE_URL", ""),
        patch.object(crawl_service, "_crawl_via_local_crawl4ai", return_value=None),
        patch("httpx.AsyncClient", _mock_async_client(transport)),
    ):
        result = asyncio.run(crawl_service.crawl_web_page("https://example.com/long-article", max_chars=200))

    assert "已按上下文安全预算精简提取前 200 字符" in result
    assert "..." in result


if __name__ == "__main__":
    test_is_safe_public_url()
    test_html_to_clean_markdown()
    test_crawl_via_crawl4ai_api()
    test_crawl_via_builtin_fallback()
    test_crawl_unsafe_url_rejection()
    test_crawl_budget_truncation()
