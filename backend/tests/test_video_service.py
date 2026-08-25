from __future__ import annotations

import base64
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.generation_service import _generate_scene_video
from app.services.video_service import GENERATION_TIMEOUT_SECONDS, VideoResult, VideoSettings, _generate_doubao_video_sdk, _generate_qwen_video, build_doubao_payload, gemini_video_base_url, is_native_qwen_video_url, qwen_media_policy_model, resolve_qwen_video_quality, resolve_video_options, resolve_video_settings, supported_video_defaults, validate_video_inputs


REFERENCE = {"name": "first.png", "data": "data:image/png;base64," + base64.b64encode(b"image").decode("ascii")}


def assert_raises(message: str, callback) -> None:
    try:
        callback()
    except ValueError as exc:
        assert message in str(exc)
    else:
        raise AssertionError(f"expected ValueError containing {message!r}")


def test_aspect_ratio_mapping_and_provider_limits() -> None:
    assert resolve_video_settings("doubao", "1280x720") == VideoSettings("720p", "16:9")
    assert resolve_video_settings("doubao", "720x1280") == VideoSettings("720p", "9:16")
    assert resolve_video_settings("doubao", "1920x1080") == VideoSettings("1080p", "16:9")
    assert_raises("only supported for Doubao and Gemini", lambda: resolve_video_settings("qwen", "1280x720"))
    assert_raises("1:1", lambda: resolve_video_settings("gemini", "1024x1024"))
    assert resolve_qwen_video_quality("480P") == "480p"
    assert resolve_qwen_video_quality("1080p") == "1080p"
    assert resolve_qwen_video_quality("4k") == "4k"
    assert_raises("480p, 720p, 1080p, 2K, or 4K", lambda: resolve_qwen_video_quality("8k"))


def test_doubao_payload_with_and_without_reference() -> None:
    settings = VideoSettings("720p", "16:9")
    text_payload = build_doubao_payload("seedance", "camera move", settings, None, 24, 5)
    assert text_payload["content"] == [{"type": "text", "text": "camera move"}]
    assert text_payload["resolution"] == "720p"
    assert text_payload["ratio"] == "16:9"
    assert text_payload["duration"] == 5
    assert text_payload["fps"] == 24

    image_payload = build_doubao_payload("seedance", "camera move", settings, "1080p", 24, 5, REFERENCE)
    assert len(image_payload["content"]) == 2
    assert image_payload["content"][1]["role"] == "first_frame"
    assert image_payload["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert image_payload["resolution"] == "1080p"


def test_gemini_video_base_url_does_not_duplicate_api_version() -> None:
    assert gemini_video_base_url("https://generativelanguage.googleapis.com/v1beta") == "https://generativelanguage.googleapis.com"
    assert gemini_video_base_url("https://generativelanguage.googleapis.com/v1beta/openai") == "https://generativelanguage.googleapis.com"


def test_doubao_sdk_uses_configured_relay() -> None:
    created = SimpleNamespace(id="task-1")
    completed = SimpleNamespace(status="succeeded", content=SimpleNamespace(video_url="https://video.test/result.mp4"))

    class Tasks:
        def create(self, **kwargs):
            self.request = kwargs
            return created

        def get(self, **kwargs):
            assert kwargs == {"task_id": "task-1"}
            return completed

    class Client:
        instances = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.content_generation = SimpleNamespace(tasks=Tasks())
            self.instances.append(self)

    video = SimpleNamespace(content=b"mp4", raise_for_status=lambda: None)
    client = AsyncMock()
    client.get.return_value = video
    context = AsyncMock()
    context.__aenter__.return_value = client
    with (
        patch.dict(sys.modules, {"volcenginesdkarkruntime": SimpleNamespace(Ark=Client)}),
        patch("app.services.video_service.httpx.AsyncClient", return_value=context),
        patch("app.services.video_service.asyncio.sleep", new=AsyncMock()),
    ):
        result = asyncio.run(_generate_doubao_video_sdk("key", "doubao-seedance-2.0", "move", VideoSettings("720p", "16:9"), None, 24, 5, None, "https://relay.example.com/api/v3"))

    assert result.data == b"mp4"
    assert Client.instances[0].kwargs["base_url"] == "https://relay.example.com/api/v3"
    assert Client.instances[0].content_generation.tasks.request["model"] == "doubao-seedance-2.0"
    assert "fps" not in Client.instances[0].content_generation.tasks.request


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
        result = asyncio.run(_generate_qwen_video("test-key", "wan2.7-i2v", "camera move", "480p", 5, False, [REFERENCE], None, None, "https://relay.example.com/api/v1", "9:16"))

    assert result.data == b"mp4"
    request = client.post.call_args.kwargs
    assert request["json"]["input"]["media"][0]["type"] == "first_frame"
    assert request["json"]["input"]["media"][0]["url"].startswith("data:image/png;base64,")
    assert request["json"]["parameters"]["resolution"] == "480P"
    assert request["json"]["parameters"]["ratio"] == "9:16"
    assert request["json"]["parameters"]["prompt_extend"] is False
    assert "fps" not in request["json"]["parameters"]


def test_qwen_video_model_matches_input_type() -> None:
    for model, references, message in (
        ("wan2.7-i2v", [], "requires a reference image"),
        ("wan2.7-t2v", [REFERENCE], "does not accept a reference image"),
    ):
        try:
            asyncio.run(_generate_qwen_video("test-key", model, "camera move", "720p", 5, True, references, None, None, ""))
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"expected {model} input validation to fail")


