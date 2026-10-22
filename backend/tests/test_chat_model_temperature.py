from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import httpx

from app.llms.router import ModelRouter
from app.services.agent_service import stream_chat_agent


def test_temperature_on_provider_wire() -> None:
    async def check(provider, model_id, base_url, omitted):
        requests = []

        def handler(request):
            body = json.loads(request.content)
            requests.append(request)
            assert body["model"] == model_id
            assert ("temperature" not in body) == omitted, body
            if not omitted:
                assert body["temperature"] == 0.3
            if provider == "anthropic":
                return httpx.Response(200, json={
                    "id": "msg_test", "type": "message", "role": "assistant", "model": model_id,
                    "content": [{"type": "text", "text": "OK"}], "stop_reason": "end_turn",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                })
            return httpx.Response(200, json={
                "id": "chat_test", "object": "chat.completion", "created": 1, "model": model_id,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("langchain_anthropic.chat_models._get_default_async_httpx_client", return_value=client):
                kwargs = {} if provider == "anthropic" else {"http_async_client": client}
                model = ModelRouter().chat_model(provider, "test", model_id, base_url, temperature=0.3, **kwargs)
                assert (await model.ainvoke("test")).content == "OK"
        assert len(requests) == 1
        assert requests[0].url.path.endswith("/messages" if provider == "anthropic" else "/chat/completions")

    for provider, base_url in (
        ("anthropic", ""),  # Official native endpoint, intercepted before the network.
        ("anthropic", "https://relay.test"),
        ("openai", "https://relay.test/v1"),
        ("custom", "https://relay.test/v1"),
    ):
        for model_id, omitted in (
            ("claude-fable-5", True), ("claude-fable-5-20261001", True),
            ("claude-sonnet-5.5", False), ("claude-fable-50", False),
        ):
            asyncio.run(check(provider, model_id, base_url, omitted))


def test_agent_and_plain_fallback_omit_temperature() -> None:
    async def check():
        requests = []

        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            assert "temperature" not in body
            events = [{"type": "message_start", "message": {
                "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-fable-5",
                "content": [], "stop_reason": None, "usage": {"input_tokens": 1, "output_tokens": 0},
            }}]
            if len(requests) > 1:
                events.extend([
                    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "OK"}},
                    {"type": "content_block_stop", "index": 0},
                ])
            events.extend([
                {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 1}},
                {"type": "message_stop"},
            ])
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text="".join(
                f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
            ))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("langchain_anthropic.chat_models._get_default_async_httpx_client", return_value=client):
                events = [event async for event in stream_chat_agent(
                    {"provider": "anthropic", "apiKey": "test", "model": "claude-fable-5", "baseUrl": "https://relay.test"},
                    "chat_temperature", [{"role": "user", "content": "test"}], None,
                )]
        assert len(requests) == 2, requests
        assert requests[0]["tools"] and "tools" not in requests[1]
        assert events[-1]["content"] == "OK", events

    asyncio.run(check())


if __name__ == "__main__":
    test_temperature_on_provider_wire()
    test_agent_and_plain_fallback_omit_temperature()
