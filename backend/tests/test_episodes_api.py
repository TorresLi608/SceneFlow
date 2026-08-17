"""The episode layer over the real ASGI app: a series holds its content in episodes."""

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
from app.models import Episode, ModelConfig, Scene, User
from app.services import artifact_service
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
    database.DB_PATH = str(Path(directory) / "episodes.db")
    database._engines.pop(database.DB_PATH, None)
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "private_generated"
    projects.run_generation = _fake_run_generation
    models.parse_script = _fake_parse_script
    try:
        with TestClient(app) as client:
            with database.db() as session:
                user = User(created_at=now(), updated_at=now(), username="showrunner", password="x", role="user", is_disabled=False)
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


def _create_project(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post("/api/projects", json={"title": "都市奇缘"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["project"]


def test_a_new_series_starts_with_episode_one() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers)

            # A series with no episode could not hold a single shot, so it never exists.
            assert [episode["episodeNumber"] for episode in project["episodes"]] == [1]
            assert project["currentEpisodeId"] == project["episodes"][0]["id"]


def test_added_episodes_number_upwards() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _create_project(client, headers)["id"]

            second = client.post(f"/api/projects/{project_id}/episodes", json={"title": "重逢"}, headers=headers)
            third = client.post(f"/api/projects/{project_id}/episodes", json={"title": "新的一集"}, headers=headers)

            assert second.status_code == 201, second.text
            assert second.json()["episode"]["episodeNumber"] == 2
            assert second.json()["episode"]["title"] == "重逢"
            # No title given, so it names itself after its number.
            assert third.json()["episode"]["title"] == "新的一集"
            listed = client.get(f"/api/projects/{project_id}/episodes", headers=headers).json()["episodes"]
            assert [episode["episodeNumber"] for episode in listed] == [1, 2, 3]


def test_parsing_an_episode_leaves_the_rest_of_the_series_alone() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers)
            project_id = project["id"]
            first_id = project["episodes"][0]["id"]
            client.post(f"/api/projects/{project_id}/parse", json={"script": "第一集剧本"}, headers=headers)
            second_id = client.post(f"/api/projects/{project_id}/episodes", json={"title": "新的一集"}, headers=headers).json()["episode"]["id"]

            parsed = client.post(
                f"/api/projects/{project_id}/parse",
                json={"script": "第二集剧本", "episodeId": second_id},
                headers=headers,
            )

            assert parsed.status_code == 200, parsed.text
            assert parsed.json()["episodeId"] == second_id
            # Episode 1's storyboard survived a parse aimed at episode 2.
            first = client.get(f"/api/projects/{project_id}/episodes/{first_id}", headers=headers).json()["episode"]
            second = client.get(f"/api/projects/{project_id}/episodes/{second_id}", headers=headers).json()["episode"]
            assert len(first["scenes"]) == len(PARSED.scenes)
            assert len(second["scenes"]) == len(PARSED.scenes)
            assert {scene["id"] for scene in first["scenes"]}.isdisjoint({scene["id"] for scene in second["scenes"]})
            # Each episode numbers its own shots from 1.
            assert [scene["order"] for scene in second["scenes"]] == [1, 2]
            assert second["sourceText"] == "第二集剧本"


def test_parse_defaults_to_the_newest_episode() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers)
            project_id = project["id"]
            first_id = project["episodes"][0]["id"]
            second_id = client.post(f"/api/projects/{project_id}/episodes", json={"title": "新的一集"}, headers=headers).json()["episode"]["id"]

            parsed = client.post(f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers)

            assert parsed.json()["episodeId"] == second_id
            first = client.get(f"/api/projects/{project_id}/episodes/{first_id}", headers=headers).json()["episode"]
            assert first["scenes"] == []


def test_generate_renders_only_the_target_episode() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers)
            project_id = project["id"]
            first_id = project["episodes"][0]["id"]
            client.post(f"/api/projects/{project_id}/parse", json={"script": "第一集"}, headers=headers)
            second_id = client.post(f"/api/projects/{project_id}/episodes", json={"title": "新的一集"}, headers=headers).json()["episode"]["id"]

            # Episode 2 has no shots yet, so there is nothing to render.
            empty = client.post(f"/api/projects/{project_id}/generate", json={"episodeId": second_id}, headers=headers)
            assert empty.status_code == 400, empty.text

            started = client.post(f"/api/projects/{project_id}/generate", json={"episodeId": first_id}, headers=headers)

            assert started.status_code == 202, started.text
            assert started.json()["episodeId"] == first_id
            assert started.json()["sceneCount"] == len(PARSED.scenes)
            with database.db() as session:
                status = session.exec(database.select(Episode.status).where(Episode.id == first_id)).first()
            assert status == "generating"


def test_deleting_an_episode_takes_its_shots_with_it() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers)
            project_id = project["id"]
            first_id = project["episodes"][0]["id"]
            client.post(f"/api/projects/{project_id}/parse", json={"script": "第一集"}, headers=headers)

            removed = client.delete(f"/api/projects/{project_id}/episodes/{first_id}", headers=headers)

            assert removed.status_code == 204, removed.text
            assert client.get(f"/api/projects/{project_id}/episodes", headers=headers).json()["episodes"] == []
            with database.db() as session:
                live = session.exec(
                    database.select(Scene).where(Scene.episode_id == first_id, Scene.deleted_at.is_(None))
                ).all()
            # Shots are the episode's content; leaving them would strand unreachable rows.
            assert list(live) == []


