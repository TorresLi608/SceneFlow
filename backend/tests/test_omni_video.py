from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

import httpx
from sqlmodel import select

from app.api.v1.videos import generate_video_route
from app.api.v1.settings import discover_models, video_model_catalog
from app.schemas.serializers import config_json
from app.core.security import encrypt
from app.core import database
from app.models import ModelConfig, UsageLog, User
from app.services import artifact_service
from app.services.config_service import config_create_fields, default_video_capabilities, normalize_config_payload, _model_config
from app.services.generation_record_service import list_generation_records
from app.services.video_service import VideoSettings, generate_video, resolve_video_settings


REFERENCE = {"data": "data:image/png;base64," + base64.b64encode(b"image").decode()}


def generate(base="https://generativelanguage.googleapis.com/v1beta", **kwargs):
    return generate_video(
        "gemini", "test-key", kwargs.pop("model", "gemini-omni-1.1-flash"), "camera move",
        "9:16", None, 5, quality="1080p", base_url=base, **kwargs,
    )


def test_omni_configs_catalog_and_model_discovery() -> None:
    capabilities = default_video_capabilities("gemini", "gemini-omni-1.1-flash")
    assert capabilities["qualities"] == ["720p", "1080p", "4K"]
    assert capabilities["fps"] == []
    assert (capabilities["minDuration"], capabilities["maxDuration"]) == (3, 10)
    assert capabilities["maxReferenceImages"] == 1
    assert capabilities["supportsFirstFrame"] and not capabilities["supportsLastFrame"]
    for model, base in (("gemini-omni-1.1-flash", "https://generativelanguage.googleapis.com/v1beta"), ("omni1.1-flash", "https://relay.example.com/v1")):
        config = normalize_config_payload({
            "provider": "Gemini", "purpose": "video", "modelSeries": model,
            "baseUrl": base, "apiKey": "test-key",
        })
        assert (config["provider"], config["model"], config["base_url"]) == ("gemini", model, base)
        assert config["video_capabilities"] == capabilities
    catalog = video_model_catalog(1)["models"]
    assert any(item["provider"] == "gemini" and item["model"] == "gemini-omni-1.1-flash" for item in catalog)
    assert any(item["provider"] == "gemini" and item["model"].startswith("veo-") for item in catalog)
    with patch("app.api.v1.settings.models.list_models", new=AsyncMock(return_value=["omni1.1-flash"])) as discover:
        relay = asyncio.run(discover_models({"provider": "gemini", "baseUrl": "https://relay.example.com/v1", "apiKey": "test-key"}, 1))
        assert relay["models"] == ["omni1.1-flash"]
        discover.assert_awaited_once_with("gemini", "test-key", "https://relay.example.com/v1")
    # Previously saved Google configs still serialize and execute as Gemini.
    assert not any(item["provider"] == "google" for item in catalog)
    legacy = ModelConfig(provider="google", purpose="video", model_name="gemini-omni-1.1-flash", encrypted_key=encrypt("test-key"))
    assert config_json(legacy)["provider"] == "gemini"
    resolved = _model_config(legacy, "video", "video", "user")
    assert resolved["provider"] == "gemini"
    assert resolved["model"] == "gemini-omni-1.1-flash"
    assert resolved["videoCapabilities"] == capabilities
    assert normalize_config_payload({}, legacy)["provider"] == "gemini"
    assert resolve_video_settings("gemini", "9:16", "1080p") == VideoSettings("1080p", "9:16")
    try:
        resolve_video_settings("gemini", "1:1")
    except ValueError:
        pass
    else:
        raise AssertionError("Omni does not support square video")


