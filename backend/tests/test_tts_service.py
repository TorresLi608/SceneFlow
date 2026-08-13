import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.config_service import normalize_config_payload
from app.services.tts_service import _duration, _openai_tts, _qwen_tts, _system_tts, synthesize


def test_system_audio_config_needs_no_api_key() -> None:
    config = normalize_config_payload({"purpose": "audio", "provider": "system", "modelSeries": "Tingting", "apiKey": ""})
    assert config["provider"] == "system"
    assert config["model"] == "Tingting"

    edge = normalize_config_payload({"purpose": "audio", "provider": "edge", "modelSeries": "zh-CN-XiaoxiaoNeural", "apiKey": ""})
    assert edge["provider"] == "edge"


def test_system_tts_uses_available_binary() -> None:
    with TemporaryDirectory() as directory, patch("app.services.tts_service.shutil.which", side_effect=lambda name: "/usr/bin/say" if name == "say" else None), patch("app.services.tts_service.subprocess.run") as run:
        _system_tts("你好", "Tingting", Path(directory) / "voice.wav")
        assert run.call_args.args[0][0] == "/usr/bin/say"
        assert "Tingting" in run.call_args.args[0]


def test_edge_tts_saves_mp3() -> None:
    communicator = MagicMock()
    communicator.save = AsyncMock()
    with TemporaryDirectory() as directory, patch("app.services.tts_service.edge_tts.Communicate", return_value=communicator), patch("app.services.tts_service._duration", return_value=2.5):
        path = Path(directory) / "voice.mp3"
        actual, duration = asyncio.run(synthesize("你好", {"provider": "edge", "model": "zh-CN-XiaoxiaoNeural"}, path))
        assert actual == path
        assert duration == 2.5
        communicator.save.assert_awaited_once_with(str(path))


def test_openai_tts_requests_wav() -> None:
    response = MagicMock(content=b"wav")
    response.raise_for_status = MagicMock()
    client = AsyncMock()
    client.post.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client
    with TemporaryDirectory() as directory, patch("app.services.tts_service.httpx.AsyncClient", return_value=context):
        path = Path(directory) / "voice.wav"
        asyncio.run(_openai_tts("hello", {"apiKey": "secret", "model": "tts-1", "baseUrl": "https://example.test/v1"}, path))
        assert client.post.call_args.kwargs["json"]["response_format"] == "wav"
        assert path.read_bytes() == b"wav"


def test_duration_uses_ffprobe() -> None:
    result = MagicMock(stdout='{"format":{"duration":"3.25"}}')
    with patch("app.services.tts_service.shutil.which", return_value="/usr/bin/ffprobe"), patch("app.services.tts_service.subprocess.run", return_value=result):
        assert _duration(Path("voice.mp3"), 9) == 3.25


def test_qwen_tts_uses_model_and_voice() -> None:
    response = MagicMock()
    response.json.return_value = {"output": {"audio": {"data": "d2F2"}}}
    response.raise_for_status = MagicMock()
    client = AsyncMock()
    client.post.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client
    with TemporaryDirectory() as directory, patch("app.services.tts_service.httpx.AsyncClient", return_value=context):
        path = Path(directory) / "voice.wav"
        asyncio.run(_qwen_tts("hello", {"apiKey": "secret", "model": "qwen3-tts-flash:Cherry", "baseUrl": "https://example.test/v1"}, path))
        assert client.post.call_args.kwargs["json"] == {"model": "qwen3-tts-flash", "input": {"text": "hello", "voice": "Cherry"}}
        assert path.read_bytes() == b"wav"


if __name__ == "__main__":
    test_system_audio_config_needs_no_api_key()
    test_system_tts_uses_available_binary()
    test_edge_tts_saves_mp3()
    test_openai_tts_requests_wav()
    test_duration_uses_ffprobe()
    test_qwen_tts_uses_model_and_voice()
