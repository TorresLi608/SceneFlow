"""The storyboard breakdown, project model settings, and stopping a run.

Three things this covers that the old parse path had no equivalent of:

- a breakdown carries camera moves, transitions, durations, and motion prompts, and can
  produce either half of that on its own;
- a project pins its own model per purpose and falls back to the account when it has not;
- a run in flight can be asked to stop.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import tempfile
from typing import Any, Iterator

from fastapi.testclient import TestClient
from sqlmodel import select

from app.core import database, runs
from app.core.security import encrypt, token_for
from app.llms.registry import models
from app.llms.router import BreakdownResult, ShotDraft
from app.models import ModelConfig, User
from app.services import artifact_service
from app.utils.common import now


BROKEN_DOWN = BreakdownResult(
    shots=[
        ShotDraft(
            narration="山门在雾里若隐若现",
            visualPrompt="wide shot, misty mountain gate",
            dialogue="师父，我们到了。",
            speaker="小满",
            shotType="远景",
            cameraMove="缓慢推镜",
            transition="淡入",
            durationSeconds=6,
            videoPrompt="镜头自雾中缓缓推向山门，风吹动幡旗",
        ),
        ShotDraft(
            narration="少年抬头望向石阶",
            visualPrompt="low angle, boy looking up stone steps",
            shotType="中景",
            cameraMove="固定",
            transition="硬切",
            durationSeconds=3,
            videoPrompt="少年抬头，呼吸在冷空气里凝成白雾",
        ),
    ],
    usage={"inputTokens": 10, "outputTokens": 20},
)

CONFIGS = (
    ("script", "openai", "gpt-4o-mini"),
    ("image", "openai", "gpt-image-1"),
    ("video", "qwen", "wan2.5-i2v"),
    ("audio", "qwen", "qwen3-tts-vd-2026-01-26"),
)


async def _fake_breakdown(*_args: Any, **_kwargs: Any) -> BreakdownResult:
    return BROKEN_DOWN


async def _never_runs(*_args: Any, **_kwargs: Any) -> None:
    """Stand in for the background render so the test never reaches a provider."""


@contextmanager
def _app(directory: str) -> Iterator[tuple[TestClient, dict[str, str], int]]:
    from app.api.v1 import episodes
    from app.main import app

    original = (
        database.DB_PATH,
        artifact_service.PRIVATE_GENERATED_DIR,
        episodes.run_storyboard,
        episodes.run_tone_sheet,
        models.breakdown_script,
    )
    database.DB_PATH = str(Path(directory) / "breakdown.db")
    database._engines.pop(database.DB_PATH, None)
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "private_generated"
    episodes.run_storyboard = _never_runs
    episodes.run_tone_sheet = _never_runs
    models.breakdown_script = _fake_breakdown
    try:
        with TestClient(app) as client:
            with database.db() as session:
                user = User(
                    created_at=now(),
                    updated_at=now(),
                    username="showrunner",
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
            yield client, {"Authorization": f"Bearer {token_for(user_id)}"}, user_id
    finally:
        (
            database.DB_PATH,
            artifact_service.PRIVATE_GENERATED_DIR,
            episodes.run_storyboard,
            episodes.run_tone_sheet,
            models.breakdown_script,
        ) = original
        database._engines.pop(str(database.DB_PATH), None)


def _project(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post("/api/projects", json={"title": "都市奇缘"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["project"]


def _breakdown(client, headers, project_id, episode_id, **body) -> Any:
    payload = {"script": "第一集剧本", "target": "both", **body}
    return client.post(
        f"/api/projects/{project_id}/episodes/{episode_id}/breakdown",
        json=payload,
        headers=headers,
    )


def test_breakdown_writes_camera_transition_duration_and_motion_prompt() -> None:
    """The fields a clip needs, which the old parse produced none of."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            project = _project(client, headers)
            episode_id = project["episodes"][0]["id"]

            response = _breakdown(client, headers, project["id"], episode_id)

            assert response.status_code == 200, response.text
            assert response.json()["applied"] is True
            shots = response.json()["scenes"]
            assert len(shots) == 2
            assert shots[0]["cameraMove"] == "缓慢推镜"
            assert shots[0]["transition"] == "淡入"
            # Both prompts open with the shot's own number, re-derived from `order_num`
            # rather than trusted from the model — see `prompt_service.with_shot_label`.
            assert shots[0]["videoPrompt"] == "分镜 1：镜头自雾中缓缓推向山门，风吹动幡旗"
            assert shots[1]["videoPrompt"].startswith("分镜 2：")
            assert shots[0]["visualPrompt"].startswith("分镜 1：")
            # Seconds in, milliseconds out — the column is milliseconds like every duration
            # here, but a model asked for milliseconds guesses far worse.
            assert shots[0]["durationMs"] == 6000
            assert shots[1]["durationMs"] == 3000
            assert shots[0]["dialogue"] == "师父，我们到了。"