def test_omni_official_inline_output_and_reference_roles() -> None:
    original_client = httpx.AsyncClient
    for frame in (False, True):
        requests = []

        def handle(request):
            requests.append(request)
            assert request.url == "https://generativelanguage.googleapis.com/v1beta/interactions"
            assert request.headers["x-goog-api-key"] == "test-key"
            assert "authorization" not in request.headers
            payload = json.loads(request.content)
            assert payload["model"] == "gemini-omni-1.1-flash"
            assert payload["response_format"] == {"type": "video", "delivery": "uri", "aspect_ratio": "9:16", "resolution": "1080p", "duration": "5s"}
            assert payload["background"] is False and payload["store"] is False and payload["stream"] is False
            image, prompt = payload["input"]
            assert image == {"type": "image", "mime_type": "image/png", "data": base64.b64encode(b"image").decode()}
            assert ("<FIRST_FRAME>" if frame else "<IMAGE_REF_0>") in prompt["text"]
            return httpx.Response(200, json={"status": "completed", "steps": [
                {"type": "user_input", "content": [{"type": "video", "data": "bad"}]},
                {"type": "model_output", "content": [{"type": "video", "mime_type": "video/mp4", "data": base64.b64encode(b"omni-mp4").decode()}]},
            ]})

        with patch("app.services.video_service.httpx.AsyncClient", side_effect=lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(handle))):
            result = asyncio.run(generate(**({"first_frame": REFERENCE} if frame else {"references": [REFERENCE]})))
        assert result.data == b"omni-mp4"
        assert len(requests) == 1


def test_omni_official_polls_file_then_downloads() -> None:
    original_client = httpx.AsyncClient
    requests = []
    polls = 0

    def handle(request):
        nonlocal polls
        requests.append(request)
        if request.url.host == "cdn.example.com":
            assert "x-goog-api-key" not in request.headers
            return httpx.Response(200, content=b"downloaded-mp4")
        assert request.headers["x-goog-api-key"] == "test-key"
        if request.method == "POST":
            assert json.loads(request.content)["input"] == "camera move"
            return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "video", "uri": "https://generativelanguage.googleapis.com/v1beta/files/clip:download?alt=media"}]}]})
        if request.url.path.endswith(":download"):
            assert request.url.params["alt"] == "media"
            return httpx.Response(302, headers={"location": "https://cdn.example.com/files/clip.mp4"})
        assert request.url.path == "/v1beta/files/clip"
        polls += 1
        return httpx.Response(200, json={"state": "ACTIVE" if polls == 2 else "PROCESSING"})

    with patch("app.services.video_service.httpx.AsyncClient", side_effect=lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(handle))), patch("app.services.video_service.asyncio.sleep", new=AsyncMock()):
        result = asyncio.run(generate())
    assert result.data == b"downloaded-mp4"
    assert len(requests) == 5


def test_omni_relay_preserves_alias_and_uses_video_tasks() -> None:
    original_client = httpx.AsyncClient
    for legacy in (False, True):
        requests = []

        def handle(request):
            requests.append(request)
            if request.url.host == "cdn.example.com":
                assert "authorization" not in request.headers and "x-goog-api-key" not in request.headers
                return httpx.Response(200, content=b"relay-omni-mp4")
            assert request.headers["authorization"] == "Bearer test-key"
            assert "x-goog-api-key" not in request.headers
            if request.method == "POST":
                if legacy and request.url.path == "/v1/videos":
                    return httpx.Response(404)
                payload = json.loads(request.content)
                assert payload["model"] == "omni1.1-flash"
                assert payload["duration"] == 5 and payload["seconds"] == "5"
                assert payload["images"] == [REFERENCE["data"]]
                assert "response_format" not in payload
                return httpx.Response(200, json={"id": "task-1", "status": "queued"})
            assert request.url.path == ("/v1/video/generations/task-1" if legacy else "/v1/videos/task-1")
            return httpx.Response(200, json={"status": "completed", "url": "https://cdn.example.com/omni.mp4"})

        with patch("app.services.video_service.httpx.AsyncClient", side_effect=lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(handle))), patch("app.services.video_service.asyncio.sleep", new=AsyncMock()):
            result = asyncio.run(generate("https://relay.example.com/v1", model="omni1.1-flash", references=[REFERENCE]))
        assert result.data == b"relay-omni-mp4"
        assert len(requests) == (4 if legacy else 3)


