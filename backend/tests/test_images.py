from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from openai import RateLimitError

from app.api.v1.images import generate_image
from app.core import database
from app.core.database import db, init_db
from app.llms.router import GENERATION_TIMEOUT_SECONDS, ModelRouter, _qwen_image_size
from app.models import User
from app.utils.common import now


@contextmanager
def _db():
    yield object()


def test_generate_image_records_usage_without_references() -> None:
    config = {"provider": "openai", "apiKey": "test-key", "model": "gpt-image-1"}
    usage = Mock()
    with (
        patch("app.api.v1.images.db", _db),
        patch("app.api.v1.images.active_model_config", return_value=config),
        patch("app.api.v1.images.models.generate_image", AsyncMock(return_value=SimpleNamespace(data=b"png", format="png"))),
        patch("app.api.v1.images.record_usage", usage),
        patch("app.api.v1.images.persist_image", return_value="http://example.test/image.png"),
    ):
        result = asyncio.run(generate_image({"prompt": "a fox"}, 1))

    assert result["image"]["url"] == "http://example.test/image.png"
    assert usage.call_args.args[:3] == (1, config, "image")
    assert isinstance(usage.call_args.args[3], float)


def test_official_image_requires_balance_but_personal_config_does_not() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "images.db"
        try:
            init_db()
            stamp = now()
            with db() as session:
                user = User(created_at=stamp, updated_at=stamp, username="image-user", password="x", role="user", is_disabled=False)
                session.add(user)
                session.flush()
                user_id = int(user.id)
            config = {"source": "official", "provider": "openai", "apiKey": "test-key", "model": "gpt-image-1"}
            generate = AsyncMock(return_value=SimpleNamespace(data=b"png", format="png"))
            with (
                patch("app.api.v1.images.active_model_config", return_value=config),
                patch("app.api.v1.images.models.generate_image", generate),
                patch("app.api.v1.images.record_usage"),
                patch("app.api.v1.images.persist_image", return_value="http://example.test/image.png"),
            ):
                try:
                    asyncio.run(generate_image({"prompt": "a fox"}, user_id))
                    raise AssertionError("official image generation must be blocked at zero balance")
                except Exception as exc:
                    assert getattr(exc, "status_code", None) == 402
                assert generate.await_count == 0

                with db() as session:
                    session.get(User, user_id).balance_micros = 1
                result = asyncio.run(generate_image({"prompt": "a fox"}, user_id))
                assert result["image"]["url"] == "http://example.test/image.png"
                assert generate.await_count == 1
        finally:
            database.DB_PATH = original_path


def test_gemini_image_uses_generate_content_without_duplicate_api_version() -> None:
    generate = AsyncMock(
        return_value=SimpleNamespace(
            parts=[SimpleNamespace(inline_data=SimpleNamespace(data=b"png", mime_type="image/png"))]
        )
    )
    aio = SimpleNamespace(models=SimpleNamespace(generate_content=generate), aclose=AsyncMock())
    client = Mock(return_value=SimpleNamespace(aio=aio))

    with patch("app.llms.router.genai.Client", client):
        result = asyncio.run(
            ModelRouter()._generate_gemini_image(
                "test-key",
                "gemini-image",
                "draw it",
                [("reference.jpg", b"jpeg", "image/jpeg")],
                "16:9",
                "2K",
                "https://generativelanguage.googleapis.com/v1beta",
            )
        )

    assert result.data == b"png"
    assert client.call_args.kwargs["http_options"] == {
        "base_url": "https://generativelanguage.googleapis.com",
        "timeout": GENERATION_TIMEOUT_SECONDS * 1000,
    }
    request = generate.call_args.kwargs
    assert request["config"].response_modalities == ["TEXT", "IMAGE"]
    assert request["config"].image_config.aspect_ratio == "16:9"
    assert request["contents"][1].inline_data.data == b"jpeg"


def test_openai_image_does_not_retry_provider_errors() -> None:
    request = httpx.Request("POST", "https://images.example.test/v1/images/generations")
    error = RateLimitError(
        "No available image quota. Please try again later.",
        response=httpx.Response(429, request=request),
        body={"error": "No available image quota. Please try again later."},
    )
    generate = AsyncMock(side_effect=error)
    client = Mock(return_value=SimpleNamespace(images=SimpleNamespace(generate=generate)))

    with patch("app.llms.router.AsyncOpenAI", client):
        try:
            asyncio.run(ModelRouter().generate_image("test-key", "image-model", "draw it"))
            raise AssertionError("provider error must be returned")
        except ValueError as exc:
            assert "provider status 429" in str(exc)

    assert generate.await_count == 1
    assert client.call_args.kwargs["max_retries"] == 0


def test_qwen_image_uses_async_task_with_reference_images() -> None:
    assert _qwen_image_size("2:3", "2K", False) == "1360*2048"
    assert _qwen_image_size("16:9", "4K", True, "wan2.7-image-pro") == "2K"
    assert _qwen_image_size("16:9", "4K", False, "wan2.7-image") == "2048*1152"
    response = SimpleNamespace(json=lambda: {"output": {"task_id": "task-1"}}, raise_for_status=lambda: None)
    task = SimpleNamespace(json=lambda: {"output": {"task_status": "SUCCEEDED", "results": [{"url": "https://image.test/result.png"}]}}, raise_for_status=lambda: None)
    image = SimpleNamespace(content=b"png", headers={"content-type": "image/png"}, raise_for_status=lambda: None)
    client = AsyncMock()
    client.post.return_value = response
    client.get.side_effect = [task, image]
    context = AsyncMock()
    context.__aenter__.return_value = client
    with patch("app.llms.router.httpx.AsyncClient", return_value=context), patch("app.llms.router.asyncio.sleep", new=AsyncMock()):
        result = asyncio.run(
            ModelRouter()._generate_qwen_image(
                "test-key", "wan2.7-image", "draw it", [("face.png", b"png", "image/png")], "16:9", "2K"
            )
        )

    assert result.data == b"png"
    request = client.post.call_args.kwargs
    assert request["headers"]["X-DashScope-Async"] == "enable"
    assert request["json"]["input"]["messages"][0]["content"][0]["image"].startswith("data:image/png;base64,")
    assert request["json"]["input"]["messages"][0]["content"][-1] == {"text": "draw it"}
    assert request["json"]["parameters"]["size"] == "2K"


if __name__ == "__main__":
    test_generate_image_records_usage_without_references()
    test_official_image_requires_balance_but_personal_config_does_not()
    test_gemini_image_uses_generate_content_without_duplicate_api_version()
    test_openai_image_does_not_retry_provider_errors()
    test_qwen_image_uses_async_task_with_reference_images()
