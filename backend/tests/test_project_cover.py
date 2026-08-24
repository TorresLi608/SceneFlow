"""Project identity: the synopsis and cover a series card is built from.

Both are optional by design, and both AI helpers are project-less and side-effect free so
the create dialog can use them before a project row exists.
"""

from __future__ import annotations

import base64
from pathlib import Path
import tempfile
from typing import Any, Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.core import database
from app.core.security import encrypt, token_for
from app.llms.registry import models
from app.llms.router import ImageResult, TextResult
from app.models import ModelConfig, Project, User
from app.services import artifact_service
from app.utils.common import now


# A one-pixel PNG, small enough to keep the fixtures readable.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode("ascii")

CONFIGS = (
    ("script", "openai", "gpt-4o-mini"),
    ("image", "openai", "gpt-image-1"),
)


async def _fake_generate_image(*_args: Any, **_kwargs: Any) -> ImageResult:
    return ImageResult(data=PNG_BYTES, format="png")


async def _fake_complete_text(*_args: Any, **_kwargs: Any) -> TextResult:
    return TextResult(text="被雨困住的小城里，两个陌生人共用了同一把伞。", usage={"inputTokens": 8, "outputTokens": 20})


@contextmanager
def _app(directory: str) -> Iterator[tuple[TestClient, dict[str, str]]]:
    from app.main import app

    original = (
        database.DB_PATH,
        artifact_service.PRIVATE_GENERATED_DIR,
        models.generate_image,
        models.complete_text,
    )
    database.DB_PATH = str(Path(directory) / "cover.db")
    database._engines.pop(database.DB_PATH, None)
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "private_generated"
    models.generate_image = _fake_generate_image
    models.complete_text = _fake_complete_text
    try:
        with TestClient(app) as client:
            with database.db() as session:
                user = User(
                    created_at=now(),
                    updated_at=now(),
                    username="director",
                    password="x",
                    role="user",
                    is_disabled=False,
                )
                session.add(user)
                session.flush()
                user_id = int(user.id)
                for purpose, provider, model_name in CONFIGS:
                    session.add(
                        ModelConfig(
                            created_at=now(),
                            updated_at=now(),
                            user_id=user_id,
                            source="user",
                            provider=provider,
                            encrypted_key=encrypt("sk-test-key-value"),
                            is_active=True,
                            is_enabled=True,
                            purpose=purpose,
                            model_name=model_name,
                        )
                    )
            yield client, {"Authorization": f"Bearer {token_for(user_id)}"}
    finally:
        (
            database.DB_PATH,
            artifact_service.PRIVATE_GENERATED_DIR,
            models.generate_image,
            models.complete_text,
        ) = original
        database._engines.pop(str(database.DB_PATH), None)


def _create_project(client: TestClient, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    response = client.post("/api/projects", json={"title": "雨伞", **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["project"]


def test_a_project_without_a_cover_or_synopsis_is_still_valid() -> None:
    """Both fields are optional; the card falls back client-side rather than 400-ing here."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers)

            assert project["description"] == ""
            assert project["coverImageUrl"] is None


def test_description_round_trips_through_create_patch_and_list() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers, description="两个陌生人共用一把伞")
            assert project["description"] == "两个陌生人共用一把伞"

            patched = client.patch(
                f"/api/projects/{project['id']}",
                json={"description": "改写后的简介"},
                headers=headers,
            )
            assert patched.status_code == 200, patched.text
            assert patched.json()["project"]["description"] == "改写后的简介"

            listed = client.get("/api/projects", headers=headers).json()["projects"][0]
            assert listed["description"] == "改写后的简介"


def test_uploaded_cover_is_stored_by_path_and_served_through_a_signed_link() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers)

            response = client.put(
                f"/api/projects/{project['id']}/cover",
                json={"imageData": PNG_DATA_URL},
                headers=headers,
            )

            assert response.status_code == 200, response.text
            cover_url = response.json()["project"]["coverImageUrl"]
            assert "/api/chat/artifacts/" in cover_url
            # The row holds a relative path, never the expiring URL that was handed out.
            with database.db() as session:
                stored = session.exec(
                    database.select(Project).where(Project.id == project["id"])
                ).first().cover_image_path
            assert stored and not stored.startswith("http")

            download = client.get("/api/chat/artifacts/" + cover_url.rsplit("/", 1)[-1])
            assert download.status_code == 200, download.text
            assert download.content == PNG_BYTES


def test_a_cover_that_is_not_an_image_data_url_is_refused() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers)

            response = client.put(
                f"/api/projects/{project['id']}/cover",
                json={"imageData": "https://example.com/cover.png"},
                headers=headers,
            )

            assert response.status_code == 400, response.text
            assert "data URL" in response.json()["error"]


def test_clearing_the_cover_returns_the_project_to_the_fallback() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers)
            client.put(f"/api/projects/{project['id']}/cover", json={"imageData": PNG_DATA_URL}, headers=headers)

            response = client.delete(f"/api/projects/{project['id']}/cover", headers=headers)

            assert response.status_code == 200, response.text
            assert response.json()["project"]["coverImageUrl"] is None


def test_cover_generation_returns_bytes_without_touching_any_project() -> None:
    """The create dialog calls this before a project exists, so it must not need one."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            before = client.get("/api/projects", headers=headers).json()["projects"]

            response = client.post(
                "/api/projects/cover/generate",
                json={"prompt": "雨夜街头，两个陌生人共用一把伞", "title": "雨伞"},
                headers=headers,
            )

            assert response.status_code == 200, response.text
            assert response.json()["imageData"].startswith("data:image/png;base64,")
            # Nothing was created or written along the way.
            assert client.get("/api/projects", headers=headers).json()["projects"] == before


def test_cover_generation_needs_a_prompt_not_just_a_title() -> None:
    """The picture is described by the prompt, so a title alone is not something to draw.

    Deliberately stricter than before: the cover used to be derived from the title and
    synopsis, which meant the only way to change it was to rewrite the story.
    """
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            assert client.post("/api/projects/cover/generate", json={}, headers=headers).status_code == 400

            titled = client.post(
                "/api/projects/cover/generate",
                json={"title": "雨伞"},
                headers=headers,
            )
            assert titled.status_code == 400, titled.text


def test_cover_prompt_round_trips_through_create_patch_and_list() -> None:
    """The prompt is stored, so reopening a project shows what drew its cover."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            created = client.post(
                "/api/projects",
                json={"title": "雨伞", "coverPrompt": "雨夜街头"},
                headers=headers,
            )
            assert created.status_code == 201, created.text
            assert created.json()["project"]["coverPrompt"] == "雨夜街头"

            patched = client.patch(
                f"/api/projects/{created.json()['project']['id']}",
                json={"coverPrompt": "天台黄昏"},
                headers=headers,
            )
            assert patched.status_code == 200, patched.text
            assert patched.json()["project"]["coverPrompt"] == "天台黄昏"

            listed = client.get("/api/projects", headers=headers).json()["projects"][0]
            assert listed["coverPrompt"] == "天台黄昏"


if __name__ == "__main__":
    test_a_project_without_a_cover_or_synopsis_is_still_valid()
    test_description_round_trips_through_create_patch_and_list()
    test_uploaded_cover_is_stored_by_path_and_served_through_a_signed_link()
    test_a_cover_that_is_not_an_image_data_url_is_refused()
    test_clearing_the_cover_returns_the_project_to_the_fallback()
    test_cover_generation_returns_bytes_without_touching_any_project()
    test_cover_generation_needs_a_prompt_not_just_a_title()
    test_cover_prompt_round_trips_through_create_patch_and_list()
    print("test_project_cover ok")