def test_qwen_native_video_uploads_media_to_temporary_oss() -> None:
    created = SimpleNamespace(output={"task_id": "task-1"})
    task = SimpleNamespace(output={"task_status": "SUCCEEDED", "video_url": "https://video.test/result.mp4"})
    video = SimpleNamespace(content=b"mp4", raise_for_status=lambda: None)
    client = AsyncMock()
    client.get.return_value = video
    context = AsyncMock()
    context.__aenter__.return_value = client
    submit = MagicMock(return_value=created)
    wait = MagicMock(return_value=task)
    upload = MagicMock(return_value=("oss://temp/frame.png", {}))
    with (
        patch("app.services.video_service.OssUtils.upload", upload),
        patch("app.services.video_service.VideoSynthesis.async_call", new=submit),
        patch("app.services.video_service.VideoSynthesis.wait", new=wait),
        patch("app.services.video_service.httpx.AsyncClient", return_value=context),
    ):
        result = asyncio.run(_generate_qwen_video("test-key", "wan2.7-i2v", "camera move", "720p", 5, True, [REFERENCE], None, None, "https://dashscope.aliyuncs.com/api/v1", "16:9"))

    assert result.data == b"mp4"
    assert upload.call_args.kwargs["model"] == "wan2.6-i2v"
    request = submit.call_args.kwargs
    assert request["base_address"] == "https://dashscope.aliyuncs.com/api/v1"
    assert request["ratio"] == "16:9"
    assert request["extra_input"]["media"] == [{"type": "first_frame", "url": "oss://temp/frame.png"}]
    wait.assert_called_once_with(created, api_key="test-key", wait_timeout=GENERATION_TIMEOUT_SECONDS)


def test_qwen_media_policy_uses_supported_upload_model() -> None:
    assert qwen_media_policy_model("wan2.5-i2v") == "wan2.6-i2v"
    assert qwen_media_policy_model("wan2.7-i2v") == "wan2.6-i2v"
    assert qwen_media_policy_model("wan2.7-r2v") == "wan2.6-r2v"
    assert qwen_media_policy_model("wan2.7-t2v") == "wan2.7-t2v"


def test_video_options_follow_model_capabilities() -> None:
    capabilities = {
        "qualities": ["480p", "720p"],
        "fps": [],
        "aspectRatios": ["16:9", "adaptive"],
        "promptExtend": True,
        "minDuration": 3,
        "maxDuration": 10,
    }
    assert resolve_video_options({"quality": "720p", "aspectRatio": "adaptive", "duration": 3, "promptExtend": True}, capabilities) == (
        "720p", "adaptive", None, 3, True
    )
    assert_raises("between 3 and 10", lambda: resolve_video_options({"duration": 11}, capabilities))
    assert_raises("does not support fps", lambda: resolve_video_options({"fps": 24}, capabilities))


def test_saved_video_defaults_drop_options_unsupported_by_a_new_model() -> None:
    capabilities = {
        "qualities": ["720p"],
        "fps": [],
        "aspectRatios": [],
        "promptExtend": False,
        "minDuration": 3,
        "maxDuration": 5,
    }
    saved = {
        "quality": "1080p",
        "aspectRatio": "9:16",
        "fps": 30,
        "duration": 10,
        "promptExtend": True,
    }

    assert supported_video_defaults(saved, capabilities) == {}
    assert resolve_video_options(supported_video_defaults(saved, capabilities), capabilities) == ("720p", None, None, 3, False)


def test_video_media_capabilities_are_enforced() -> None:
    capabilities = {
        "referenceImages": True,
        "referenceImagesRequired": True,
        "maxReferenceImages": 1,
        "referenceVideo": False,
        "maxReferenceVideos": 0,
        "referenceVideosRequired": False,
        "referenceAudio": False,
        "maxReferenceAudios": 0,
        "referenceAudiosRequired": False,
    }
    assert_raises("requires a reference image", lambda: validate_video_inputs(capabilities, [], None, None))
    assert_raises("at most 1", lambda: validate_video_inputs(capabilities, [REFERENCE, REFERENCE], None, None))
    validate_video_inputs(capabilities, [REFERENCE], None, None)