def test_omni_official_failure_timeout_and_media_guards() -> None:
    original_client = httpx.AsyncClient
    bodies = [
        {"status": "failed", "error": {"message": "generation failed"}},
        {"status": "completed", "steps": []},
        {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "video", "data": "invalid!"}]}]},
    ]
    for body in bodies:
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(200, json=body)

        with patch("app.services.video_service.httpx.AsyncClient", side_effect=lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(handle))):
            try:
                asyncio.run(generate())
            except ValueError:
                pass
            else:
                raise AssertionError("expected generation failure")
        assert len(requests) == 1

    async def slow_response(request):
        await asyncio.sleep(0.1)
        raise AssertionError("request must time out")

    with patch("app.services.video_service.httpx.AsyncClient", side_effect=lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(slow_response))), patch("app.services.video_service.GENERATION_TIMEOUT_SECONDS", 0.01):
        try:
            asyncio.run(generate())
        except TimeoutError:
            pass
        else:
            raise AssertionError("expected generation timeout")
    for media in ({"last_frame": REFERENCE}, {"reference_videos": [REFERENCE]}, {"references": [REFERENCE, REFERENCE]}, {"references": [REFERENCE], "first_frame": REFERENCE}):
        try:
            asyncio.run(generate(**media))
        except ValueError:
            pass
        else:
            raise AssertionError("unsupported media must not be silently ignored")


def test_omni_video_route_resolves_configs_persists_history_and_meters() -> None:
    original_client = httpx.AsyncClient
    with tempfile.TemporaryDirectory() as directory:
        original_db, original_media = database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR
        database.DB_PATH = str(Path(directory) / "omni.db")
        artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "media"
        try:
            database.init_db()
            with database.db() as session:
                owner = User(username="omni-video-owner", password="x", balance_micros=1000000)
                session.add(owner)
                session.flush()
                owner_id = int(owner.id)
            for source in ("official", "user"):
                payload = {
                    "purpose": "video", "provider": "gemini", "modelSeries": "gemini-omni-1.1-flash",
                    "baseUrl": "https://generativelanguage.googleapis.com/v1beta", "apiKey": "test-key",
                }
                fields = config_create_fields(payload, normalize_config_payload(payload))
                with database.db() as session:
                    config = ModelConfig(**fields, source=source, user_id=owner_id if source == "user" else None, unit_name="second")
                    session.add(config)
                    session.flush()
                    config_id = config.id

                def handle(request):
                    assert request.url.path == "/v1beta/interactions"
                    return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "video", "data": base64.b64encode(b"route-mp4").decode()}]}]})

                with patch("app.services.video_service.httpx.AsyncClient", side_effect=lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(handle))):
                    result = asyncio.run(generate_video_route({
                        "officialConfigId" if source == "official" else "configId": config_id,
                        "prompt": "camera move", "duration": 5, "aspectRatio": "9:16", "quality": "1080p",
                    }, owner_id))
                assert result["video"]["model"] == "gemini-omni-1.1-flash"
                assert "fps" not in result["video"]
                assert result["history"]["provider"] == "gemini"
            with database.db() as session:
                history = list_generation_records(session, owner_id, "video")
                assert len(history) == 2
                assert all(item.provider == "gemini" and not item.path.startswith("http") for item in history)
                logs = session.exec(select(UsageLog).where(UsageLog.user_id == owner_id)).all()
                assert len(logs) == 2
                assert all(item.provider == "gemini" and item.quantity == 5 for item in logs)
        finally:
            database._engines.pop(str(database.DB_PATH), None)
            database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR = original_db, original_media


if __name__ == "__main__":
    test_omni_configs_catalog_and_model_discovery()
    test_omni_official_inline_output_and_reference_roles()
    test_omni_official_polls_file_then_downloads()
    test_omni_relay_preserves_alias_and_uses_video_tasks()
    test_omni_official_failure_timeout_and_media_guards()
    test_omni_video_route_resolves_configs_persists_history_and_meters()
