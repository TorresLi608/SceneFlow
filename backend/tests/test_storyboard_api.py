"""Storyboard rendering: the tone sheet anchors the episode, then each shot renders against it."""

from __future__ import annotations

import base64
from pathlib import Path
import tempfile
import threading
from typing import Any, Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.core import database
from app.core.security import encrypt, token_for
from app.llms.router import ImageResult
from app.models import Episode, ModelConfig, Project, Scene, User
from app.services import artifact_service
from app.services.generation_service import MAX_REFERENCE_IMAGES
from app.services.storyboard_service import build_context_references
from app.utils.common import now


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

CONFIGS = (
    ("script", "openai", "gpt-4o-mini"),
    ("image", "openai", "gpt-image-1"),
)


class Recorder:
    """Captures every provider call so the order and the references can be asserted on."""

    def __init__(self, fail_first: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_first = fail_first
        self.done = threading.Event()

    async def generate_image(self, _key: str, _model: str, prompt: str, *_args: Any, **_kwargs: Any) -> ImageResult:
        self.calls.append({"kind": "generate", "prompt": prompt, "references": []})
        if self.fail_first and len(self.calls) == 1:
            raise ValueError("provider is down")
        return ImageResult(data=PNG_BYTES, format="png")

    async def edit_image(
        self, _key: str, _model: str, prompt: str, references: list[Any], *_args: Any, **_kwargs: Any
    ) -> ImageResult:
        self.calls.append({"kind": "edit", "prompt": prompt, "references": list(references)})
        if self.fail_first and len(self.calls) == 1:
            raise ValueError("provider is down")
        return ImageResult(data=PNG_BYTES, format="png")


@contextmanager
def _app(directory: str, recorder: Recorder) -> Iterator[tuple[TestClient, dict[str, str]]]:
    from app.services import storyboard_service
    from app.main import app

    original = (
        database.DB_PATH,
        artifact_service.PRIVATE_GENERATED_DIR,
        storyboard_service.models.generate_image,
        storyboard_service.models.edit_image,
    )
    database.DB_PATH = str(Path(directory) / "storyboard.db")
    database._engines.pop(database.DB_PATH, None)
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "private_generated"
    storyboard_service.models.generate_image = recorder.generate_image
    storyboard_service.models.edit_image = recorder.edit_image
    try:
        with TestClient(app) as client:
            with database.db() as session:
                user = User(created_at=now(), updated_at=now(), username="board", password="x", role="user", is_disabled=False)
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
            storyboard_service.models.generate_image,
            storyboard_service.models.edit_image,
        ) = original
        database._engines.pop(str(database.DB_PATH), None)


def _project_with_shots(client: TestClient, headers: dict[str, str], shots: int = 2) -> tuple[str, str]:
    created = client.post("/api/projects", json={"title": "山海"}, headers=headers)
    assert created.status_code == 201, created.text
    project = created.json()["project"]
    project_id, episode_id = project["id"], project["currentEpisodeId"]
    with database.db() as session:
        episode = session.get(Episode, episode_id)
        episode.source_text = "少年上山求道。"
        session.add(episode)
        for index in range(shots):
            session.add(
                Scene(
                    id=f"scene_{index}",
                    created_at=now(),
                    updated_at=now(),
                    project_id=project_id,
                    episode_id=episode_id,
                    order_num=index + 1,
                    narration=f"第 {index + 1} 镜",
                    image_status="idle",
                )
            )
    return project_id, episode_id


def _wait_idle(client: TestClient, headers: dict[str, str], project_id: str) -> str:
    """The run is a background task; poll until the project lock is released."""
    for _ in range(200):
        status = next(
            item["status"]
            for item in client.get("/api/projects", headers=headers).json()["projects"]
            if item["id"] == project_id
        )
        if status not in {"generating", "parsing", "video_generating"}:
            return status
        threading.Event().wait(0.05)
    raise AssertionError("storyboard run did not finish")


def _sheet(project_id: str) -> str:
    return artifact_service.store_artifact("characters", project_id, "cast.png", PNG_BYTES)


