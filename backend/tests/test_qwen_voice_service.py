import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.qwen_voice_service import create_voice


def test_voice_design_uses_configured_target_model_and_preview_audio() -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"output": {"voice": "announcer", "preview_audio": {"data": "d2F2"}}}
    # Async now, so a client disconnect actually cancels the request: the design call can
    # take minutes, and the blocking version ignored the user's stop button entirely.
    client = AsyncMock()
    client.post.return_value = response
    client.__aenter__.return_value = client
    with patch("app.services.qwen_voice_service.httpx.AsyncClient", return_value=client):
        voice_id, audio = asyncio.run(
            create_voice(
                {
                    "apiKey": "secret",
                    "baseUrl": "https://dashscope.aliyuncs.com/api/v1",
                    "model": "qwen3-tts-vd-2026-01-26",
                },
                "沉稳的播音员",
                "各位听众朋友，大家好。",
                "announcer",
            )
        )

    assert client.post.call_args.args[0].endswith("/services/audio/tts/customization")
    assert client.post.call_args.kwargs["json"] == {
        "model": "qwen-voice-design",
        "input": {
            "action": "create",
            "target_model": "qwen3-tts-vd-2026-01-26",
            "preferred_name": "announcer",
            "voice_prompt": "沉稳的播音员",
            "preview_text": "各位听众朋友，大家好。",
            "language": "zh",
        },
        "parameters": {"sample_rate": 24000, "response_format": "wav"},
    }
    assert voice_id == "announcer"
    assert audio == b"wav"


def test_voice_design_falls_back_from_task_model_to_valid_target_model() -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"output": {"voice": "voice_123", "preview_audio": {"data": "d2F2"}}}
    client = AsyncMock()
    client.post.return_value = response
    client.__aenter__.return_value = client
    with patch("app.services.qwen_voice_service.httpx.AsyncClient", return_value=client):
        voice_id, audio = asyncio.run(
            create_voice(
                {
                    "apiKey": "secret",
                    "baseUrl": "https://dashscope.aliyuncs.com/api/v1",
                    "model": "qwen-voice-design",
                },
                "沉稳的声音",
                "测试文本",
                "test",
            )
        )

    assert client.post.call_args.kwargs["json"]["input"]["target_model"] == "qwen3-tts-vd-realtime-2025-12-16"
    assert voice_id == "voice_123"


if __name__ == "__main__":
    test_voice_design_uses_configured_target_model_and_preview_audio()
    test_voice_design_falls_back_from_task_model_to_valid_target_model()

