"""End-to-end checks over the real ASGI app: the contract the frontend actually calls."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any, Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.core import database
from app.core.security import encrypt, token_for
from app.llms.registry import models
from app.llms.router import ParseResult, SceneDraft
from app.models import ModelConfig, Project, Scene, User
from app.services import artifact_service
from app.services.generation_service import episode_media_status
from app.utils.common import now


PARSED = ParseResult(
    scenes=[
        SceneDraft(narration="山门在雾里若隐若现", visualPrompt="wide shot, misty mountain gate"),
        SceneDraft(narration="少年抬头望向石阶", visualPrompt="low angle, boy looking up stone steps"),
    ],
    source="llm",
    usage={"inputTokens": 10, "outputTokens": 20},
)

CONFIGS = (
    ("script", "openai", "gpt-4o-mini"),
    ("image", "openai", "gpt-image-1"),
    ("audio", "edge", "zh-CN-XiaoxiaoNeural"),
)


async def _fake_parse_script(*_args: Any, **_kwargs: Any) -> ParseResult:
    return PARSED


async def _fake_run_generation(*_args: Any, **_kwargs: Any) -> None:
    """Stand in for the real fan-out so the test never reaches a provider."""


@contextmanager
def _app(directory: str) -> Iterator[tuple[TestClient, dict[str, str]]]:
    from app.api.v1 import projects
    from app.main import app

    original = (database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR, projects.run_generation, models.parse_script)
    database.DB_PATH = str(Path(directory) / "api.db")
    database._engines.pop(database.DB_PATH, None)
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "private_generated"
    projects.run_generation = _fake_run_generation
    models.parse_script = _fake_parse_script
    try:
        with TestClient(app) as client:
            with database.db() as session:
                user = User(created_at=now(), updated_at=now(), username="director", password="x", role="user", is_disabled=False)
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
        database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR, projects.run_generation, models.parse_script = original
        database._engines.pop(str(database.DB_PATH), None)


def _create_project(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/projects", json={"title": "都市奇缘"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["project"]["id"]


def test_rejected_body_uses_the_same_error_shape_as_everything_else() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            response = client.post("/api/projects", json={"title": "x", "bogus": 1}, headers=headers)

            assert response.status_code == 422, response.text
            # One shape for every failure, and it names the offending field.
            body = response.json()
            assert set(body) == {"error"}
            assert "bogus" in body["error"]


def test_production_settings_round_trip() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _create_project(client, headers)
            created = client.get("/api/projects", headers=headers).json()["projects"][0]
            assert created["productionSettings"]["aspectRatio"] == "9:16"

            # Exactly the payload the settings form posts.
            response = client.patch(
                f"/api/projects/{project_id}/production-settings",
                json={
                    "mode": "drama",
                    "aspectRatio": "16:9",
                    "width": 1920,
                    "height": 1080,
                    "fps": 30,
                    "targetDurationMs": 90000,
                    "language": "zh-CN",
                    "stylePrompt": "cinematic",
                    "negativePrompt": "text, watermark",
                },
                headers=headers,
            )

            assert response.status_code == 200, response.text
            settings = response.json()["project"]["productionSettings"]
            assert (settings["mode"], settings["aspectRatio"], settings["fps"]) == ("drama", "16:9", 30)
            # currentStage was not in the payload, so it must survive untouched.
            assert response.json()["project"]["currentStage"] == "script"

            rejected = client.patch(
                f"/api/projects/{project_id}/production-settings",
                json={"targetDurationMs": 5},
                headers=headers,
            )
            assert rejected.status_code == 422, rejected.text


def test_parse_applies_when_there_is_nothing_to_lose() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _create_project(client, headers)

            response = client.post(
                f"/api/projects/{project_id}/parse",
                json={"script": "少年上山求道，山门在雾里。"},
                headers=headers,
            )

            assert response.status_code == 200, response.text
            body = response.json()
            assert body["applied"] is True
            assert body["discardsGeneratedScenes"] == 0
            assert [scene["narration"] for scene in body["scenes"]] == [draft.narration for draft in PARSED.scenes]
            # The parse lock has to be released, or nothing else can ever start.
            assert body["status"] == "idle"


def test_reparse_holds_back_until_the_user_accepts_losing_rendered_shots() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _create_project(client, headers)
            client.post(f"/api/projects/{project_id}/parse", json={"script": "第一版剧本"}, headers=headers)

            # Stand in for a render that already cost the user money.
            stored = artifact_service.store_artifact("projects", project_id, "shot.png", b"rendered")
            with database.db() as session:
                scene = session.exec(database.select(Scene).where(Scene.project_id == project_id)).first()
                scene.image_path = stored
                scene.image_status = "success"
                session.add(scene)
                first_scene_id = scene.id

            preview = client.post(
                f"/api/projects/{project_id}/parse",
                json={"script": "第二版剧本"},
                headers=headers,
            )

            assert preview.status_code == 200, preview.text
            body = preview.json()
            assert body["applied"] is False
            assert body["discardsGeneratedScenes"] == 1
            assert len(body["pendingScenes"]) == len(PARSED.scenes)
            # Nothing was destroyed: the rendered shot is still there.
            assert any(scene["id"] == first_scene_id for scene in body["scenes"])

            confirmed = client.post(
                f"/api/projects/{project_id}/parse",
                json={"script": "第二版剧本", "replaceAll": True},
                headers=headers,
            )

            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["applied"] is True
            assert all(scene["id"] != first_scene_id for scene in confirmed.json()["scenes"])


def test_scene_assets_are_served_through_a_fresh_signed_link() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _create_project(client, headers)
            client.post(f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers)
            stored = artifact_service.store_artifact("projects", project_id, "shot.png", b"rendered-bytes")
            with database.db() as session:
                scene = session.exec(database.select(Scene).where(Scene.project_id == project_id)).first()
                scene.image_path = stored
                scene.image_status = "success"
                session.add(scene)

            project = client.get("/api/projects", headers=headers).json()["projects"][0]
            image_url = next(scene["image"]["url"] for scene in project["scenes"] if scene["image"]["url"])

            # The row stores a path; the response carries a link that actually resolves.
            assert "/api/chat/artifacts/" in image_url
            download = client.get("/api/chat/artifacts/" + image_url.rsplit("/", 1)[-1])
            assert download.status_code == 200, download.text
            assert download.content == b"rendered-bytes"


def test_scene_terminal_progress_survives_reload() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _create_project(client, headers)
            client.post(f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers)
            with database.db() as session:
                scene = session.exec(database.select(Scene).where(Scene.project_id == project_id)).first()
                scene.image_status = "success"
                scene.audio_status = "generating"
                session.add(scene)

            scene = client.get("/api/projects", headers=headers).json()["projects"][0]["scenes"][0]
            assert scene["image"]["progress"] == 100
            assert scene["audio"]["progress"] == 20


def test_selected_media_generation_and_scene_crud() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _create_project(client, headers)
            parsed = client.post(f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers).json()
            selected_id = parsed["scenes"][0]["id"]

            started = client.post(
                f"/api/projects/{project_id}/generate",
                json={"media": "audio", "sceneIds": [selected_id]},
                headers=headers,
            )
            assert started.status_code == 202, started.text
            assert started.json()["media"] == "audio"
            assert started.json()["sceneCount"] == 1

            # The test worker leaves the project busy, matching the lock test below.
            with database.db() as session:
                project = session.exec(database.select(Project).where(Project.id == project_id)).first()
                project.status = "idle"
                session.add(project)
            added = client.post(
                f"/api/projects/{project_id}/scenes",
                json={"episodeId": parsed["episodeId"], "narration": "新增镜头"},
                headers=headers,
            )
            assert added.status_code == 201, added.text
            added_id = added.json()["scene"]["id"]
            deleted = client.delete(f"/api/projects/{project_id}/scenes/{added_id}", headers=headers)
            assert deleted.status_code == 204, deleted.text


def test_retry_status_keeps_other_failed_scenes_visible() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _create_project(client, headers)
            parsed = client.post(f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers).json()
            with database.db() as session:
                scenes = list(session.exec(database.select(Scene).where(Scene.project_id == project_id)).all())
                scenes[0].image_status = "success"
                scenes[1].image_status = "error"
                session.add_all(scenes)

            assert episode_media_status(parsed["episodeId"], [True]) == "partial"


def test_second_generate_is_refused_while_the_first_is_running() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _create_project(client, headers)
            client.post(f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers)

            first = client.post(f"/api/projects/{project_id}/generate", json={}, headers=headers)
            second = client.post(f"/api/projects/{project_id}/generate", json={}, headers=headers)

            assert first.status_code == 202, first.text
            assert second.status_code == 409, second.text
            assert "busy" in second.json()["error"]


if __name__ == "__main__":
    test_rejected_body_uses_the_same_error_shape_as_everything_else()
    test_production_settings_round_trip()
    test_parse_applies_when_there_is_nothing_to_lose()
    test_reparse_holds_back_until_the_user_accepts_losing_rendered_shots()
    test_scene_assets_are_served_through_a_fresh_signed_link()
    test_scene_terminal_progress_survives_reload()
    test_selected_media_generation_and_scene_crud()
    test_retry_status_keeps_other_failed_scenes_visible()
    test_second_generate_is_refused_while_the_first_is_running()