def test_breakdown_releases_project_lock_when_usage_recording_fails() -> None:
    """A post-provider failure must not leave the series permanently busy."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            from app.api.v1 import episodes

            project = _project(client, headers)
            episode_id = project["episodes"][0]["id"]
            original_record_usage = episodes.record_usage

            def _fail_record_usage(*_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("usage store unavailable")

            episodes.record_usage = _fail_record_usage
            try:
                response = _breakdown(client, headers, project["id"], episode_id)
            finally:
                episodes.record_usage = original_record_usage

            assert response.status_code == 502
            with database.db() as session:
                from app.models import Project

                assert session.get(Project, project["id"]).status == "idle"


def test_breakdown_failure_records_a_redacted_error_with_request_id() -> None:
    async def _invalid_response(*_args: Any, **_kwargs: Any) -> BreakdownResult:
        raise ValueError("response did not contain a JSON object; model output: [private script]")

    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            project = _project(client, headers)
            episode_id = project["episodes"][0]["id"]
            models.breakdown_script = _invalid_response

            response = _breakdown(client, headers, project["id"], episode_id)

            assert response.status_code == 502
            request_id = response.headers["X-Request-Id"]
            with database.db() as session:
                from app.models import ErrorLog

                error = session.exec(select(ErrorLog).where(ErrorLog.request_id == request_id)).one()
            assert error.error_code == "BREAKDOWN_INVALID_JSON"
            assert error.project_id == project["id"]
            assert error.episode_id == episode_id
            assert "private script" not in error.message
            with database.db() as session:
                admin_id = int(session.exec(select(User).where(User.role == "superAdmin")).one().id)
            listed = client.get(
                "/api/admin/error-logs",
                params={"requestId": request_id},
                headers={"Authorization": f"Bearer {token_for(admin_id)}"},
            )
            assert listed.status_code == 200
            assert listed.json()["errorLogs"][0]["requestId"] == request_id
            assert client.get("/api/admin/error-logs", headers=headers).status_code == 403


def test_shots_only_breakdown_leaves_the_motion_fields_empty() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            project = _project(client, headers)
            episode_id = project["episodes"][0]["id"]

            response = _breakdown(client, headers, project["id"], episode_id, target="shots")

            assert response.status_code == 200, response.text
            first = response.json()["scenes"][0]
            assert first["narration"] == "山门在雾里若隐若现"
            assert first["cameraMove"] == ""
            assert first["transition"] == ""
            assert first["videoPrompt"] == ""
            assert first["durationMs"] == 0


def test_video_pass_annotates_existing_shots_without_replacing_them() -> None:
    """Re-deriving motion must not discard frames the user already paid to render."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            project = _project(client, headers)
            episode_id = project["episodes"][0]["id"]
            created = _breakdown(client, headers, project["id"], episode_id, target="shots")
            original_ids = [scene["id"] for scene in created.json()["scenes"]]

            response = _breakdown(client, headers, project["id"], episode_id, target="video")

            assert response.status_code == 200, response.text
            shots = response.json()["scenes"]
            # Same rows, now carrying motion.
            assert [scene["id"] for scene in shots] == original_ids
            assert shots[0]["cameraMove"] == "缓慢推镜"
            assert shots[0]["durationMs"] == 6000
            assert shots[0]["narration"] == "山门在雾里若隐若现"


