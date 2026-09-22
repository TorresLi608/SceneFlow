from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
from langchain_core.tools import ToolException

from app.core import config
from app.services import searxng_service

_RealAsyncClient = httpx.AsyncClient


def _mock_async_client(transport: httpx.MockTransport):
    return lambda **kwargs: _RealAsyncClient(transport=transport, **{k: v for k, v in kwargs.items() if k != "transport"})


def test_searxng_unconfigured() -> None:
    with patch.object(config, "SEARXNG_BASE_URL", ""):
        assert not searxng_service.is_searxng_configured()
        try:
            asyncio.run(searxng_service.search_searxng("python news"))
            assert False, "should have raised ToolException"
        except ToolException as exc:
            assert "尚未配置" in str(exc)


def test_searxng_empty_query() -> None:
    with patch.object(config, "SEARXNG_BASE_URL", "http://searxng.local:8080"):
        try:
            asyncio.run(searxng_service.search_searxng("   "))
            assert False, "should have raised ToolException"
        except ToolException as exc:
            assert "不能为空" in str(exc)


def test_searxng_search_success_without_token() -> None:
    fake_response = {
        "query": "fastapi tutorial",
        "results": [
            {
                "title": "FastAPI 官方文档",
                "url": "https://fastapi.tiangolo.com",
                "content": "FastAPI framework, high performance, easy to learn.",
            },
            {
                "title": "FastAPI GitHub",
                "url": "https://github.com/fastapi/fastapi",
                "content": "FastAPI repository on GitHub.",
            },
        ],
    }

    recorded_request: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded_request["url"] = str(request.url)
        recorded_request["params"] = dict(request.url.params)
        recorded_request["headers"] = dict(request.headers)
        return httpx.Response(200, json=fake_response)

    transport = httpx.MockTransport(handler)
    with (
        patch.object(config, "SEARXNG_BASE_URL", "http://searxng.local:8080"),
        patch.object(config, "SEARXNG_ENGINE_TOKEN", ""),
        patch.object(config, "SEARXNG_ENGINES", ""),
        patch("httpx.AsyncClient", _mock_async_client(transport)),
    ):
        assert searxng_service.is_searxng_configured()
        result = asyncio.run(searxng_service.search_searxng("fastapi tutorial"))

    assert "FastAPI 官方文档" in result
    assert "https://fastapi.tiangolo.com" in result
    assert "FastAPI GitHub" in result
    assert recorded_request["params"]["q"] == "fastapi tutorial"
    assert recorded_request["params"]["format"] == "json"
    assert "tokens" not in recorded_request["params"]
    assert recorded_request["params"]["engines"] == searxng_service.DEFAULT_SEARCH_ENGINES
    assert "authorization" not in recorded_request["headers"]


def test_searxng_sanitize_query() -> None:
    assert searxng_service.sanitize_query("成都今天天气 2025年? 实时天气？") == "成都今天天气 2025年 实时天气"
    assert searxng_service.sanitize_query("  'Python 3.12' 发布会!  ") == "Python 3.12 发布会"
    assert searxng_service.sanitize_query("???") == "???"


def test_searxng_step_summary() -> None:
    assert searxng_service.extract_search_step_summary("未检索到与「成都天气」相关的网络搜索结果。") == "未检索到匹配网页"
    assert searxng_service.extract_search_step_summary("### 网页搜索结果（关键词：成都天气，共找到 6 条）\n1. xxx") == "检索到 6 条相关网页"
    assert searxng_service.extract_search_step_summary(searxng_service.search_limit_notice(3)) == "已达本轮搜索上限"
    assert searxng_service.extract_search_step_summary("普通文本") == ""


def test_searxng_format_results_header_matches_listed_entries() -> None:
    items = [{"title": f"T{i}", "url": f"https://e.com/{i}", "content": "x" * 180} for i in range(1, 6)]
    formatted = searxng_service.format_search_results("q", items, max_snippet_chars=180, max_total_chars=500)
    listed = sum(1 for line in formatted.splitlines() if line[:2].rstrip(".").isdigit())
    assert listed == 2, formatted
    assert formatted.startswith("### 网页搜索结果（关键词：q，共精选 2 条）")
    assert searxng_service.extract_search_step_summary(formatted) == "检索到 2 条精选网页"


def test_searxng_fallback_on_unresponsive_engines() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        engines = request.url.params.get("engines")
        calls.append(engines)
        if engines == "google":
            # 模拟指定引擎响应超时且返回空结果
            return httpx.Response(200, json={"results": [], "unresponsive_engines": [["google", "timeout"]]})
        # 降级到默认高可用引擎
        return httpx.Response(
            200,
            json={"results": [{"title": "备用结果", "url": "https://backup.com", "content": "降级成功"}]},
        )

    transport = httpx.MockTransport(handler)
    with (
        patch.object(config, "SEARXNG_BASE_URL", "http://searxng.local:8080"),
        patch.object(config, "SEARXNG_ENGINES", "google"),
        patch("httpx.AsyncClient", _mock_async_client(transport)),
    ):
        result = asyncio.run(searxng_service.search_searxng("test query"))

    assert "备用结果" in result
    assert calls == ["google", searxng_service.DEFAULT_SEARCH_ENGINES]


