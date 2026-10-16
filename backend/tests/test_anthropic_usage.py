from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import httpx
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import HumanMessage

from app.llms.router import ModelRouter
from app.services import agent_service
from app.services.usage_service import aggregate_token_usage, calculate_cost_micros


def _response(tail: list[dict] | None, *, input_tokens: int = 7) -> httpx.Response:
    events = [
        {"type": "message_start", "message": {
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-test",
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": 0,
                      "cache_read_input_tokens": 20, "cache_creation_input_tokens": 10},
        }},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "OK"}},
        {"type": "content_block_stop", "index": 0},
    ]
    if tail is not None:
        for index, usage in enumerate(tail):
            events.append({"type": "message_delta", "usage": usage,
                           "delta": {"stop_reason": "end_turn" if index == len(tail) - 1 else None,
                                     "stop_sequence": None}})
        events.append({"type": "message_stop"})
    body = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events)
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


def test_anthropic_stream_usage_is_not_lost_or_double_counted() -> None:
    async def check(tail, expected_output):
        transport = httpx.MockTransport(lambda _: _response(tail))
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("langchain_anthropic.chat_models._get_default_async_httpx_client", return_value=client):
                model = ModelRouter().chat_model("anthropic", "test", "claude-test", "https://relay.test")
                with get_usage_metadata_callback() as callback:
                    chunks = [chunk async for chunk in model.astream([HumanMessage(content="test")])]
        result = chunks[0]
        for chunk in chunks[1:]:
            result += chunk
        assert result.content == "OK"
        usage = aggregate_token_usage(result.usage_metadata)
        assert usage == {"inputTokens": 37, "outputTokens": expected_output,
                         "cacheReadTokens": 20, "cacheWriteTokens": 10}, usage
        assert aggregate_token_usage(callback.usage_metadata) == usage
        assert result.usage_metadata["total_tokens"] == 37 + expected_output

    # Legacy tails only report output; newer ones repeat the full cumulative usage.
    asyncio.run(check([{"output_tokens": 8}], 8))
    asyncio.run(check([{"input_tokens": 7, "output_tokens": 8,
                        "cache_read_input_tokens": 20, "cache_creation_input_tokens": 10}], 8))
    asyncio.run(check([{"output_tokens": 4}, {"output_tokens": 8}], 8))
    # An incomplete relay stream must retain known usage, never estimate missing output.
    asyncio.run(check(None, 0))


def test_anthropic_sync_stream_and_disabled_usage() -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: _response([{"output_tokens": 8}]))) as client:
        with patch("langchain_anthropic.chat_models._get_default_httpx_client", return_value=client):
            model = ModelRouter().chat_model("anthropic", "test", "claude-test", "https://relay.test")
            with get_usage_metadata_callback() as callback:
                list(model.stream("test"))
            assert aggregate_token_usage(callback.usage_metadata)["inputTokens"] == 37
            assert aggregate_token_usage(callback.usage_metadata)["outputTokens"] == 8
            assert all(chunk.usage_metadata is None for chunk in model.stream("test", stream_usage=False))


def test_incomplete_relay_usage_reaches_agent_billing() -> None:
    async def check():
        def handler(request):
            assert json.loads(request.content)["tools"]
            response = _response(None)
            # Match the observed relay: input=7, output=0, no final message_delta/stop.
            body = response.text.replace('"output_tokens": 1', '"output_tokens": 0')
            body = body.replace('"cache_read_input_tokens": 20', '"cache_read_input_tokens": 0')
            body = body.replace('"cache_creation_input_tokens": 10', '"cache_creation_input_tokens": 0')
            return httpx.Response(200, text=body, headers=response.headers)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with (
                patch("langchain_anthropic.chat_models._get_default_async_httpx_client", return_value=client),
                patch("app.llms.anthropic.logger.warning") as warning,
            ):
                events = [event async for event in agent_service.stream_chat_agent(
                    {"provider": "anthropic", "apiKey": "test", "model": "claude-test", "baseUrl": "https://relay.test"},
                    "chat_usage", [{"role": "user", "content": "test"}], None,
                )]
        assert events[-1]["content"] == "OK"
        usage = events[-1]["usage"]
        assert usage == {"inputTokens": 7, "outputTokens": 0, "cacheReadTokens": 0, "cacheWriteTokens": 0}, usage
        assert calculate_cost_micros({"input_price_per_million": "2", "output_price_per_million": "2",
                                      "pricing_multiplier": "2"}, usage) == 28
        warning.assert_called_once()
        assert "without a final stop_reason" in warning.call_args.args[0]

    asyncio.run(check())


def test_anthropic_concurrent_streams_keep_separate_counts() -> None:
    async def check():
        def handler(request):
            value = int(json.loads(request.content)["messages"][0]["content"])
            return _response([{"output_tokens": value}], input_tokens=value)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("langchain_anthropic.chat_models._get_default_async_httpx_client", return_value=client):
                model = ModelRouter().chat_model("anthropic", "test", "claude-test", "https://relay.test")

                async def collect(value):
                    result = None
                    async for chunk in model.astream(str(value)):
                        result = chunk if result is None else result + chunk
                    return aggregate_token_usage(result.usage_metadata)

                results = await asyncio.gather(collect(11), collect(19))
        assert [item["inputTokens"] for item in results] == [41, 49]
        assert [item["outputTokens"] for item in results] == [11, 19]

    asyncio.run(check())


if __name__ == "__main__":
    test_anthropic_stream_usage_is_not_lost_or_double_counted()
    test_anthropic_sync_stream_and_disabled_usage()
    test_incomplete_relay_usage_reaches_agent_billing()
    test_anthropic_concurrent_streams_keep_separate_counts()
