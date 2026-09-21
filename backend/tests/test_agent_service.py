from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.services import agent_service, artifact_service
from app.llms.router import ChatGoogleGenerativeAI, ModelRouter, _content_text, _json_object, _reasoning_text


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


def test_image_tool_reconciles_broken_model_copied_url_without_duplicate() -> None:
    from app.llms.router import ImageResult

    generate = AsyncMock(return_value=ImageResult(data=b"\x89PNG fake", format="png"))
    events = asyncio.run(
        _run_image_tool(
            {"provider": "openai", "apiKey": "k", "model": "img", "baseUrl": ""},
            "为你画好了：\n\n![橘猫](http://127.0.0.1:8080/api/chat/artifacts/broken-token)",
            generate=generate,
        )
    )

    final = events[-1]["content"]
    assert "broken-token" not in final
    assert "/api/chat/artifacts/" in final
    # 确保没有重复生成两张图片
    assert final.count("![橘猫](") == 1


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
    model = ModelRouter().chat_model("qwen", "test-key", "qwen-test")
    assert model.stream_usage is True
    gemini_model = ModelRouter().chat_model("gemini", "test-key", "gemini-3.6-flash")
    assert isinstance(gemini_model, ChatGoogleGenerativeAI)


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


def test_web_search_tool_unconfigured_skips_registration() -> None:
    from app.core import config

    with patch.object(config, "SEARXNG_BASE_URL", ""):
        tools = agent_service.create_chat_tools("chat_test", None)
        tool_names = [t.name for t in tools]
        assert "web_search" not in tool_names


def test_web_search_tool_configured_and_executes() -> None:
    from app.core import config
    from unittest.mock import patch

    async def _test():
        with (
            patch.object(config, "SEARXNG_BASE_URL", "http://searxng.test:8080"),
            patch(
                "app.services.agent_service.search_searxng",
                AsyncMock(return_value="### 网页搜索结果（关键词：SceneFlow 资讯）\n\n1. [SceneFlow 发布](https://example.com)\n   最新 AI 生剧工作流上线。"),
            ),
        ):
            tools = agent_service.create_chat_tools("chat_test", None)
            tool_names = [t.name for t in tools]
            assert "web_search" in tool_names

            model = ToolFakeModel(
                disable_streaming=True,
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "web_search",
                                "args": {"query": "SceneFlow 资讯"},
                                "id": "call_search_1",
                            }
                        ],
                    ),
                    AIMessage(content="据搜索，最新 AI 生剧工作流已上线 [SceneFlow 发布](https://example.com)。"),
                ],
            )
            fake_agent = create_agent(model=model, tools=tools)
            original_agent = agent_service._agent
            agent_service._agent = lambda *args, **kwargs: fake_agent
            try:
                events = [
                    event
                    async for event in agent_service.stream_chat_agent(
                        {"provider": "openai", "apiKey": "test", "model": "fake", "baseUrl": ""},
                        "chat_test",
                        [{"role": "user", "content": "帮我搜索 SceneFlow 资讯"}],
                        None,
                    )
                ]
            finally:
                agent_service._agent = original_agent

            search_steps = [
                e["step"] for e in events if e["type"] == "agent_step" and e["step"]["label"] == "网络搜索"
            ]
            assert len(search_steps) >= 2
            assert search_steps[0]["status"] == "running"
            assert search_steps[0]["detail"] == "检索「SceneFlow 资讯」"
            assert search_steps[1]["status"] == "done"
            assert search_steps[1]["detail"] == "检索完成"

    asyncio.run(_test())


def test_agent_system_prompt_temporal_and_search_optimization() -> None:
    with patch("app.services.agent_service.is_searxng_configured", return_value=True):
        prompt = agent_service._agent_system_prompt()
        assert "当前现实世界日期" in prompt
        assert "意图与时间分析" in prompt
        assert "搜索词优化重写" in prompt
        assert "严禁包含问号" in prompt


def test_final_answer_does_not_leak_prior_turn_messages() -> None:
    # 模拟包含两轮历史和一个新用户提问的状态
    # 历史: Human(0), AI(1), Human(2), AI(3)
    # 本轮: Human(4), AI(5, content="")
    output = {
        "messages": [
            HumanMessage(content="成都天气如何"),
            AIMessage(content="今天成都多云转阵雨"),
            HumanMessage(content="10月份穿什么衣服"),
            AIMessage(content="如果10月去成都旅游建议穿外套"),
            HumanMessage(content="牛逼"),
            AIMessage(content=""),
        ]
    }
    # 基础消息数为 5（前4条历史+第5条新提问）
    base_count = 5
    # 验证在新消息为空时，_final_answer 绝对不会往回翻出第 3 条消息的穿衣指南
    answer = agent_service._final_answer(output, base_count=base_count)
    assert answer == "", f"Expected empty answer, got: {answer}"

    # 验证如果有新内容，能正确提取新内容
    output["messages"][-1] = AIMessage(content="哈哈，能帮上忙就好！")
    new_answer = agent_service._final_answer(output, base_count=base_count)
    assert new_answer == "哈哈，能帮上忙就好！"


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
    test_web_search_tool_unconfigured_skips_registration()
    test_web_search_tool_configured_and_executes()
    test_agent_system_prompt_temporal_and_search_optimization()
    test_final_answer_does_not_leak_prior_turn_messages()


