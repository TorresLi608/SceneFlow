"""The series bible: variant resolution, shot casting, and what reaches the providers."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any, Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.core import database
from app.core.security import encrypt, token_for
from app.llms.registry import models
from app.llms.router import ImageResult, ParseResult, SceneDraft
from app.models import Character, CharacterVariant, ModelConfig, Scene, User
from app.services import artifact_service
from app.services.character_service import resolve_character
from app.services.generation_service import (
    MAX_REFERENCE_IMAGES,
    build_image_prompt,
    character_references,
    spoken_line,
    voice_config,
)
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

EDGE = {"provider": "edge", "model": "zh-CN-XiaoxiaoNeural", "apiKey": "", "baseUrl": ""}


async def _fake_parse_script(*_args: Any, **_kwargs: Any) -> ParseResult:
    return PARSED


async def _fake_run_generation(*_args: Any, **_kwargs: Any) -> None:
    """Stand in for the real fan-out so the test never reaches a provider."""


@contextmanager
def _app(directory: str) -> Iterator[tuple[TestClient, dict[str, str]]]:
    from app.api.v1 import projects
    from app.main import app

    original = (database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR, projects.run_generation, models.parse_script)
    database.DB_PATH = str(Path(directory) / "characters.db")
    database._engines.pop(database.DB_PATH, None)
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "private_generated"
    projects.run_generation = _fake_run_generation
    models.parse_script = _fake_parse_script
    try:
        with TestClient(app) as client:
            with database.db() as session:
                user = User(created_at=now(), updated_at=now(), username="bible", password="x", role="user", is_disabled=False)
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
                            is_verified=True,
                            purpose=purpose,
                            model_name=model_name,
                        )
                    )
            yield client, {"Authorization": f"Bearer {token_for(user_id)}"}
    finally:
        database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR, projects.run_generation, models.parse_script = original
        database._engines.pop(str(database.DB_PATH), None)


def _project(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/projects", json={"title": "山海"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["project"]["id"]


def _character(client: TestClient, headers: dict[str, str], project_id: str, **body: Any) -> dict[str, Any]:
    payload = {"name": "林小满", "appearancePrompt": "短发少年，灰布长衫", **body}
    response = client.post(f"/api/projects/{project_id}/characters", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["character"]


def _card(**values: Any) -> Character:
    return Character(
        id="char_1",
        project_id="proj_1",
        name="林小满",
        appearance_prompt="短发少年，灰布长衫",
        reference_image_path="projects/p/base.png",
        voice_provider="edge",
        voice_model="zh-CN-YunxiNeural",
        **values,
    )


def test_a_character_without_variants_is_itself_in_every_episode() -> None:
    resolved = resolve_character(_card(), [], episode_number=7)

    assert resolved.appearance_prompt == "短发少年，灰布长衫"
    assert resolved.voice_model == "zh-CN-YunxiNeural"


def test_a_variant_takes_over_only_inside_its_episode_range() -> None:
    grown = CharacterVariant(
        id="cvar_1",
        character_id="char_1",
        name="成年",
        appearance_prompt="青年剑客，玄色劲装",
        from_episode=5,
        to_episode=None,
    )

    before = resolve_character(_card(), [grown], episode_number=4)
    after = resolve_character(_card(), [grown], episode_number=5)

    assert before.appearance_prompt == "短发少年，灰布长衫"
    assert after.appearance_prompt == "青年剑客，玄色劲装"


def test_a_variant_leaves_alone_what_it_does_not_set() -> None:
    hoarse = CharacterVariant(
        id="cvar_1",
        character_id="char_1",
        name="失声",
        appearance_prompt="",
        voice_model="zh-CN-YunjianNeural",
        from_episode=3,
        to_episode=3,
    )

    resolved = resolve_character(_card(), [hoarse], episode_number=3)

    # Only the voice changed, so the established look and portrait carry through.
    assert resolved.voice_model == "zh-CN-YunjianNeural"
    assert resolved.appearance_prompt == "短发少年，灰布长衫"
    assert resolved.reference_image_path == "projects/p/base.png"


def test_the_later_change_wins_when_ranges_overlap() -> None:
    first = CharacterVariant(
        id="cvar_1", character_id="char_1", name="成年", appearance_prompt="青年剑客", from_episode=5, to_episode=None
    )
    second = CharacterVariant(
        id="cvar_2", character_id="char_1", name="断臂", appearance_prompt="独臂剑客", from_episode=9, to_episode=None
    )

    resolved = resolve_character(_card(), [first, second], episode_number=12)

    assert resolved.appearance_prompt == "独臂剑客"


def test_the_prompt_carries_framing_and_the_cast() -> None:
    prompt = build_image_prompt(
        {
            "narration": "少年抬头",
            "visual_prompt": "low angle",
            "shot_type": "过肩",
            "camera_move": "缓推",
            "characters": [{"name": "林小满", "appearance_prompt": "短发少年，灰布长衫"}],
        }
    )

    assert "Framing: 过肩, 缓推." in prompt
    assert "林小满: 短发少年，灰布长衫" in prompt


def test_dialogue_is_spoken_in_the_speakers_voice() -> None:
    scene = {
        "narration": "山风呼啸",
        "dialogue": "就是现在。",
        "speaker": {"voice_provider": "edge", "voice_model": "zh-CN-YunxiNeural"},
    }

    line, config = spoken_line(scene, EDGE)

    # One audio track per shot, so the character's line wins over the narrator's.
    assert line == "就是现在。"
    assert config["model"] == "zh-CN-YunxiNeural"


def test_narration_keeps_the_default_voice_when_no_one_speaks() -> None:
    line, config = spoken_line({"narration": "山风呼啸", "dialogue": ""}, EDGE)

    assert line == "山风呼啸"
    assert config["model"] == EDGE["model"]


def test_a_voice_from_an_unconfigured_provider_is_not_used() -> None:
    config = voice_config(EDGE, {"voice_provider": "openai", "voice_model": "alloy"})

    # The card stores no credentials, so honouring this would fail on a key we do not have.
    assert config["model"] == EDGE["model"]


def test_characters_round_trip_with_their_variants() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            character = _character(client, headers, project_id)

            created = client.post(
                f"/api/projects/{project_id}/characters/{character['id']}/variants",
                json={"name": "成年", "appearancePrompt": "青年剑客", "fromEpisode": 5},
                headers=headers,
            )

            assert created.status_code == 201, created.text
            listed = client.get(f"/api/projects/{project_id}/characters", headers=headers).json()["characters"]
            assert [item["name"] for item in listed] == ["林小满"]
            assert [variant["name"] for variant in listed[0]["variants"]] == ["成年"]
            assert listed[0]["variants"][0]["toEpisode"] is None


def test_a_variant_that_ends_before_it_starts_is_refused() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            character = _character(client, headers, project_id)

            refused = client.post(
                f"/api/projects/{project_id}/characters/{character['id']}/variants",
                json={"name": "错的", "fromEpisode": 8, "toEpisode": 3},
                headers=headers,
            )

            # It would never resolve for any episode, so it is rejected at the door.
            assert refused.status_code == 400, refused.text


def test_unlocking_a_character_is_an_edit_a_patch_can_make() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            character = _character(client, headers, project_id)
            client.patch(
                f"/api/projects/{project_id}/characters/{character['id']}",
                json={"isLocked": True},
                headers=headers,
            )

            unlocked = client.patch(
                f"/api/projects/{project_id}/characters/{character['id']}",
                json={"isLocked": False},
                headers=headers,
            )

            assert unlocked.status_code == 200, unlocked.text
            assert unlocked.json()["character"]["isLocked"] is False


def test_a_shot_casts_only_characters_from_its_own_project() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            character = _character(client, headers, project_id)
            scene_id = client.post(
                f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers
            ).json()["scenes"][0]["id"]
            # A real character, but from a different show in the same account.
            other_project = _project(client, headers)
            outsider = _character(client, headers, other_project, name="别的剧的人")

            cast = client.put(
                f"/api/projects/{project_id}/scenes/{scene_id}/characters",
                json={"characterIds": [character["id"]]},
                headers=headers,
            )

            assert cast.status_code == 200, cast.text
            assert cast.json()["characterIds"] == [character["id"]]

            stranger = client.put(
                f"/api/projects/{project_id}/scenes/{scene_id}/characters",
                json={"characterIds": [outsider["id"]]},
                headers=headers,
            )
            assert stranger.status_code == 400, stranger.text
            assert outsider["id"] in stranger.json()["error"]

            # The rejected write left the existing cast alone.
            projects = client.get("/api/projects", headers=headers).json()["projects"]
            episode_id = next(item["currentEpisodeId"] for item in projects if item["id"] == project_id)
            episode = client.get(f"/api/projects/{project_id}/episodes/{episode_id}", headers=headers).json()["episode"]
            shot = next(item for item in episode["scenes"] if item["id"] == scene_id)
            assert shot["characterIds"] == [character["id"]]


def test_deleting_a_character_takes_it_out_of_every_shot() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            character = _character(client, headers, project_id)
            scene_id = client.post(
                f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers
            ).json()["scenes"][0]["id"]
            client.put(
                f"/api/projects/{project_id}/scenes/{scene_id}/characters",
                json={"characterIds": [character["id"]]},
                headers=headers,
            )

            removed = client.delete(f"/api/projects/{project_id}/characters/{character['id']}", headers=headers)

            assert removed.status_code == 204, removed.text
            episode_id = client.get("/api/projects", headers=headers).json()["projects"][0]["currentEpisodeId"]
            episode = client.get(f"/api/projects/{project_id}/episodes/{episode_id}", headers=headers).json()["episode"]
            shot = next(item for item in episode["scenes"] if item["id"] == scene_id)
            # A deleted character left in the cast would keep steering prompts.
            assert shot["characterIds"] == []


def test_generation_leaves_locked_shots_alone() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            scenes = client.post(
                f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers
            ).json()["scenes"]
            client.patch(
                f"/api/projects/{project_id}/scenes/{scenes[0]['id']}",
                json={"isLocked": True},
                headers=headers,
            )

            started = client.post(f"/api/projects/{project_id}/generate", json={}, headers=headers)

            assert started.status_code == 202, started.text
            # The approved shot is not re-rendered, so only the other one is queued.
            assert started.json()["sceneCount"] == len(scenes) - 1


def test_generation_says_so_when_every_shot_is_locked() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            scenes = client.post(
                f"/api/projects/{project_id}/parse", json={"script": "剧本"}, headers=headers
            ).json()["scenes"]
            for scene in scenes:
                client.patch(
                    f"/api/projects/{project_id}/scenes/{scene['id']}",
                    json={"isLocked": True},
                    headers=headers,
                )

            refused = client.post(f"/api/projects/{project_id}/generate", json={}, headers=headers)

            # Silently doing nothing would read as a run that finished instantly.
            assert refused.status_code == 400, refused.text
            assert "locked" in refused.json()["error"]


def test_the_cast_reaches_generation_resolved_for_that_episode() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            from app.api.v1 import projects as projects_api

            project_id = _project(client, headers)
            character = _character(client, headers, project_id)
            client.post(
                f"/api/projects/{project_id}/characters/{character['id']}/variants",
                json={"name": "成年", "appearancePrompt": "青年剑客", "fromEpisode": 2},
                headers=headers,
            )
            second = client.post(f"/api/projects/{project_id}/episodes", json={}, headers=headers).json()["episode"]
            parsed = client.post(
                f"/api/projects/{project_id}/parse",
                json={"script": "第二集", "episodeId": second["id"]},
                headers=headers,
            ).json()
            for scene in parsed["scenes"]:
                client.put(
                    f"/api/projects/{project_id}/scenes/{scene['id']}/characters",
                    json={"characterIds": [character["id"]]},
                    headers=headers,
                )

            captured: dict[str, Any] = {}

            async def _capture(_project_id: str, scenes: list[dict[str, Any]], *_args: Any, **_kwargs: Any) -> None:
                captured["scenes"] = scenes

            original = projects_api.run_generation
            projects_api.run_generation = _capture
            try:
                client.post(
                    f"/api/projects/{project_id}/generate",
                    json={"episodeId": second["id"]},
                    headers=headers,
                )
            finally:
                projects_api.run_generation = original

            cast = captured["scenes"][0]["characters"]
            # Episode 2 is inside the variant's range, so the grown-up look is what renders.
            assert [item["appearance_prompt"] for item in cast] == ["青年剑客"]


def test_a_portrait_freezes_the_configuration_that_made_it() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            from app.api.v1 import characters as characters_api

            project_id = _project(client, headers)
            character = _character(client, headers, project_id)

            async def _fake_image(*_args: Any, **_kwargs: Any) -> ImageResult:
                return ImageResult(data=b"portrait-bytes", format="png")

            original = characters_api.models.generate_image
            characters_api.models.generate_image = _fake_image
            try:
                drawn = client.post(
                    f"/api/projects/{project_id}/characters/{character['id']}/portrait",
                    headers=headers,
                )
            finally:
                characters_api.models.generate_image = original

            assert drawn.status_code == 200, drawn.text
            card = drawn.json()["character"]
            # Frozen, so changing the account default later cannot restyle an established
            # character the rest of the series was already matched against.
            assert (card["imageProvider"], card["imageModel"]) == ("openai", "gpt-image-1")
            assert "/api/chat/artifacts/" in card["referenceImageUrl"]
            fetched = client.get("/api/chat/artifacts/" + card["referenceImageUrl"].rsplit("/", 1)[-1])
            assert fetched.content == b"portrait-bytes"


def test_a_locked_character_is_not_redrawn() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            character = _character(client, headers, project_id)
            client.patch(
                f"/api/projects/{project_id}/characters/{character['id']}",
                json={"isLocked": True},
                headers=headers,
            )

            refused = client.post(
                f"/api/projects/{project_id}/characters/{character['id']}/portrait",
                headers=headers,
            )

            assert refused.status_code == 409, refused.text


def test_a_portrait_becomes_the_reference_a_shot_renders_against() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = artifact_service.PRIVATE_GENERATED_DIR
        artifact_service.PRIVATE_GENERATED_DIR = Path(directory)
        try:
            stored = artifact_service.store_artifact("characters", "proj_1", "char_1.png", b"portrait-bytes")

            references = character_references(
                {"characters": [{"id": "char_1", "name": "林小满", "reference_image_path": stored}]}
            )
        finally:
            artifact_service.PRIVATE_GENERATED_DIR = original

    assert len(references) == 1
    name, data, mime_type = references[0]
    assert name.endswith(".png")
    assert (data, mime_type) == (b"portrait-bytes", "image/png")


def test_only_the_first_few_portraits_ride_along() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = artifact_service.PRIVATE_GENERATED_DIR
        artifact_service.PRIVATE_GENERATED_DIR = Path(directory)
        try:
            crowd = {
                "characters": [
                    {
                        "id": f"char_{index}",
                        "name": str(index),
                        "reference_image_path": artifact_service.store_artifact(
                            "characters", "proj_1", f"{index}.png", f"portrait-{index}".encode()
                        ),
                    }
                    for index in range(MAX_REFERENCE_IMAGES + 3)
                ]
            }

            references = character_references(crowd)
        finally:
            artifact_service.PRIVATE_GENERATED_DIR = original

    # Providers cap how many references one request may carry, and the cast is ordered,
    # so the crowd is truncated rather than the request being rejected outright.
    assert len(references) == MAX_REFERENCE_IMAGES
    assert [data for _, data, _ in references] == [f"portrait-{index}".encode() for index in range(MAX_REFERENCE_IMAGES)]


def test_a_missing_portrait_costs_consistency_not_the_shot() -> None:
    references = character_references(
        {"characters": [{"id": "char_1", "name": "林小满", "reference_image_path": "characters/gone/char_1.png"}]}
    )

    assert references == []


if __name__ == "__main__":
    test_a_character_without_variants_is_itself_in_every_episode()
    test_a_variant_takes_over_only_inside_its_episode_range()
    test_a_variant_leaves_alone_what_it_does_not_set()
    test_the_later_change_wins_when_ranges_overlap()
    test_the_prompt_carries_framing_and_the_cast()
    test_dialogue_is_spoken_in_the_speakers_voice()
    test_narration_keeps_the_default_voice_when_no_one_speaks()
    test_a_voice_from_an_unconfigured_provider_is_not_used()
    test_characters_round_trip_with_their_variants()
    test_a_variant_that_ends_before_it_starts_is_refused()
    test_unlocking_a_character_is_an_edit_a_patch_can_make()
    test_a_shot_casts_only_characters_from_its_own_project()
    test_deleting_a_character_takes_it_out_of_every_shot()
    test_generation_leaves_locked_shots_alone()
    test_generation_says_so_when_every_shot_is_locked()
    test_the_cast_reaches_generation_resolved_for_that_episode()
    test_a_portrait_freezes_the_configuration_that_made_it()
    test_a_locked_character_is_not_redrawn()
    test_a_portrait_becomes_the_reference_a_shot_renders_against()
    test_only_the_first_few_portraits_ride_along()
    test_a_missing_portrait_costs_consistency_not_the_shot()