def test_video_pass_refuses_when_there_are_no_shots_to_annotate() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            project = _project(client, headers)
            episode_id = project["episodes"][0]["id"]

            response = _breakdown(client, headers, project["id"], episode_id, target="video")

            assert response.status_code == 400, response.text


def test_breakdown_reports_what_a_resplit_would_discard_before_doing_it() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            project = _project(client, headers)
            project_id = project["id"]
            episode_id = project["episodes"][0]["id"]
            first = _breakdown(client, headers, project_id, episode_id)
            scene_id = first.json()["scenes"][0]["id"]
            # Give one shot a rendered frame, so re-splitting has something to lose.
            with database.db() as session:
                from app.models import Scene

                scene = session.get(Scene, scene_id)
                scene.image_path = "projects/x/y.png"
                session.add(scene)

            held = _breakdown(client, headers, project_id, episode_id)
            assert held.status_code == 200, held.text
            assert held.json()["applied"] is False
            assert held.json()["discardsGeneratedScenes"] == 1

            confirmed = _breakdown(client, headers, project_id, episode_id, replaceAll=True)
            assert confirmed.json()["applied"] is True


def test_selected_references_reach_the_model_and_an_empty_selection_is_valid() -> None:
    """Ticking a character is what turns "a woman" into "参照《…》三面图" in the prompt."""
    captured: list[str] = []

    async def _capture(*args: Any, **_kwargs: Any) -> BreakdownResult:
        # (provider, api_key, model, system, user, base_url)
        captured.append(args[4])
        return BROKEN_DOWN

    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            models.breakdown_script = _capture
            project = _project(client, headers)
            project_id = project["id"]
            episode_id = project["episodes"][0]["id"]
            character = client.post(
                f"/api/projects/{project_id}/characters",
                json={"name": "小满", "description": "十六岁，倔强"},
                headers=headers,
            ).json()["character"]

            _breakdown(
                client,
                headers,
                project_id,
                episode_id,
                references={"characterIds": [character["id"]]},
            )
            assert "小满" in captured[-1]
            # No drawn sheet yet, so the model is told to reason from the written setting.
            assert "没有设定图" in captured[-1]

            _breakdown(client, headers, project_id, episode_id, replaceAll=True)
            # Selecting nothing is a real choice, not an unfinished form.
            assert "没有提供任何角色" in captured[-1]


