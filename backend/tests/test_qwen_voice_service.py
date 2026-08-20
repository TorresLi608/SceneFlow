from unittest.mock import MagicMock, patch

from app.services.qwen_voice_service import create_voice


def test_voice_design_uses_configured_target_model_and_preview_audio() -> None:
    response = MagicMock()
    response.json.return_value = {"output": {"voice": "announcer", "preview_audio": {"data": "d2F2"}}}
    with patch("app.services.qwen_voice_service.httpx.post", return_value=response) as post:
        voice_id, audio = create_voice(
            {
                "apiKey": "secret",
                "baseUrl": "https://dashscope.aliyuncs.com/api/v1",
                "model": "qwen3-tts-vd-2026-01-26",
            },
            "沉稳的播音员",
            "各位听众朋友，大家好。",
            "announcer",
        )

    assert post.call_args.args[0].endswith("/services/audio/tts/customization")
    assert post.call_args.kwargs["json"] == {
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


if __name__ == "__main__":
    test_voice_design_uses_configured_target_model_and_preview_audio()
