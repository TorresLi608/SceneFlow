import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.tts_service import _duration, _system_tts, synthesize


def test_system_tts_uses_available_binary() -> None:
    with TemporaryDirectory() as directory, patch("app.services.tts_service.shutil.which", side_effect=lambda name: "/usr/bin/say" if name == "say" else None), patch("app.services.tts_service.subprocess.run") as run:
        _system_tts("你好", "Tingting", Path(directory) / "voice.wav")
        assert run.call_args.args[0][0] == "/usr/bin/say"
        assert "Tingting" in run.call_args.args[0]


def test_edge_tts_saves_local_audition() -> None:
    communicator = MagicMock()
    communicator.save = AsyncMock()
    with TemporaryDirectory() as directory, patch("app.services.tts_service.edge_tts.Communicate", return_value=communicator), patch("app.services.tts_service._duration", return_value=2.5):
        path = Path(directory) / "voice.mp3"
        actual, duration = asyncio.run(synthesize("你好", {"provider": "edge", "model": "zh-CN-XiaoxiaoNeural"}, path))
        assert actual == path
        assert duration == 2.5
        communicator.save.assert_awaited_once_with(str(path))


def test_duration_uses_ffprobe() -> None:
    result = MagicMock(stdout='{"format":{"duration":"3.25"}}')
    with patch("app.services.tts_service.shutil.which", return_value="/usr/bin/ffprobe"), patch("app.services.tts_service.subprocess.run", return_value=result):
        assert _duration(Path("voice.mp3"), 9) == 3.25


if __name__ == "__main__":
    test_system_tts_uses_available_binary()
    test_edge_tts_saves_local_audition()
    test_duration_uses_ffprobe()
