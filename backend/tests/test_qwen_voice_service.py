import asyncio
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.api.v1.audio import generate_audio
from app.models import UserVoice
from app.services.config_service import QWEN_VD_MODEL
from app.services.qwen_voice_service import create_voice


def test_voice_design_uses_customization_endpoint_and_preview_audio() -> None:
    response = MagicMock()
    response.json.return_value = {"output": {"voice": "announcer", "preview_audio": {"data": "d2F2"}}}
    with patch("app.services.qwen_voice_service.httpx.post", return_value=response) as post:
        voice_id, audio = create_voice(
            {"apiKey": "secret", "baseUrl": "https://dashscope.aliyuncs.com/api/v1"},
            "沉稳的播音员",
            "各位听众朋友，大家好。",
            "announcer",
        )

    assert post.call_args.args[0].endswith("/services/audio/tts/customization")
    assert post.call_args.kwargs["json"] == {
        "model": "qwen-voice-design",
        "input": {
            "action": "create",
            "target_model": QWEN_VD_MODEL,
            "preferred_name": "announcer",
            "voice_prompt": "沉稳的播音员",
            "preview_text": "各位听众朋友，大家好。",
            "language": "zh",
        },
        "parameters": {"sample_rate": 24000, "response_format": "wav"},
    }
    assert voice_id == "announcer"
    assert audio == b"wav"


def test_audio_generation_resolves_saved_voice_id() -> None:
    session = MagicMock()
    session.exec.return_value.first.return_value = UserVoice(
        id="user-voice_1",
        user_id=7,
        voice_id="qwen-provider-voice-id",
        is_saved=True,
    )

    @contextmanager
    def fake_db():
        yield session

    async def fake_synthesize(_text: str, config: dict[str, str], output: Path, _options):
        assert config["voice"] == "qwen-provider-voice-id"
        output.write_bytes(b"wav")
        return output, 1.0

    config = {"provider": "qwen", "model": QWEN_VD_MODEL, "apiKey": "secret", "baseUrl": ""}
    with (
        patch("app.api.v1.audio.db", fake_db),
        patch("app.api.v1.audio.official_model_config", return_value=config),
        patch("app.api.v1.audio.require_model_balance"),
        patch("app.api.v1.audio.synthesize", side_effect=fake_synthesize),
        patch("app.api.v1.audio.save_binary_artifact", return_value="/audio.wav"),
        patch("app.api.v1.audio.record_usage"),
    ):
        result = asyncio.run(
            generate_audio(
                {"text": "今晚打老虎", "voice": "user-voice_1", "officialConfigId": 12},
                user_id=7,
            )
        )

    assert result["audio"]["voice"] == "user-voice_1"


if __name__ == "__main__":
    test_voice_design_uses_customization_endpoint_and_preview_audio()
    test_audio_generation_resolves_saved_voice_id()
