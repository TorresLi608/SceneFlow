from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.services import agent_service, artifact_service
from app.llms.router import ModelRouter, _content_text, _json_object, _reasoning_text


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


async def _run_image_tool(image_config, final_reply: str, *, generate=None) -> list[dict]:
    """Drive one image-tool turn with a fake chat model and a stubbed image provider."""
    with tempfile.TemporaryDirectory() as directory:
        original_dir = artifact_service.PRIVATE_GENERATED_DIR
        original_agent = agent_service._agent
        original_generate = agent_service.models.generate_image
        artifact_service.PRIVATE_GENERATED_DIR = Path(directory)
        if generate is not None:
            agent_service.models.generate_image = generate
        model = ToolFakeModel(
            disable_streaming=True,
            responses=[
                AIMessage(content="", tool_calls=[{"name": "generate_image", "args": {"prompt": "一只橘猫", "title": "橘猫"}, "id": "call_img"}]),
                AIMessage(content=final_reply),
            ],
        )
        fake_agent = create_agent(model=model, tools=agent_service.create_chat_tools("chat_image", image_config))
        agent_service._agent = lambda *args, **kwargs: fake_agent
        try:
            return [
                event
                async for event in agent_service.stream_chat_agent(
                    {"provider": "openai", "apiKey": "test", "model": "fake", "baseUrl": ""},
                    "chat_image",
                    [{"role": "user", "content": "画一只橘猫"}],
                    image_config,
                )
            ]
        finally:
            agent_service._agent = original_agent
            agent_service.models.generate_image = original_generate
            artifact_service.PRIVATE_GENERATED_DIR = original_dir


def test_image_tool_result_reaches_the_reply_without_leaking_the_url_into_steps() -> None:
    from app.llms.router import ImageResult

    generate = AsyncMock(return_value=ImageResult(data=b"\x89PNG fake", format="png"))
    events = asyncio.run(_run_image_tool({"provider": "openai", "apiKey": "k", "model": "img", "baseUrl": ""}, "图片已经生成。", generate=generate))

    done_steps = [event["step"] for event in events if event["type"] == "agent_step" and event["step"]["label"] == "生成图片" and event["step"]["status"] == "done"]
    assert done_steps and done_steps[0]["detail"] == "橘猫.png"
    assert not any("/api/chat/artifacts/" in (event["step"].get("detail") or "") for event in events if event["type"] == "agent_step")
    final = events[-1]["content"]
    assert final.startswith("图片已经生成。")
    assert "![橘猫](" in final and "/api/chat/artifacts/" in final
    assert any(event["type"] == "content_delta" and "![橘猫](" in event["content"] for event in events)


def test_failed_image_tool_marks_the_step_and_adds_a_notice_to_the_reply() -> None:
    events = asyncio.run(_run_image_tool(None, "抱歉，暂时无法生成图片。"))

    error_steps = [event["step"] for event in events if event["type"] == "agent_step" and event["step"]["label"] == "生成图片" and event["step"]["status"] == "error"]
    assert error_steps and "尚未配置图片生成模型" in error_steps[0]["detail"]
    assert not any(event["type"] == "agent_step" and event["step"]["label"] == "生成图片" and event["step"]["status"] == "done" for event in events)
    final = events[-1]["content"]
    assert final.startswith("抱歉，暂时无法生成图片。")
    assert "> ⚠️ 图片生成失败：尚未配置图片生成模型" in final
    assert "![" not in final


def test_failed_image_tool_with_an_empty_model_reply_still_produces_content() -> None:
    events = asyncio.run(_run_image_tool(None, ""))

    assert events[-1]["content"].startswith("> ⚠️ 图片生成失败：")
    assert any(event["type"] == "content_delta" and event["content"].startswith("> ⚠️ 图片生成失败：") for event in events)


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


def test_openai_compatible_breakdown_skips_the_openai_beta_parser() -> None:
    router = ModelRouter()
    model = MagicMock()
    model.ainvoke = AsyncMock(
        return_value=AIMessage(content='{"shots":[{"narration":"雾中山门","visualPrompt":"wide shot"}]}')
    )
    router.chat_model = MagicMock(return_value=model)
    result = asyncio.run(router.breakdown_script("qwen", "test-key", "qwen-test", "system", "script"))
    assert result.shots[0].narration == "雾中山门"


def test_breakdown_disables_stream_usage_for_compatibility_gateways() -> None:
    # Direct provider calls intentionally do not use LangChain streaming.
    assert ModelRouter().chat_model("qwen", "test-key", "qwen-test", stream_usage=False).stream_usage is False


def test_json_object_ignores_wrappers_and_trailing_model_text() -> None:
    payload = _json_object(
        '结果如下：\n```json\n{"shots":[{"narration":"雾中山门"}]}\n```\n补充说明：已完成。'
    )
    assert payload["shots"][0]["narration"] == "雾中山门"
    assert _json_object('{"shots": []}\n{"extra": true}') == {"shots": []}
    assert _json_object(r'{\"scenes\": []}') == {"scenes": []}


def test_breakdown_payload_accepts_a_bare_shot_array() -> None:
    from app.llms.router import _json_breakdown_payload

    assert _json_breakdown_payload('[{"narration":"雾中山门"}]')["shots"][0]["narration"] == "雾中山门"


def test_breakdown_payload_accepts_escaped_quotes_from_model() -> None:
    from app.llms.router import _json_breakdown_payload

    payload = _json_breakdown_payload(r'[{\"narration\": \"深夜，韩立躺在床上\", \"dialogue\": \"他说：\\\"别出声。\\\"\"}]')
    assert payload["shots"][0]["narration"].startswith("深夜")
    assert payload["shots"][0]["dialogue"] == '他说："别出声。"'


def test_breakdown_payload_accepts_twice_escaped_quotes_from_model() -> None:
    from app.llms.router import _json_breakdown_payload

    payload = _json_breakdown_payload(r'[{\\\"narration\\\": \\\"深夜，韩立躺在床上\\\"}]')
    assert payload["shots"][0]["narration"].startswith("深夜")


def test_breakdown_payload_recovers_complete_shots_from_a_truncated_array() -> None:
    from app.llms.router import _json_breakdown_payload

    payload = _json_breakdown_payload('[{"narration":"第一镜","visualPrompt":"山门"},{"narration":"未完成')
    assert payload["shots"] == [{"narration": "第一镜", "visualPrompt": "山门"}]


if __name__ == "__main__":
    test_agent_tool_loop()
    test_reasoning_blocks_are_separate_from_answer()
    test_openai_compatible_streams_report_usage()
    test_openai_compatible_breakdown_skips_the_openai_beta_parser()
    test_breakdown_disables_stream_usage_for_compatibility_gateways()
    test_json_object_ignores_wrappers_and_trailing_model_text()
    test_breakdown_payload_accepts_a_bare_shot_array()
    test_breakdown_payload_accepts_escaped_quotes_from_model()
    test_breakdown_payload_accepts_twice_escaped_quotes_from_model()
    test_breakdown_payload_recovers_complete_shots_from_a_truncated_array()