def test_project_models_resolve_project_first_then_the_account() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, user_id):
            project_id = _project(client, headers)["id"]

            listed = client.get(f"/api/projects/{project_id}/models", headers=headers)
            assert listed.status_code == 200, listed.text
            models_payload = listed.json()["models"]
            # Nothing pinned yet, so every purpose falls through to the account default.
            assert models_payload["image"]["model"] == "gpt-image-1"
            assert models_payload["image"]["isProjectPick"] is False
            assert models_payload["image"]["capabilities"]["maxReferenceImages"] == 4
            assert models_payload["video"]["capabilities"]["maxReferenceImages"] >= 1
            # Credentials never leave the server.
            assert "apiKey" not in models_payload["image"]

            with database.db() as session:
                from sqlmodel import select

                other = ModelConfig(
                    created_at=now(),
                    updated_at=now(),
                    user_id=user_id,
                    source="user",
                    provider="qwen",
                    encrypted_key=encrypt("sk-test-key-value"),
                    is_active=False,
                    is_enabled=True,
                    purpose="image",
                    model_name="wan2.7-image",
                )
                session.add(other)
                session.flush()
                pinned_id = int(other.id)
                assert session.exec(select(ModelConfig)).first() is not None

            patched = client.patch(
                f"/api/projects/{project_id}",
                json={"modelSettings": {"imageConfigId": pinned_id, "imageResolution": "4K"}},
                headers=headers,
            )
            assert patched.status_code == 200, patched.text
            assert patched.json()["project"]["modelSettings"]["imageResolution"] == "4K"

            repeated = client.get(f"/api/projects/{project_id}/models", headers=headers).json()["models"]
            assert repeated["image"]["model"] == "wan2.7-image"
            assert repeated["image"]["isProjectPick"] is True

            # 0 clears the pick; null would read as "leave this field alone".
            client.patch(
                f"/api/projects/{project_id}",
                json={"modelSettings": {"imageConfigId": 0}},
                headers=headers,
            )
            cleared = client.get(f"/api/projects/{project_id}/models", headers=headers).json()["models"]
            assert cleared["image"]["model"] == "gpt-image-1"
            assert cleared["image"]["isProjectPick"] is False


def test_cancelling_with_nothing_running_is_not_an_error() -> None:
    """The user clicked stop on a run that had just finished; that is not a failure."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            project_id = _project(client, headers)["id"]

            response = client.post(f"/api/projects/{project_id}/cancel", headers=headers)

            assert response.status_code == 200, response.text
            assert response.json()["canceled"] is False


def test_cancelling_signals_the_registered_run() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            project_id = _project(client, headers)["id"]
            event = runs.register(project_id)
            try:
                response = client.post(f"/api/projects/{project_id}/cancel", headers=headers)

                assert response.status_code == 200, response.text
                assert response.json()["canceled"] is True
                assert event.is_set()
            finally:
                runs.release(project_id, event)


def test_releasing_a_superseded_run_leaves_the_new_flag_alone() -> None:
    """A cancelled run unwinding must not disarm the run the user started after it."""
    first = runs.register("proj_x")
    second = runs.register("proj_x")
    runs.release("proj_x", first)

    assert runs.cancel("proj_x") is True
    assert second.is_set()
    runs.release("proj_x", second)
    assert runs.cancel("proj_x") is False


def test_tone_sheet_is_its_own_step_and_needs_shots() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            project = _project(client, headers)
            project_id = project["id"]
            episode_id = project["episodes"][0]["id"]

            empty = client.post(
                f"/api/projects/{project_id}/episodes/{episode_id}/tone-sheet",
                json={},
                headers=headers,
            )
            assert empty.status_code == 400, empty.text

            _breakdown(client, headers, project_id, episode_id)
            response = client.post(
                f"/api/projects/{project_id}/episodes/{episode_id}/tone-sheet",
                json={},
                headers=headers,
            )
            assert response.status_code == 202, response.text
            assert response.json()["regeneratesToneSheet"] is True


if __name__ == "__main__":
    test_breakdown_writes_camera_transition_duration_and_motion_prompt()
    test_breakdown_releases_project_lock_when_usage_recording_fails()
    test_breakdown_failure_records_a_redacted_error_with_request_id()
    test_shots_only_breakdown_leaves_the_motion_fields_empty()
    test_video_pass_annotates_existing_shots_without_replacing_them()
    test_video_pass_refuses_when_there_are_no_shots_to_annotate()
    test_breakdown_reports_what_a_resplit_would_discard_before_doing_it()
    test_selected_references_reach_the_model_and_an_empty_selection_is_valid()
    test_project_models_resolve_project_first_then_the_account()
    test_cancelling_with_nothing_running_is_not_an_error()
    test_cancelling_signals_the_registered_run()
    test_releasing_a_superseded_run_leaves_the_new_flag_alone()
    test_tone_sheet_is_its_own_step_and_needs_shots()
