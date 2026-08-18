"""One shared prompt optimizer serves the three standalone media generators."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import tempfile
from typing import Any, Iterator

from fastapi.testclient import TestClient

from app.core import database
from app.core.security import encrypt, token_for
from app.llms.registry import models
from app.llms.router import TextResult
from app.models import ModelConfig, User
from app.utils.common import now


CALLS: list[tuple[str, str]] = []


async def _fake_complete_text(*args: Any, **_kwargs: Any) -> TextResult:
    CALLS.append((str(args[3]), str(args[4])))
    return TextResult(text=f"optimized-{len(CALLS)}", usage={"inputTokens": 4, "outputTokens": 2})


@contextmanager
def _app(directory: str) -> Iterator[tuple[TestClient, dict[str, str], list[str]]]:
    from app.api.v1 import prompts
    from app.main import app

    original = (database.DB_PATH, models.complete_text, prompts.record_usage)
    usage: list[str] = []
    test_db_path = str(Path(directory) / "prompts.db")
    database.DB_PATH = test_db_path
    database._engines.pop(database.DB_PATH, None)
    models.complete_text = _fake_complete_text
    prompts.record_usage = lambda _user, _config, feature, *_args, **_kwargs: usage.append(feature)
    CALLS.clear()
    try:
        with TestClient(app) as client:
            with database.db() as session:
                user = User(created_at=now(), updated_at=now(), username="director", password="x", role="user", is_disabled=False)
                session.add(user)
                session.flush()
                user_id = int(user.id)
                session.add(ModelConfig(
                    created_at=now(), updated_at=now(), user_id=user_id, source="user",
                    provider="openai", encrypted_key=encrypt("sk-test-key-value"), is_active=True,
                    is_enabled=True, purpose="script", model_name="gpt-4o-mini",
                ))
            yield client, {"Authorization": f"Bearer {token_for(user_id)}"}, usage
    finally:
        database.DB_PATH, models.complete_text, prompts.record_usage = original
        database._engines.pop(test_db_path, None)


def test_media_prompt_optimization_uses_distinct_instructions_and_records_usage() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, usage):
            for kind, context in (
                ("image", {"outputLanguage": "en", "aspectRatio": "16:9", "quality": "2K"}),
                ("video", {"outputLanguage": "zh", "duration": 5, "fps": 24}),
                ("audio", {"voice": "Cherry", "speechRate": 1.2}),
            ):
                response = client.post(
                    "/api/prompts/optimize",
                    json={"kind": kind, "prompt": "原始内容", "context": context},
                    headers=headers,
                )
                assert response.status_code == 200, response.text
                assert response.json()["prompt"].startswith("optimized-")

            assert len({system for system, _user in CALLS}) == 3
            assert '"aspectRatio": "16:9"' in CALLS[0][1]
            assert "输出语言：英文" in CALLS[0][1]
            assert "输出语言：中文" in CALLS[1][1]
            assert "输出语言：" not in CALLS[2][1]
            assert usage == ["image_prompt_optimize", "video_prompt_optimize", "audio_prompt_optimize"]


def test_media_prompt_optimization_validates_kind_and_content() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _usage):
            for body in (
                {"kind": "music", "prompt": "x"},
                {"kind": "image", "prompt": ""},
                {"kind": "image", "prompt": "x", "context": {"outputLanguage": "fr"}},
            ):
                response = client.post("/api/prompts/optimize", json=body, headers=headers)
                assert response.status_code == 422, response.text


if __name__ == "__main__":
    test_media_prompt_optimization_uses_distinct_instructions_and_records_usage()
    test_media_prompt_optimization_validates_kind_and_content()
    print("test_prompt_optimization ok")
