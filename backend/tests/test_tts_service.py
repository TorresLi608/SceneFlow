import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.config_service import normalize_config_payload
from app.services.tts_service import _duration, _openai_tts, _qwen_tts, _qwen_tts_sdk, _qwen_vd_tts_realtime, _system_tts, synthesize


def test_system_audio_config_needs_no_api_key() -> None:
    config = normalize_config_payload({"purpose": "audio", "provider": "qwen", "modelSeries": "", "apiKey": "secret"})
    assert config["provider"] == "qwen"
    assert config["model"] == "qwen3-tts-vd-2026-01-26"


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


def test_qwen_native_tts_uses_official_websocket_sdk() -> None:
    synthesizer = MagicMock()
    synthesizer.call.return_value = b"mp3"
    with TemporaryDirectory() as directory, patch("app.services.tts_service.SpeechSynthesizer", return_value=synthesizer) as constructor, patch("app.services.tts_service.dashscope.api_key", "old-key"), patch("app.services.tts_service.dashscope.base_websocket_api_url", "old-url"):
        path = Path(directory) / "voice.wav"
        _qwen_tts_sdk("hello", "new-key", "qwen-audio-3.0-tts-flash", "", path)
        assert path.read_bytes() == b"mp3"
        assert constructor.call_args.kwargs == {"model": "qwen-audio-3.0-tts-flash", "voice": ""}
        synthesizer.call.assert_called_once_with("hello", timeout_millis=15 * 60 * 1000)


def test_qwen_native_tts_passes_supported_generation_options() -> None:
    synthesizer = MagicMock()
    synthesizer.call.return_value = b"mp3"
    options = {
        "format": "MP3_24000HZ_MONO_256KBPS",
        "volume": 70,
        "speech_rate": 1.2,
        "pitch_rate": 0.9,
        "seed": 42,
        "instruction": "warm",
        "language_hints": ["zh"],
    }
    with TemporaryDirectory() as directory, patch("app.services.tts_service.SpeechSynthesizer", return_value=synthesizer) as constructor:
        _qwen_tts_sdk("hello", "new-key", "qwen-audio-3.0-tts-flash", "Cherry", Path(directory) / "voice.mp3", options)
    assert constructor.call_args.kwargs["volume"] == 70
    assert constructor.call_args.kwargs["speech_rate"] == 1.2
    assert constructor.call_args.kwargs["pitch_rate"] == 0.9
    assert constructor.call_args.kwargs["seed"] == 42
    assert constructor.call_args.kwargs["instruction"] == "warm"
    assert constructor.call_args.kwargs["language_hints"] == ["zh"]


def test_qwen_voice_design_uses_realtime_pcm_and_writes_wav() -> None:
    class FakeRealtime:
        def __init__(self, *, callback, **_kwargs):
            self.callback = callback

        def connect(self):
            self.callback.on_open()

        def update_session(self, **kwargs):
            assert kwargs["voice"] == "voice-1"
            assert "instructions" not in kwargs

        def append_text(self, text):
            assert text == "你好"
            self.callback.on_event({"type": "response.audio.delta", "delta": "aGk="})

        def finish(self):
            self.callback.on_event({"type": "response.done"})

        def close(self):
            pass

    with TemporaryDirectory() as directory, patch("app.services.tts_service._RealtimeClient", FakeRealtime), patch("app.services.tts_service.dashscope.api_key", "old-key"), patch("app.services.tts_service.time.sleep"):
        path = Path(directory) / "voice.wav"
        _qwen_vd_tts_realtime("你好", "voice-1", "new-key", path)
        assert path.read_bytes()[0:4] == b"RIFF"
        assert path.read_bytes()[-2:] == b"hi"


if __name__ == "__main__":
    test_system_audio_config_needs_no_api_key()
    test_system_tts_uses_available_binary()
    test_edge_tts_saves_mp3()
    test_openai_tts_requests_wav()
    test_duration_uses_ffprobe()
    test_qwen_tts_uses_model_and_voice()
    test_qwen_native_tts_uses_official_websocket_sdk()
    test_qwen_native_tts_passes_supported_generation_options()
    test_qwen_voice_design_uses_realtime_pcm_and_writes_wav()
