"""Project-wide style: persistence, model hand-offs, and unchanged editable prompts."""

import asyncio
from contextlib import nullcontext
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.v1.projects import _scene_payloads
from app.core import database
from app.llms.registry import models
from app.llms.router import ImageResult
from app.models import Episode, Project, Scene
from app.services.generation_service import build_image_prompt
from app.services.job_handlers import draft_reference_prompt, draw_reference_image
from app.services.prompt_service import VISUAL_STYLE_PROMPTS, visual_style_prompt
from tests.test_projects_api import _app
from tests.test_project_cover import PNG_BYTES
from tests.test_storyboard_api import Recorder, _app as storyboard_app, _project_with_shots
from tests.test_video_service import _render_scene_video


def test_style_round_trip_and_model_handoffs() -> None:
    with tempfile.TemporaryDirectory() as directory, _app(directory) as (client, headers):
        response = client.post("/api/projects", json={"title": "Style check"}, headers=headers)
        assert response.status_code == 201, response.text
        project = response.json()["project"]
        assert project["productionSettings"]["visualStyle"] == "cinematic"
        project_id = project["id"]
        parsed = client.post(f"/api/projects/{project_id}/parse", json={"script": "A scene"}, headers=headers).json()
        for style in VISUAL_STYLE_PROMPTS:
            updated = client.patch(f"/api/projects/{project_id}", json={
                "productionSettings": {"visualStyle": style, "stylePrompt": "柔和逆光"},
            }, headers=headers)
            assert updated.status_code == 200, updated.text
            settings = updated.json()["project"]["productionSettings"]
            assert settings["visualStyle"] == style and settings["stylePrompt"] == "柔和逆光"
            listed = client.get("/api/projects", headers=headers).json()["projects"][0]
            assert listed["productionSettings"]["visualStyle"] == style
            with database.db() as session:
                row = session.get(Project, project_id)
                episode = session.get(Episode, parsed["episodeId"])
                scenes = list(session.exec(database.select(Scene).where(Scene.project_id == project_id)).all())
                payload = _scene_payloads(session, row, episode.episode_number, scenes)[0]
            assert VISUAL_STYLE_PROMPTS[style] in build_image_prompt(payload)
            assert "cinematic anime" not in build_image_prompt(payload)
            image = AsyncMock(return_value=ImageResult(data=PNG_BYTES, format="png"))
            with patch.object(models, "generate_image", image):
                cover = client.post("/api/projects/cover/generate", json={
                    "prompt": "A poster", "visualStyle": style, "stylePrompt": "柔和逆光",
                }, headers=headers)
            assert cover.status_code == 200, cover.text
            assert VISUAL_STYLE_PROMPTS[style] in image.call_args.args[2]

        invalid = client.patch(f"/api/projects/{project_id}", json={
            "title": "must not persist", "productionSettings": {"visualStyle": "unknown"},
        }, headers=headers)
        assert invalid.status_code == 422, invalid.text
        assert client.get("/api/projects", headers=headers).json()["projects"][0]["title"] == "Style check"
        # null leaves the saved style alone; explicit empty restores legacy custom-only mode.
        unchanged = client.patch(f"/api/projects/{project_id}", json={
            "description": "updated", "productionSettings": {"visualStyle": None},
        }, headers=headers)
        assert unchanged.json()["project"]["productionSettings"]["visualStyle"] == "3d"
        cleared = client.patch(f"/api/projects/{project_id}/production-settings", json={
            "visualStyle": "", "stylePrompt": "水墨写意",
        }, headers=headers)
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["project"]["productionSettings"]["visualStyle"] == ""
        assert visual_style_prompt("", "水墨写意") == "水墨写意"


def test_tone_storyboard_and_video_use_the_saved_style() -> None:
    recorder = Recorder()
    with tempfile.TemporaryDirectory() as directory, storyboard_app(directory, recorder) as (client, headers):
        project_id, episode_id = _project_with_shots(client, headers)
        updated = client.patch(f"/api/projects/{project_id}/production-settings", json={"visualStyle": "3d"}, headers=headers)
        assert updated.status_code == 200, updated.text
        # Execute the background owner directly to inspect both tone and shot calls.
        from app.api.v1.episodes import _plan
        from app.services.storyboard_service import run_storyboard
        from app.services.config_service import project_model_config
        with database.db() as session:
            project = session.get(Project, project_id)
            episode = session.get(Episode, episode_id)
            scenes = list(session.exec(database.select(Scene).where(Scene.episode_id == episode_id).order_by(Scene.order_num)).all())
            config = project_model_config(session, project.user_id, project, "image", "style test")
            plan = _plan(project, episode, scenes, [], merge_references=False, regenerate=True, max_reference_images=4)
            user_id = project.user_id
        asyncio.run(run_storyboard(plan, config, user_id))
        assert len(recorder.calls) >= 2
        assert all(VISUAL_STYLE_PROMPTS["3d"] in call["prompt"] for call in recorder.calls)
    style = visual_style_prompt("anime")
    succeeded, request = _render_scene_video(
        {"quality": "720p", "aspectRatio": None, "fps": None, "duration": 5, "promptExtend": False,
         "explicitVideoReferences": True},
        [{"name": "frame.png", "data": "data:image/png;base64,aW1hZ2U="}], style_prompt=style,
    )
    assert succeeded and style in request["prompt"] and "camera move" in request["prompt"]


def test_reference_jobs_apply_style_without_rewriting_editable_prompt() -> None:
    project = SimpleNamespace(visual_style="realistic", style_prompt="柔和逆光")
    # Stop after the model boundary; this test does not need an artifact/DB fixture.
    class ModelBoundary(Exception):
        pass
    draw = AsyncMock(side_effect=ModelBoundary())
    job = {"projectId": "p", "userId": 1, "input": {"target": "prop", "prompt": "Bronze lock"}}
    with (
        patch("app.services.job_handlers.db", side_effect=lambda: nullcontext(object())),
        patch("app.services.job_handlers.owned_project", return_value=project),
        patch("app.services.job_handlers.image_config", return_value={}),
        patch("app.services.job_handlers.image_options", return_value=("1:1", "2K")),
        patch("app.services.job_handlers.draw_reference", draw),
    ):
        try:
            asyncio.run(draw_reference_image(job))
        except ModelBoundary:
            pass
    assert VISUAL_STYLE_PROMPTS["realistic"] in draw.call_args.args[2]
    assert "Bronze lock" in draw.call_args.args[2]
    draft = AsyncMock(return_value="reviewable draft")
    with (
        patch("app.services.job_handlers.db", side_effect=lambda: nullcontext(object())),
        patch("app.services.job_handlers.owned_project", return_value=project),
        patch("app.services.job_handlers.script_config", return_value={}),
        patch("app.services.job_handlers.draft_prompt", draft),
    ):
        result = asyncio.run(draft_reference_prompt({**job, "input": {"target": "prop", "userText": "Bronze lock"}}))
    assert result["prompt"] == "reviewable draft"
    assert VISUAL_STYLE_PROMPTS["realistic"] in draft.call_args.args[3]


if __name__ == "__main__":
    test_style_round_trip_and_model_handoffs()
    test_tone_storyboard_and_video_use_the_saved_style()
    test_reference_jobs_apply_style_without_rewriting_editable_prompt()
    print("project visual style checks passed")
