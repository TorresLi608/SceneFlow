from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.services import agent_service, artifact_service
from app.llms.router import ImageResult
from app.services.chat_agent_middleware import MAX_TOOL_CALLS, MAX_TOOL_ROUNDS, FINAL_ANSWER_FALLBACK


CONFIG = {"provider": "openai", "apiKey": "test", "model": "fake", "baseUrl": ""}
USAGE = {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}


class BudgetModel(FakeMessagesListChatModel):
    requests: list[dict] = Field(default_factory=list)
    ignore_tool_disable: bool = False

    def bind_tools(self, tools, **kwargs):
        return self.bind(tools_enabled=bool(tools))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        enabled = kwargs.get("tools_enabled", False)
        self.requests.append({"messages": messages, "tools_enabled": enabled})
        if not enabled and not self.ignore_tool_disable:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content="根据已有资料给出回答，未完成的部分暂无法确认。", usage_metadata=USAGE,
            ))])
        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        # The fake model cycles its stored AIMessage objects; real provider calls
        # have distinct response IDs even when their content repeats.
        return ChatResult(generations=[ChatGeneration(message=g.message.model_copy(update={"id": None})) for g in result.generations])


def calls(*urls: str, prefix="call") -> AIMessage:
    return AIMessage(content="", usage_metadata=USAGE, tool_calls=[
        {"name": "fetch_web_content", "args": {"url": url}, "id": f"{prefix}_{index}"}
        for index, url in enumerate(urls)
    ])


async def run(model, crawl, *, stream=False, session="budget-test"):
    with patch.object(agent_service.models, "chat_model", return_value=model), patch.object(agent_service, "crawl_web_page", crawl):
        if stream:
            events = [event async for event in agent_service.stream_chat_agent(
                CONFIG, session, [{"role": "user", "content": "比较这些网页"}], None,
            )]
            assert events[-1]["type"] == "agent_complete"
            return events[-1]
        return await agent_service.run_chat_agent(
            CONFIG, session, [{"role": "user", "content": "比较这些网页"}], None,
        )


def test_long_tool_sequence_finishes_with_evidence_and_usage() -> None:
    async def check():
        for stream in (False, True):
            model = BudgetModel(disable_streaming=True, responses=[
                calls(f"https://example.com/{i}", prefix=f"round{i}") for i in range(10)
            ])
            crawl = AsyncMock(return_value="已读取的网页资料")
            result = await run(model, crawl, stream=stream)
            assert crawl.await_count == MAX_TOOL_ROUNDS
            assert len(model.requests) == MAX_TOOL_ROUNDS + 1
            assert not model.requests[-1]["tools_enabled"]
            evidence = [m for m in model.requests[-1]["messages"] if isinstance(m, ToolMessage)]
            assert len(evidence) == MAX_TOOL_ROUNDS
            assert all(m.content == "已读取的网页资料" for m in evidence)
            content = result["content"] if stream else result.content
            usage = result["usage"] if stream else result.usage
            assert "根据已有资料" in content
            assert usage["inputTokens"] == (MAX_TOOL_ROUNDS + 1) * 10
            assert usage["outputTokens"] == (MAX_TOOL_ROUNDS + 1) * 2
    asyncio.run(check())


def test_parallel_tool_batch_cannot_exceed_budget() -> None:
    model = BudgetModel(disable_streaming=True, responses=[calls(*[
        f"https://example.com/{i}" for i in range(MAX_TOOL_CALLS + 3)
    ])])
    crawl = AsyncMock(return_value="网页内容")
    result = asyncio.run(run(model, crawl))
    assert crawl.await_count == MAX_TOOL_CALLS
    assert len(model.requests) == 2
    assert "根据已有资料" in result.content
    messages = model.requests[-1]["messages"]
    assert len([m for m in messages if isinstance(m, ToolMessage)]) == MAX_TOOL_CALLS + 3


def test_duplicate_calls_share_inflight_result_and_keep_tool_ids() -> None:
    async def check():
        for parallel in (False, True):
            url = "https://example.com/same"
            responses = [calls(url, url)] if parallel else [calls(url, prefix="first"), calls(url, prefix="repeat")]
            model = BudgetModel(disable_streaming=True, responses=responses)
            crawl = AsyncMock(return_value="只提取一次的资料")
            await run(model, crawl, stream=True)
            assert crawl.await_count == 1
            tool_messages = [m for m in model.requests[-1]["messages"] if isinstance(m, ToolMessage)]
            assert len(tool_messages) == 2
            assert len({m.tool_call_id for m in tool_messages}) == 2
            assert all(m.content == "只提取一次的资料" for m in tool_messages)
            assert not model.requests[-1]["tools_enabled"]
    asyncio.run(check())


