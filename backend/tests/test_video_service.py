from __future__ import annotations

import base64

from app.services.video_service import VideoSettings, build_doubao_payload, gemini_video_base_url, resolve_video_settings


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


if __name__ == "__main__":
    test_resolution_mapping_and_provider_limits()
    test_doubao_payload_with_and_without_reference()
    test_gemini_video_base_url_does_not_duplicate_api_version()