def test_qwen_native_url_detection_keeps_relays_configurable() -> None:
    assert is_native_qwen_video_url("https://dashscope.aliyuncs.com/api/v1")
    assert not is_native_qwen_video_url("https://relay.example.com/api/v1")


def _render_scene_video(options: dict, media: list[dict], max_images: int = 1):
    """Drive one scene render with the providers stubbed, and hand back the request made."""
    config = {
        "provider": "qwen", "apiKey": "secret", "model": "wan2.7-i2v", "baseUrl": "https://relay.example.com/api/v1",
        "videoCapabilities": {
            "referenceImages": True,
            "maxReferenceImages": max_images,
            "referenceImagesRequired": True,
            "referenceAudio": True,
        },
    }
    scene = {"id": "scene-1", "order_num": 1, "visual_prompt": "camera move", "image_path": "frame.png", "characters": []}
    generate = AsyncMock(return_value=VideoResult(b"mp4"))
    with (
        patch("app.services.generation_service._stored_media", side_effect=media),
        patch("app.services.generation_service.generate_video", new=generate),
        patch("app.services.generation_service.db", return_value=MagicMock()),
        patch("app.services.generation_service.require_model_balance"),
        patch("app.services.generation_service.record_usage"),
        patch("app.services.generation_service.store_artifact", return_value="projects/p/scene-1.mp4"),
        patch("app.services.generation_service.signed_url_for_stored", return_value="/api/files/video"),
        patch("app.services.generation_service.update_scene_row"),
        patch("app.services.generation_service.scene_event", new=AsyncMock()),
    ):
        succeeded = asyncio.run(_generate_scene_video("p", scene, config, 1, options))
    return succeeded, generate.call_args.kwargs


def test_storyboard_video_passes_scene_media_and_capabilities() -> None:
    image = {"name": "frame.png", "data": "data:image/png;base64,aW1hZ2U="}
    voices = {"name": "voices.mp3", "data": "data:audio/mpeg;base64,YXVkaW8="}

    succeeded, request = _render_scene_video(
        {"quality": "720p", "aspectRatio": None, "fps": None, "duration": 5, "promptExtend": True,
         "voiceSheetPath": "voices/p/voices.mp3"},
        [image, voices],
    )

    assert succeeded
    assert request["references"] == [image]
    assert request["reference_audios"] == [voices]
    assert request["quality"] == "720p"
    assert request["prompt_extend"] is True


def test_a_render_without_audio_sends_none() -> None:
    image = {"name": "frame.png", "data": "data:image/png;base64,aW1hZ2U="}

    succeeded, request = _render_scene_video(
        {"quality": "720p", "aspectRatio": None, "fps": None, "duration": 5, "promptExtend": False,
         "voiceSheetPath": None},
        [image],
    )

    assert succeeded
    assert request["reference_audios"] == []


def test_selected_video_references_replace_automatic_character_media() -> None:
    frame = {"name": "frame.png", "data": "data:image/png;base64,ZnJhbWU="}
    image = {"name": "prop.png", "data": "data:image/png;base64,cHJvcA=="}
    video = {"name": "clip.mp4", "data": "data:video/mp4;base64,dmlkZW8="}
    audio = {"name": "voice.mp3", "data": "data:audio/mpeg;base64,YXVkaW8="}

    succeeded, request = _render_scene_video(
        {
            "quality": "720p", "aspectRatio": None, "fps": None, "duration": 5, "promptExtend": False,
            "voiceSheetPath": None, "explicitReferences": True,
            "referenceImagePaths": ["props/p.png"], "referenceVideoPaths": ["videos/v.mp4"],
            "referenceAudioPaths": ["voices/a.mp3"],
        },
        [frame, image, video, audio],
        max_images=2,
    )

    assert succeeded
    assert request["references"] == [frame, image]
    assert request["reference_videos"] == [video]
    assert request["reference_audios"] == [audio]


if __name__ == "__main__":
    test_aspect_ratio_mapping_and_provider_limits()
    test_doubao_payload_with_and_without_reference()
    test_gemini_video_base_url_does_not_duplicate_api_version()
    test_qwen_video_uses_reference_frame_and_async_task()
    test_qwen_video_model_matches_input_type()
    test_qwen_native_video_uploads_media_to_temporary_oss()
    test_qwen_media_policy_uses_supported_upload_model()
    test_video_options_follow_model_capabilities()
    test_saved_video_defaults_drop_options_unsupported_by_a_new_model()
    test_video_media_capabilities_are_enforced()
    test_qwen_native_url_detection_keeps_relays_configurable()
    test_storyboard_video_passes_scene_media_and_capabilities()
    test_a_render_without_audio_sends_none()
    test_selected_video_references_replace_automatic_character_media()
