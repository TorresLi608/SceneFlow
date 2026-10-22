from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import AsyncMock, patch

import httpx
from google import genai

from app.services.video_service import generate_video, is_native_gemini_video_url


REFERENCE = {"data": "data:image/png;base64," + base64.b64encode(b"image").decode()}


def generate(base_url: str, fps=None, **kwargs):
    return generate_video(
        "gemini", "test-key", "veo-3.1-generate-preview", "camera move", "9:16", fps, 8,
        quality="720p", base_url=base_url, **kwargs,
    )


def test_official_sdk_serializes_submits_polls_and_downloads() -> None:
    requests = []

    def handle(request):
        requests.append(request)
        assert request.headers["x-goog-api-key"] == "test-key"
        if request.method == "POST":
            assert request.url.path == "/v1beta/models/veo-3.1-generate-preview:predictLongRunning"
            payload = json.loads(request.content)
            assert payload["parameters"]["durationSeconds"] == 8
            assert payload["parameters"]["aspectRatio"] == "9:16"
            assert "fps" not in payload["parameters"]
            assert payload["instances"][0]["image"]["bytesBase64Encoded"] == base64.b64encode(b"image").decode()
            return httpx.Response(200, json={"name": "models/veo-3.1-generate-preview/operations/task-1"})
        if "operations" in request.url.path:
            return httpx.Response(200, json={
                "name": "models/veo-3.1-generate-preview/operations/task-1", "done": True,
                "response": {"generateVideoResponse": {"generatedSamples": [{"video": {
                    "uri": "https://generativelanguage.googleapis.com/v1beta/files/clip:download?alt=media"
                }}]}},
            })
        assert request.url.path == "/v1beta/files/clip:download"
        return httpx.Response(200, content=b"official-mp4")

    original_client = genai.Client

    def client_factory(**kwargs):
        kwargs["http_options"]["async_client_args"] = {"transport": httpx.MockTransport(handle)}
        return original_client(**kwargs)

    with patch("app.services.video_service.genai.Client", side_effect=client_factory), patch("app.services.video_service.asyncio.sleep", new=AsyncMock()):
        result = asyncio.run(generate("https://generativelanguage.googleapis.com/v1beta", fps=24, first_frame=REFERENCE))
    assert result.data == b"official-mp4"
    assert len(requests) == 3


def test_relay_task_contracts_and_token_scope() -> None:
    original_client = httpx.AsyncClient
    for legacy in (False, True):
        requests = []
        endpoint = "/v1/video/generations" if legacy else "/v1/videos"

        def handle(request):
            requests.append(request)
            if request.url.host == "cdn.example.com":
                assert "authorization" not in request.headers
                return httpx.Response(200, content=b"relay-mp4")
            assert request.headers["authorization"] == "Bearer test-key"
            if request.method == "POST":
                if legacy and request.url.path == "/v1/videos":
                    return httpx.Response(404)
                assert request.url.path == endpoint
                payload = json.loads(request.content)
                assert payload["model"] == "veo-3.1-generate-preview"
                assert payload["seconds"] == "8" and payload["duration"] == 8
                assert payload["size"] == "720x1280"
                assert payload["metadata"] == {"resolution": "720p", "aspectRatio": "9:16"}
                assert payload["images"] == [REFERENCE["data"]]
                return httpx.Response(200, json={"task_id": "task-1", "status": "queued"})
            if request.url.path.endswith("/content"):
                assert not legacy
                return httpx.Response(200, content=b"relay-mp4")
            assert request.url.path == endpoint + "/task-1"
            if legacy:
                return httpx.Response(200, json={"code": "success", "data": {"task_id": "task-1", "status": "SUCCESS", "result_url": "https://cdn.example.com/clip.mp4"}})
            return httpx.Response(200, json={"id": "task-1", "status": "completed"})

        def client_factory(**kwargs):
            return original_client(**kwargs, transport=httpx.MockTransport(handle))

        with patch("app.services.video_service.httpx.AsyncClient", side_effect=client_factory), patch("app.services.video_service.asyncio.sleep", new=AsyncMock()):
            result = asyncio.run(generate("https://relay.example.com" if legacy else "https://relay.example.com/v1", references=[REFERENCE]))
        assert result.data == b"relay-mp4"
        assert len([request for request in requests if request.method == "POST"]) == (2 if legacy else 1)


def test_relay_does_not_resubmit_failed_or_ambiguous_tasks() -> None:
    original_client = httpx.AsyncClient
    for status_code, body in (
        (500, {"error": {"message": "upstream unavailable"}}),
        (200, {"status": "queued"}),
        (200, {"id": "task-1", "status": "failed", "error": {"message": "quota exceeded"}}),
    ):
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(status_code, json=body)

        with patch("app.services.video_service.httpx.AsyncClient", side_effect=lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(handle))):
            try:
                asyncio.run(generate("https://relay.example.com/v1"))
            except (ValueError, httpx.HTTPStatusError):
                pass
            else:
                raise AssertionError("expected task failure")
        assert len(requests) == 1


def test_gemini_protocol_selection_and_media_validation() -> None:
    assert is_native_gemini_video_url("")
    assert is_native_gemini_video_url("https://generativelanguage.googleapis.com/v1beta")
    assert is_native_gemini_video_url("https://relay.example.com/gemini/v1beta")
    assert not is_native_gemini_video_url("https://relay.example.com/v1")
    for media in ({"references": [REFERENCE, REFERENCE]}, {"references": [REFERENCE], "first_frame": REFERENCE}, {"last_frame": REFERENCE}, {"reference_videos": [REFERENCE]}):
        try:
            asyncio.run(generate("https://relay.example.com/v1", **media))
        except ValueError:
            pass
        else:
            raise AssertionError("unsupported media must not be silently discarded")


def test_relay_timeout_does_not_resubmit() -> None:
    original_client = httpx.AsyncClient
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "task-1", "status": "queued"})

    with (
        patch("app.services.video_service.httpx.AsyncClient", side_effect=lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(handle))),
        patch("app.services.video_service.GENERATION_TIMEOUT_SECONDS", 0),
    ):
        try:
            asyncio.run(generate("https://relay.example.com/v1"))
        except TimeoutError:
            pass
        else:
            raise AssertionError("expected timeout")
    assert len(requests) == 1


if __name__ == "__main__":
    test_official_sdk_serializes_submits_polls_and_downloads()
    test_relay_task_contracts_and_token_scope()
    test_relay_does_not_resubmit_failed_or_ambiguous_tasks()
    test_gemini_protocol_selection_and_media_validation()
    test_relay_timeout_does_not_resubmit()
