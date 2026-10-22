from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

from app.services import agent_service


CONFIG = {"provider": "anthropic", "apiKey": "test", "model": "claude-sonnet-5.5", "baseUrl": "https://relay.test"}
USAGE = {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
PROGRESS = "搜索结果里有几条相关线索。我再读取几个页面，拿到更具体的头条。"
ANSWER = "根据已读取的资料，今天的科技新闻如下：测试新闻摘要。"


class RelayModel(FakeMessagesListChatModel):
    requests: list[dict] = Field(default_factory=list)
    end_only_at: int | None = None

    def _should_stream(self, *, async_api, **kwargs):
        if self.end_only_at == len(self.requests) + 1:
            return False
        return super()._should_stream(async_api=async_api, **kwargs)

    def bind_tools(self, tools, **kwargs):
        return self.bind(tools_enabled=bool(tools))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.requests.append({"messages": messages, "tools_enabled": kwargs.get("tools_enabled", False)})
        assert len(self.requests) <= len(self.responses), "The final-answer recovery must be bounded"
        response = self.responses[len(self.requests) - 1].model_copy(update={
            "id": None, "response_metadata": {"model_name": "claude-sonnet-5.5"},
        })
        return ChatResult(generations=[ChatGeneration(message=response)])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        response = self._generate(messages, stop, **kwargs).generations[0].message
        # Relay-style output: text/thinking first, tool-call arguments later.
        if isinstance(response.content, str) and response.content:
            yield ChatGenerationChunk(message=AIMessageChunk(content=response.content))
        elif response.content:
            yield ChatGenerationChunk(message=AIMessageChunk(content=response.content))
        yield ChatGenerationChunk(message=AIMessageChunk(
            content="", usage_metadata=response.usage_metadata, response_metadata=response.response_metadata,
            tool_call_chunks=[{"name": call["name"], "args": json.dumps(call["args"]), "id": call["id"], "index": index}
                              for index, call in enumerate(response.tool_calls)],
            chunk_position="last",
        ))


def sequence(final: str = ANSWER) -> list[AIMessage]:
    return [
        AIMessage(content=PROGRESS, tool_calls=[{
            "name": "fetch_web_content", "args": {"url": "https://example.com/news"}, "id": "read_news",
        }], usage_metadata=USAGE),
        AIMessage(content=[{"type": "thinking", "thinking": "I'm now drafting the summary."}], usage_metadata=USAGE),
        AIMessage(content=final, usage_metadata=USAGE),
    ]


async def run(model, *, stream):
    crawl = AsyncMock(return_value="来源资料：测试新闻，来源 https://example.com/news")
    with patch.object(agent_service.models, "chat_model", return_value=model), patch.object(agent_service, "crawl_web_page", crawl):
        if stream:
            events = [event async for event in agent_service.stream_chat_agent(
                CONFIG, "final-answer-test", [{"role": "user", "content": "搜索今天的科技新闻"}], None,
            )]
            content, usage = events[-1]["content"], events[-1]["usage"]
        else:
            result = await agent_service.run_chat_agent(
                CONFIG, "final-answer-test", [{"role": "user", "content": "搜索今天的科技新闻"}], None,
            )
            content, usage, events = result.content, result.usage, []
    assert crawl.await_count == 1
    return content, usage, events


def test_reasoning_only_final_after_tools_recovers_with_evidence_and_usage() -> None:
    async def check():
        for stream in (False, True):
            model = RelayModel(responses=sequence())
            content, usage, events = await run(model, stream=stream)
            assert content == ANSWER, content
            assert len(model.requests) == 3
            recovery = model.requests[-1]
            assert not recovery["tools_enabled"]
            assert any(isinstance(message, ToolMessage) and "测试新闻" in message.content for message in recovery["messages"])
            assert usage["inputTokens"] == 30 and usage["outputTokens"] == 6, usage
            if stream:
                assert ANSWER in "".join(event["content"] for event in events if event["type"] == "content_delta")
    asyncio.run(check())


def test_successful_final_without_token_events_is_still_emitted() -> None:
    model = RelayModel(end_only_at=2, responses=[sequence()[0], AIMessage(content=ANSWER, usage_metadata=USAGE)])
    content, usage, events = asyncio.run(run(model, stream=True))
    assert content == ANSWER
    streamed = "".join(event["content"] for event in events if event["type"] == "content_delta")
    assert PROGRESS in streamed and ANSWER in streamed
    assert len(model.requests) == 2 and usage["inputTokens"] == 20


def test_recovery_without_text_returns_an_explicit_notice_and_does_not_loop() -> None:
    async def check():
        for stream in (False, True):
            model = RelayModel(responses=sequence(final=""))
            content, usage, events = await run(model, stream=stream)
            assert "正文" in content and "未" in content, content
            assert content != PROGRESS and len(model.requests) == 3
            assert usage["inputTokens"] == 30
            if stream:
                assert content in "".join(event["content"] for event in events if event["type"] == "content_delta")
    asyncio.run(check())


def test_final_answer_never_uses_a_tool_preamble() -> None:
    output = {"messages": [HumanMessage(content="读取新闻"), *sequence()[:2]]}
    assert agent_service._final_answer(output, base_count=1) == ""
    output["messages"].pop()
    assert agent_service._final_answer(output, base_count=1) == ""


def test_native_anthropic_relay_recovers_thinking_only_stream() -> None:
    async def check():
        requests = []

        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            number = len(requests)
            assert number <= 3
            events = [{"type": "message_start", "message": {
                "id": f"msg_{number}", "type": "message", "role": "assistant", "model": CONFIG["model"],
                "content": [], "stop_reason": None, "usage": {"input_tokens": 10, "output_tokens": 0},
            }}]

            def block(index, start, delta):
                events.extend([
                    {"type": "content_block_start", "index": index, "content_block": start},
                    {"type": "content_block_delta", "index": index, "delta": delta},
                    {"type": "content_block_stop", "index": index},
                ])

            if number == 1:
                block(0, {"type": "text", "text": ""}, {"type": "text_delta", "text": PROGRESS})
                block(1, {"type": "tool_use", "id": "read_news", "name": "fetch_web_content", "input": {}},
                      {"type": "input_json_delta", "partial_json": json.dumps({"url": "https://example.com/news"})})
            elif number == 2:
                block(0, {"type": "thinking", "thinking": "", "signature": ""},
                      {"type": "thinking_delta", "thinking": "I'm now drafting the summary."})
            else:
                assert "tools" not in body, body
                assert body["max_tokens"] == 8192, body
                assert "测试新闻" in json.dumps(body["messages"], ensure_ascii=False)
                block(0, {"type": "text", "text": ""}, {"type": "text_delta", "text": ANSWER})
            events.extend([
                {"type": "message_delta", "delta": {"stop_reason": {1: "tool_use", 2: "max_tokens", 3: "end_turn"}[number], "stop_sequence": None}, "usage": {"output_tokens": 2}},
                {"type": "message_stop"},
            ])
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text="".join(
                f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
            ))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("langchain_anthropic.chat_models._get_default_async_httpx_client", return_value=client), patch.object(
                agent_service, "crawl_web_page", AsyncMock(return_value="来源资料：测试新闻 https://example.com/news"),
            ):
                events = [event async for event in agent_service.stream_chat_agent(
                    CONFIG, "native-relay-test", [{"role": "user", "content": "搜索新闻"}], None,
                )]
        assert len(requests) == 3
        assert events[-1]["content"] == ANSWER
        assert ANSWER in "".join(event["content"] for event in events if event["type"] == "content_delta")
        assert events[-1]["usage"]["inputTokens"] == 30 and events[-1]["usage"]["outputTokens"] == 6

    asyncio.run(check())


if __name__ == "__main__":
    test_reasoning_only_final_after_tools_recovers_with_evidence_and_usage()
    test_successful_final_without_token_events_is_still_emitted()
    test_recovery_without_text_returns_an_explicit_notice_and_does_not_loop()
    test_final_answer_never_uses_a_tool_preamble()
    test_native_anthropic_relay_recovers_thinking_only_stream()