def test_an_episode_cannot_be_deleted_out_from_under_a_running_project() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers)
            project_id = project["id"]
            first_id = project["episodes"][0]["id"]
            client.post(f"/api/projects/{project_id}/parse", json={"script": "第一集"}, headers=headers)
            client.post(f"/api/projects/{project_id}/generate", json={}, headers=headers)

            refused = client.delete(f"/api/projects/{project_id}/episodes/{first_id}", headers=headers)

            assert refused.status_code == 409, refused.text
            assert "busy" in refused.json()["error"]


def test_reorder_is_scoped_to_one_episode() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project = _create_project(client, headers)
            project_id = project["id"]
            first_id = project["episodes"][0]["id"]
            client.post(f"/api/projects/{project_id}/parse", json={"script": "第一集"}, headers=headers)
            second_id = client.post(f"/api/projects/{project_id}/episodes", json={"title": "新的一集"}, headers=headers).json()["episode"]["id"]
            client.post(f"/api/projects/{project_id}/parse", json={"script": "第二集", "episodeId": second_id}, headers=headers)
            first = client.get(f"/api/projects/{project_id}/episodes/{first_id}", headers=headers).json()["episode"]
            ids = [scene["id"] for scene in first["scenes"]]

            flipped = client.patch(
                f"/api/projects/{project_id}/scenes/reorder",
                json={"sceneIds": list(reversed(ids)), "episodeId": first_id},
                headers=headers,
            )

            assert flipped.status_code == 200, flipped.text
            reordered = client.get(f"/api/projects/{project_id}/episodes/{first_id}", headers=headers).json()["episode"]
            assert [scene["id"] for scene in reordered["scenes"]] == list(reversed(ids))

            # A list spanning episodes renumbers shots the caller never saw, so it is refused.
            second = client.get(f"/api/projects/{project_id}/episodes/{second_id}", headers=headers).json()["episode"]
            mixed = client.patch(
                f"/api/projects/{project_id}/scenes/reorder",
                json={"sceneIds": ids + [second["scenes"][0]["id"]], "episodeId": first_id},
                headers=headers,
            )
            assert mixed.status_code == 400, mixed.text


def test_storyboard_fields_survive_a_round_trip() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _create_project(client, headers)["id"]
            parsed = client.post(f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers)
            scene_id = parsed.json()["scenes"][0]["id"]

            updated = client.patch(
                f"/api/projects/{project_id}/scenes/{scene_id}",
                json={
                    "dialogue": "你终于来了。",
                    "shotType": "过肩",
                    "cameraMove": "handheld push-in",
                    "durationMs": 3200,
                    "subtitleText": "你终于来了。",
                    "isLocked": True,
                },
                headers=headers,
            )

            assert updated.status_code == 200, updated.text
            scene = updated.json()["scene"]
            assert scene["dialogue"] == "你终于来了。"
            assert scene["shotType"] == "过肩"
            assert scene["cameraMove"] == "handheld push-in"
            assert scene["durationMs"] == 3200
            assert scene["isLocked"] is True

            # And they are persisted, not just echoed back.
            reread = client.get(f"/api/projects/{project_id}/episodes/{scene['episodeId']}", headers=headers)
            stored = next(item for item in reread.json()["episode"]["scenes"] if item["id"] == scene_id)
            assert stored["subtitleText"] == "你终于来了。"
            assert stored["isLocked"] is True

            # An unknown storyboard field is a 422, not a silently dropped edit.
            rejected = client.patch(
                f"/api/projects/{project_id}/scenes/{scene_id}",
                json={"shotTyp": "特写"},
                headers=headers,
            )
            assert rejected.status_code == 422, rejected.text


def test_locking_a_shot_is_an_edit_a_patch_can_undo() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _create_project(client, headers)["id"]
            parsed = client.post(f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers)
            scene_id = parsed.json()["scenes"][0]["id"]
            client.patch(f"/api/projects/{project_id}/scenes/{scene_id}", json={"isLocked": True}, headers=headers)

            unlocked = client.patch(
                f"/api/projects/{project_id}/scenes/{scene_id}",
                json={"isLocked": False},
                headers=headers,
            )

            # False is a value, not an absent field: the old "is not None" filter dropped it.
            assert unlocked.status_code == 200, unlocked.text
            assert unlocked.json()["scene"]["isLocked"] is False


if __name__ == "__main__":
    test_a_new_series_starts_with_episode_one()
    test_added_episodes_number_upwards()
    test_parsing_an_episode_leaves_the_rest_of_the_series_alone()
    test_parse_defaults_to_the_newest_episode()
    test_generate_renders_only_the_target_episode()
    test_deleting_an_episode_takes_its_shots_with_it()
    test_an_episode_cannot_be_deleted_out_from_under_a_running_project()
    test_reorder_is_scoped_to_one_episode()
    test_storyboard_fields_survive_a_round_trip()
    test_locking_a_shot_is_an_edit_a_patch_can_undo()