def test_the_tone_sheet_is_rendered_before_any_shot() -> None:
    """The whole point of the anchor: it cannot come after the frames it is meant to fix."""
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory, recorder) as (client, headers):
            project_id, episode_id = _project_with_shots(client, headers)

            started = client.post(
                f"/api/projects/{project_id}/episodes/{episode_id}/storyboard", json={}, headers=headers
            )

            assert started.status_code == 202, started.text
            assert started.json()["shotCount"] == 2
            assert started.json()["regeneratesToneSheet"] is True
            assert _wait_idle(client, headers, project_id) == "done"

            # One tone sheet, then one call per shot.
            assert len(recorder.calls) == 3
            assert "基调总览图" in recorder.calls[0]["prompt"]
            assert "第 1/2 个分镜" in recorder.calls[1]["prompt"]
            assert "第 2/2 个分镜" in recorder.calls[2]["prompt"]

            episode = client.get(f"/api/projects/{project_id}/episodes/{episode_id}", headers=headers).json()["episode"]
            assert episode["toneImageStatus"] == "success"
            assert episode["toneImageUrl"]
            assert all(scene["image"]["url"] for scene in episode["scenes"])


def test_each_shot_carries_the_anchor_and_its_predecessor() -> None:
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory, recorder) as (client, headers):
            project_id, episode_id = _project_with_shots(client, headers, shots=3)
            with database.db() as session:
                project = session.get(Project, project_id)
                project.character_sheet_path = _sheet(project_id)
                project.prop_sheet_path = _sheet(project_id)
                session.add(project)

            client.post(f"/api/projects/{project_id}/episodes/{episode_id}/storyboard", json={}, headers=headers)
            assert _wait_idle(client, headers, project_id) == "done"

            shots = recorder.calls[1:]
            # Tone sheet + merged context for the first shot; the second onward also carry
            # the previous render, which is what holds scene continuity.
            assert len(shots[0]["references"]) == 2
            assert len(shots[1]["references"]) == 3
            assert all(len(call["references"]) <= MAX_REFERENCE_IMAGES for call in shots)


def test_unmerged_references_arrive_separately() -> None:
    """Merging trades resolution for reference slots; the caller gets to choose."""
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory, recorder) as (client, headers):
            project_id, episode_id = _project_with_shots(client, headers, shots=1)
            with database.db() as session:
                project = session.get(Project, project_id)
                project.character_sheet_path = _sheet(project_id)
                project.prop_sheet_path = _sheet(project_id)
                session.add(project)

            client.post(
                f"/api/projects/{project_id}/episodes/{episode_id}/storyboard",
                json={"mergeReferences": False},
                headers=headers,
            )
            assert _wait_idle(client, headers, project_id) == "done"

            # Tone sheet + cast + props, rather than tone sheet + one merged context image.
            assert len(recorder.calls[1]["references"]) == 3


def test_a_failed_tone_sheet_stops_the_run_before_it_bills_for_shots() -> None:
    recorder = Recorder(fail_first=True)
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory, recorder) as (client, headers):
            project_id, episode_id = _project_with_shots(client, headers)

            client.post(f"/api/projects/{project_id}/episodes/{episode_id}/storyboard", json={}, headers=headers)
            assert _wait_idle(client, headers, project_id) == "failed"

            # Only the tone sheet was attempted: rendering shots without an anchor is the
            # incoherence this path exists to prevent.
            assert len(recorder.calls) == 1
            episode = client.get(f"/api/projects/{project_id}/episodes/{episode_id}", headers=headers).json()["episode"]
            assert episode["toneImageStatus"] == "error"
            assert "基调图" in episode["errorMessage"]
            assert all(scene["image"]["url"] is None for scene in episode["scenes"])


