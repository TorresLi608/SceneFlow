from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.services import agent_service, artifact_service
from app.llms.router import ModelRouter, _content_text, _reasoning_text


class ToolFakeModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


async def _run() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original_dir = artifact_service.PRIVATE_GENERATED_DIR
        original_agent = agent_service._agent
        artifact_service.PRIVATE_GENERATED_DIR = Path(directory)
        model = ToolFakeModel(
            disable_streaming=True,
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "generate_pdf",
                            "args": {"title": "测试文档", "content": "# 摘要\nAgent 工具循环正常。"},
                            "id": "call_1",
                        }
                    ],
                ),
                AIMessage(content="文档已经生成。"),
            ],
        )
        fake_agent = create_agent(model=model, tools=agent_service.create_chat_tools("chat_test", None))
        agent_service._agent = lambda *args, **kwargs: fake_agent
        try:
            events = [
                event
                async for event in agent_service.stream_chat_agent(
                    {"provider": "openai", "apiKey": "test", "model": "fake", "baseUrl": ""},
                    "chat_test",
                    [{"role": "user", "content": "生成一个测试 PDF"}],
                    None,
                )
            ]
        finally:
            agent_service._agent = original_agent
            artifact_service.PRIVATE_GENERATED_DIR = original_dir

    assert any(event["type"] == "agent_step" and event["step"]["label"] == "生成 PDF" for event in events)
    assert any(event["type"] == "content_delta" and "下载 PDF" in event["content"] for event in events)
    assert "下载 PDF" in events[-1]["content"]


def test_agent_tool_loop() -> None:
    asyncio.run(_run())


def test_reasoning_blocks_are_separate_from_answer() -> None:
    content = [
        {"type": "thinking", "thinking": "先分析"},
        {"type": "text", "text": "最终答案"},
        {"type": "reasoning", "text": "再验证"},
    ]

    assert _content_text(content) == "最终答案"
    assert _reasoning_text(content, {"reasoning_content": "准备："}) == "准备：先分析再验证"


def test_openai_compatible_streams_report_usage() -> None:
    model = ModelRouter().chat_model("gemini", "test-key", "gemini-test")
    assert model.stream_usage is True


if __name__ == "__main__":
    test_agent_tool_loop()
    test_reasoning_blocks_are_separate_from_answer()
    test_openai_compatible_streams_report_usage()
