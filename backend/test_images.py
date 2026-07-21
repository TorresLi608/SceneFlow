from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from routers.images import generate_image


@contextmanager
def _db():
    yield object()


def test_generate_image_records_usage_without_references() -> None:
    config = {"provider": "openai", "apiKey": "test-key", "model": "gpt-image-1"}
    usage = Mock()
    with (
        patch("routers.images.db", _db),
        patch("routers.images.active_model_config", return_value=config),
        patch("routers.images.models.generate_image", AsyncMock(return_value=SimpleNamespace(data=b"png", format="png"))),
        patch("routers.images.record_usage", usage),
        patch("routers.images.persist_image", return_value="http://example.test/image.png"),
    ):
        result = asyncio.run(generate_image({"prompt": "a fox"}, 1))

    assert result["image"]["url"] == "http://example.test/image.png"
    assert usage.call_args.args[:3] == (1, config, "image")
    assert isinstance(usage.call_args.args[3], float)


if __name__ == "__main__":
    test_generate_image_records_usage_without_references()