def test_searxng_search_with_token() -> None:
    fake_response = {
        "query": "ai drama",
        "results": [
            {
                "title": "AI Short Drama",
                "url": "https://example.com/drama",
                "content": "Modern AI short drama generation.",
            }
        ],
    }

    recorded_request: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded_request["params"] = dict(request.url.params)
        recorded_request["headers"] = dict(request.headers)
        return httpx.Response(200, json=fake_response)

    transport = httpx.MockTransport(handler)
    with (
        patch.object(config, "SEARXNG_BASE_URL", "http://searxng.local:8080"),
        patch.object(config, "SEARXNG_ENGINE_TOKEN", "secret-token-123"),
        patch.object(config, "SEARXNG_ENGINES", ""),
        patch("httpx.AsyncClient", _mock_async_client(transport)),
    ):
        result = asyncio.run(searxng_service.search_searxng("ai drama"))

    assert "AI Short Drama" in result
    # SearXNG reads private-engine tokens from the `tokens` parameter; a bearer header serves reverse proxies.
    assert recorded_request["params"]["tokens"] == "secret-token-123"
    assert "token" not in recorded_request["params"]
    assert recorded_request["headers"]["authorization"] == "Bearer secret-token-123"
    assert "x-token" not in recorded_request["headers"]


def test_searxng_empty_results() -> None:
    fake_response = {
        "query": "nonexistent term 123456",
        "results": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_response)

    transport = httpx.MockTransport(handler)
    with (
        patch.object(config, "SEARXNG_BASE_URL", "http://searxng.local:8080"),
        patch.object(config, "SEARXNG_ENGINES", ""),
        patch("httpx.AsyncClient", _mock_async_client(transport)),
    ):
        result = asyncio.run(searxng_service.search_searxng("nonexistent term 123456"))

    assert "未检索到与「nonexistent term 123456」相关的网络搜索结果。" in result


def test_searxng_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timed out")

    transport = httpx.MockTransport(handler)
    with (
        patch.object(config, "SEARXNG_BASE_URL", "http://searxng.local:8080"),
        patch("httpx.AsyncClient", _mock_async_client(transport)),
    ):
        try:
            asyncio.run(searxng_service.search_searxng("timeout test"))
            assert False, "should have raised ToolException"
        except ToolException as exc:
            assert "超时" in str(exc)


def test_searxng_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway")

    transport = httpx.MockTransport(handler)
    with (
        patch.object(config, "SEARXNG_BASE_URL", "http://searxng.local:8080"),
        patch("httpx.AsyncClient", _mock_async_client(transport)),
    ):
        try:
            asyncio.run(searxng_service.search_searxng("error test"))
            assert False, "should have raised ToolException"
        except ToolException as exc:
            assert "502" in str(exc)


def test_searxng_search_with_engines() -> None:
    fake_response = {
        "query": "custom engines query",
        "results": [
            {
                "title": "Engine Result",
                "url": "https://example.com/engine",
                "content": "Result from specified engine.",
            }
        ],
    }

    recorded_request: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded_request["params"] = dict(request.url.params)
        return httpx.Response(200, json=fake_response)

    transport = httpx.MockTransport(handler)
    with (
        patch.object(config, "SEARXNG_BASE_URL", "http://searxng.local:8080"),
        patch.object(config, "SEARXNG_ENGINES", "sogou,360search"),
        patch("httpx.AsyncClient", _mock_async_client(transport)),
    ):
        result = asyncio.run(searxng_service.search_searxng("custom engines query"))

    assert "Engine Result" in result
    assert recorded_request["params"]["engines"] == "sogou,360search"


def test_searxng_format_results_truncation_and_budget() -> None:
    fake_items = [
        {
            "title": "Title 1",
            "url": "https://example.com/1",
            "content": "A" * 500,  # 超过单条最大长度
        },
        {
            "title": "Blocked Page",
            "url": "https://example.com/blocked",
            "content": "Attention Required! | Cloudflare Please enable JavaScript",
        },
        {
            "title": "Title 2",
            "url": "https://example.com/2",
            "content": "Short content 2",
        },
        {
            "title": "Title 3",
            "url": "https://example.com/3",
            "content": "B" * 500,
        },
    ]

    # 单条限制 100 字符，总字符限制 400 字符
    formatted = searxng_service.format_search_results("测试搜索", fake_items, max_snippet_chars=100, max_total_chars=400)
    assert "Blocked Page" not in formatted  # 噪音过滤
    assert "Cloudflare" not in formatted
    assert "Title 1" in formatted
    assert "A" * 101 not in formatted  # 单条截断生效
    assert "..." in formatted
    assert len(formatted) <= 500  # 总长度严格受控


if __name__ == "__main__":
    test_searxng_unconfigured()
    test_searxng_empty_query()
    test_searxng_search_success_without_token()
    test_searxng_sanitize_query()
    test_searxng_step_summary()
    test_searxng_format_results_header_matches_listed_entries()
    test_searxng_fallback_on_unresponsive_engines()
    test_searxng_search_with_token()
    test_searxng_empty_results()
    test_searxng_timeout()
    test_searxng_http_error()
    test_searxng_search_with_engines()
    test_searxng_format_results_truncation_and_budget()