def test_rerunning_reuses_the_anchor_unless_asked_to_resample() -> None:
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory, recorder) as (client, headers):
            project_id, episode_id = _project_with_shots(client, headers, shots=1)
            client.post(f"/api/projects/{project_id}/episodes/{episode_id}/storyboard", json={}, headers=headers)
            _wait_idle(client, headers, project_id)
            after_first = len(recorder.calls)

            reused = client.post(
                f"/api/projects/{project_id}/episodes/{episode_id}/storyboard", json={}, headers=headers
            )
            _wait_idle(client, headers, project_id)

            assert reused.json()["regeneratesToneSheet"] is False
            # One more call, the shot — not two. Resampling the look would have thrown away
            # the frames the user already approved.
            assert len(recorder.calls) == after_first + 1

            client.post(
                f"/api/projects/{project_id}/episodes/{episode_id}/storyboard",
                json={"regenerate": True},
                headers=headers,
            )
            _wait_idle(client, headers, project_id)
            assert len(recorder.calls) == after_first + 3


def test_the_previous_episodes_anchor_carries_across_the_boundary() -> None:
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory, recorder) as (client, headers):
            project_id, first_id = _project_with_shots(client, headers, shots=1)
            with database.db() as session:
                first = session.get(Episode, first_id)
                first.tone_image_path = _sheet(project_id)
                session.add(first)
            second = client.post(
                f"/api/projects/{project_id}/episodes", json={"title": "第二集"}, headers=headers
            ).json()["episode"]
            with database.db() as session:
                session.add(
                    Scene(
                        id="scene_second",
                        created_at=now(),
                        updated_at=now(),
                        project_id=project_id,
                        episode_id=second["id"],
                        order_num=1,
                        narration="第二集第一镜",
                        image_status="idle",
                    )
                )

            started = client.post(
                f"/api/projects/{project_id}/episodes/{second['id']}/storyboard",
                json={"previousEpisodeId": first_id, "mergeReferences": False},
                headers=headers,
            )
            assert _wait_idle(client, headers, project_id) == "done"

            assert started.json()["referenceCount"] == 1
            # The previous episode's anchor reached the tone sheet, so a series does not
            # restyle itself between episodes.
            assert len(recorder.calls[0]["references"]) == 1


def test_an_episode_cannot_reference_itself() -> None:
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory, recorder) as (client, headers):
            project_id, episode_id = _project_with_shots(client, headers, shots=1)

            refused = client.post(
                f"/api/projects/{project_id}/episodes/{episode_id}/storyboard",
                json={"previousEpisodeId": episode_id},
                headers=headers,
            )

            assert refused.status_code == 400, refused.text
            assert recorder.calls == []


def test_rendering_an_empty_episode_says_so() -> None:
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory, recorder) as (client, headers):
            created = client.post("/api/projects", json={"title": "空的"}, headers=headers).json()["project"]

            refused = client.post(
                f"/api/projects/{created['id']}/episodes/{created['currentEpisodeId']}/storyboard",
                json={},
                headers=headers,
            )

            assert refused.status_code == 400, refused.text
            assert "split the script" in refused.json()["error"]


def test_context_references_merge_into_one_slot() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = artifact_service.PRIVATE_GENERATED_DIR
        artifact_service.PRIVATE_GENERATED_DIR = Path(directory)
        try:
            sources = [(artifact_service.store_artifact("x", "p", f"{index}.png", PNG_BYTES), f"图{index}") for index in range(3)]

            merged = build_context_references(sources, merge=True)
            separate = build_context_references(sources, merge=False)
            missing = build_context_references([("characters/gone/x.png", "没了")], merge=True)
        finally:
            artifact_service.PRIVATE_GENERATED_DIR = original

    assert len(merged) == 1
    assert len(separate) == 3
    # An unreadable source costs consistency, not the render.
    assert missing == []


if __name__ == "__main__":
    test_the_tone_sheet_is_rendered_before_any_shot()
    test_each_shot_carries_the_anchor_and_its_predecessor()
    test_unmerged_references_arrive_separately()
    test_a_failed_tone_sheet_stops_the_run_before_it_bills_for_shots()
    test_rerunning_reuses_the_anchor_unless_asked_to_resample()
    test_the_previous_episodes_anchor_carries_across_the_boundary()
    test_an_episode_cannot_reference_itself()
    test_rendering_an_empty_episode_says_so()
    test_context_references_merge_into_one_slot()
    print("test_storyboard_api ok")
