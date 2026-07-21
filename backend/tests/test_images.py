from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import database
from database import db, init_db
from routers.images import generate_image
from lib.utils import now


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


def test_official_image_requires_balance_but_personal_config_does_not() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "images.db"
        try:
            init_db()
            stamp = now()
            with db() as conn:
                user_id = int(
                    conn.execute(
                        "INSERT INTO users (created_at, updated_at, username, password, role, is_disabled) VALUES (?, ?, 'image-user', 'x', 'user', 0)",
                        (stamp, stamp),
                    ).lastrowid
                )
            config = {"source": "official", "provider": "openai", "apiKey": "test-key", "model": "gpt-image-1"}
            generate = AsyncMock(return_value=SimpleNamespace(data=b"png", format="png"))
            with (
                patch("routers.images.active_model_config", return_value=config),
                patch("routers.images.models.generate_image", generate),
                patch("routers.images.record_usage"),
                patch("routers.images.persist_image", return_value="http://example.test/image.png"),
            ):
                try:
                    asyncio.run(generate_image({"prompt": "a fox"}, user_id))
                    raise AssertionError("official image generation must be blocked at zero balance")
                except Exception as exc:
                    assert getattr(exc, "status_code", None) == 402
                assert generate.await_count == 0

                with db() as conn:
                    conn.execute("UPDATE users SET balance_micros=1 WHERE id=?", (user_id,))
                result = asyncio.run(generate_image({"prompt": "a fox"}, user_id))
                assert result["image"]["url"] == "http://example.test/image.png"
                assert generate.await_count == 1
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_generate_image_records_usage_without_references()
    test_official_image_requires_balance_but_personal_config_does_not()