def test_consecutive_failures_finish_and_preserve_error_notice() -> None:
    model = BudgetModel(disable_streaming=True, responses=[
        AIMessage(content="", usage_metadata=USAGE, tool_calls=[{
            "name": "generate_image", "args": {"prompt": str(i)}, "id": f"image{i}",
        }]) for i in range(5)
    ])
    # Missing image configuration raises ToolException, handled by StructuredTool.
    result = asyncio.run(run(model, AsyncMock(), stream=True))
    assert len(model.requests) == 3
    assert not model.requests[-1]["tools_enabled"]
    assert "图片生成失败" in result["content"]
    assert result["usage"]["inputTokens"] == 30


def test_nonconforming_model_still_cannot_restart_tools() -> None:
    model = BudgetModel(disable_streaming=True, ignore_tool_disable=True, responses=[
        calls("https://example.com/same", "https://example.com/same")
    ])
    crawl = AsyncMock(return_value="网页内容")
    result = asyncio.run(run(model, crawl, stream=True))
    assert crawl.await_count == 1
    assert len(model.requests) == 2
    assert result["content"] == FINAL_ANSWER_FALLBACK
    assert result["usage"]["inputTokens"] == 20


def test_budget_and_cache_are_isolated_between_turns() -> None:
    async def check():
        crawl = AsyncMock(return_value="网页内容")
        model = BudgetModel(disable_streaming=True, responses=[calls("https://example.com/same", "https://example.com/same")])
        with patch.object(agent_service.models, "chat_model", return_value=model), patch.object(agent_service, "crawl_web_page", crawl):
            agents = [agent_service._agent(CONFIG, f"turn{i}", None) for i in range(2)]
            # Both agents see the same arguments; neither turn may use the other's cache.
            await asyncio.gather(*[agent.ainvoke({"messages": [HumanMessage(content="读取网页")]}) for agent in agents])
        assert crawl.await_count == 2
    asyncio.run(check())


def test_plain_answer_does_not_add_a_model_call() -> None:
    model = BudgetModel(disable_streaming=True, responses=[AIMessage(content="你好", usage_metadata=USAGE)])
    crawl = AsyncMock()
    result = asyncio.run(run(model, crawl))
    assert result.content == "你好"
    assert len(model.requests) == 1 and crawl.await_count == 0


def test_duplicate_image_requests_create_one_artifact() -> None:
    async def check():
        with tempfile.TemporaryDirectory() as directory:
            generate = AsyncMock(return_value=ImageResult(data=b"image-bytes", format="png"))
            model = BudgetModel(disable_streaming=True, responses=[AIMessage(content="", tool_calls=[
                {"name": "generate_image", "args": {"prompt": "一只猫"}, "id": f"image{i}"} for i in range(2)
            ])])
            with patch.object(agent_service.models, "chat_model", return_value=model), patch.object(agent_service.models, "generate_image", generate), patch.object(artifact_service, "PRIVATE_GENERATED_DIR", Path(directory)):
                result = await agent_service.run_chat_agent(CONFIG, "image-budget", [{"role": "user", "content": "生成图片"}], {"provider": "openai", "apiKey": "test", "model": "fake"})
            assert generate.await_count == 1
            assert len(list(Path(directory).rglob("*.png"))) == 1
            assert result.content.count("![") == 1
    asyncio.run(check())


def test_cancelling_turn_cancels_inflight_tool() -> None:
    async def check():
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def slow_crawl(url):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        model = BudgetModel(disable_streaming=True, responses=[calls("https://example.com/slow")])
        task = asyncio.create_task(run(model, slow_crawl))
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("cancellation must propagate")
        assert cancelled.is_set()
    asyncio.run(check())


if __name__ == "__main__":
    test_long_tool_sequence_finishes_with_evidence_and_usage()
    test_parallel_tool_batch_cannot_exceed_budget()
    test_duplicate_calls_share_inflight_result_and_keep_tool_ids()
    test_consecutive_failures_finish_and_preserve_error_notice()
    test_nonconforming_model_still_cannot_restart_tools()
    test_budget_and_cache_are_isolated_between_turns()
    test_plain_answer_does_not_add_a_model_call()
    test_duplicate_image_requests_create_one_artifact()
    test_cancelling_turn_cancels_inflight_tool()
