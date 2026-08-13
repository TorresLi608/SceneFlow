from __future__ import annotations

import base64
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.video_service import VideoSettings, _generate_qwen_video, build_doubao_payload, gemini_video_base_url, resolve_video_settings


REFERENCE = {"name": "first.png", "data": "data:image/png;base64," + base64.b64encode(b"image").decode("ascii")}


def assert_raises(message: str, callback) -> None:
    try:
        callback()
    except ValueError as exc:
        assert message in str(exc)
    else:
        raise AssertionError(f"expected ValueError containing {message!r}")


def test_resolution_mapping_and_provider_limits() -> None:
    assert resolve_video_settings("doubao", "1280x720", 24, 4) == VideoSettings("720p", "16:9")
    assert resolve_video_settings("doubao", "720x1280", 24, 15) == VideoSettings("720p", "9:16")
    assert resolve_video_settings("doubao", "1920x1080", 24, 8) == VideoSettings("1080p", "16:9")
    assert_raises("24 FPS", lambda: resolve_video_settings("gemini", "1280x720", 30, 4))
    assert_raises("1:1", lambda: resolve_video_settings("gemini", "1024x1024", 24, 4))
    assert_raises("between 4 and 15", lambda: resolve_video_settings("doubao", "1280x720", 24, 16))


def test_doubao_payload_with_and_without_reference() -> None:
    settings = VideoSettings("720p", "16:9")
    text_payload = build_doubao_payload("seedance", "camera move", settings, 5)
    assert text_payload["content"] == [{"type": "text", "text": "camera move"}]
    assert text_payload["resolution"] == "720p"
    assert text_payload["ratio"] == "16:9"
    assert text_payload["duration"] == 5

    image_payload = build_doubao_payload("seedance", "camera move", settings, 5, REFERENCE)
    assert len(image_payload["content"]) == 2
    assert image_payload["content"][1]["role"] == "first_frame"
    assert image_payload["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_gemini_video_base_url_does_not_duplicate_api_version() -> None:
    assert gemini_video_base_url("https://generativelanguage.googleapis.com/v1beta") == "https://generativelanguage.googleapis.com"
    assert gemini_video_base_url("https://generativelanguage.googleapis.com/v1beta/openai") == "https://generativelanguage.googleapis.com"


def test_qwen_video_uses_reference_frame_and_async_task() -> None:
    response = SimpleNamespace(json=lambda: {"output": {"task_id": "task-1"}}, raise_for_status=lambda: None)
    task = SimpleNamespace(json=lambda: {"output": {"task_status": "SUCCEEDED", "video_url": "https://video.test/result.mp4"}}, raise_for_status=lambda: None)
    video = SimpleNamespace(content=b"mp4", raise_for_status=lambda: None)
    client = AsyncMock()
    client.post.return_value = response
    client.get.side_effect = [task, video]
    context = AsyncMock()
    context.__aenter__.return_value = client
    with patch("app.services.video_service.httpx.AsyncClient", return_value=context), patch("app.services.video_service.asyncio.sleep", new=AsyncMock()):
        result = asyncio.run(_generate_qwen_video("test-key", "wan2.7-i2v", "camera move", VideoSettings("720p", "16:9"), 5, REFERENCE, ""))

    assert result.data == b"mp4"
    request = client.post.call_args.kwargs
    assert request["json"]["input"]["media"][0]["type"] == "first_frame"
    assert request["json"]["input"]["media"][0]["url"].startswith("data:image/png;base64,")
    assert request["json"]["parameters"]["resolution"] == "720P"
    assert "ratio" not in request["json"]["parameters"]


def test_qwen_video_model_matches_input_type() -> None:
    settings = VideoSettings("720p", "16:9")
    for model, reference, message in (
        ("wan2.7-i2v", None, "requires a reference image"),
        ("wan2.7-t2v", REFERENCE, "does not accept a reference image"),
    ):
        try:
            asyncio.run(_generate_qwen_video("test-key", model, "camera move", settings, 5, reference, ""))
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"expected {model} input validation to fail")


if __name__ == "__main__":
    test_resolution_mapping_and_provider_limits()
    test_doubao_payload_with_and_without_reference()
    test_gemini_video_base_url_does_not_duplicate_api_version()
    test_qwen_video_uses_reference_frame_and_async_task()
    test_qwen_video_model_matches_input_type()
