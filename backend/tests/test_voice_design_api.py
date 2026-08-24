"""Designing a timbre inside a project, and importing one the account already has.

The old project voice form asked the user to type a provider and a model name, which is
how a series ended up with profiles no synthesiser here could voice. Both paths below get
those from configuration instead, so a profile always names something real.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import tempfile
from typing import Any, Iterator

from fastapi.testclient import TestClient

from app.core import database
from app.core.security import encrypt, token_for
from app.models import ModelConfig, User, UserVoice
from app.services import artifact_service
from app.utils.common import new_id, now


DESIGNED_AUDIO = b"RIFF----WAVEfmt "


async def _fake_create_voice(config: dict[str, Any], prompt: str, preview: str, name: str) -> tuple[str, bytes]:
    """Stand in for Qwen voice design; returns a voice id and real audition bytes."""
    assert config["provider"] == "qwen", config
    return f"voice-{name}", DESIGNED_AUDIO


@contextmanager
def _app(directory: str) -> Iterator[tuple[TestClient, dict[str, str], int]]:
    from app.api.v1 import voices
    from app.main import app

    original = (database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR, voices.create_voice)
    database.DB_PATH = str(Path(directory) / "voice_design.db")
    database._engines.pop(database.DB_PATH, None)
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "private_generated"
    voices.create_voice = _fake_create_voice
    try:
        with TestClient(app) as client:
            with database.db() as session:
                user = User(
                    created_at=now(),
                    updated_at=now(),
                    username="sound",
                    password="x",
                    role="user",
                    is_disabled=False,
                )
                session.add(user)
                session.flush()
                user_id = int(user.id)
                session.add(
                    ModelConfig(
                        created_at=now(),
                        updated_at=now(),
                        user_id=user_id,
                        source="user",
                        provider="qwen",
                        encrypted_key=encrypt("sk-test-key-value"),
                        is_active=True,
                        is_enabled=True,
                        purpose="audio",
                        model_name="qwen3-tts-vd-2026-01-26",
                    )
                )
            yield client, {"Authorization": f"Bearer {token_for(user_id)}"}, user_id
    finally:
        database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR, voices.create_voice = original
        database._engines.pop(str(database.DB_PATH), None)


def _project(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/projects", json={"title": "山海"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["project"]["id"]


def test_designing_a_voice_binds_it_to_the_series_and_keeps_it_on_the_account() -> None:
    """A timbre that cost a paid request should be reusable in the next series for free."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, user_id):
            project_id = _project(client, headers)

            response = client.post(
                f"/api/projects/{project_id}/voices/design",
                json={
                    "name": "narrator",
                    "voicePrompt": "沉稳的中年男声，略带沙哑",
                    "previewText": "各位听众朋友，大家好。",
                },
                headers=headers,
            )

            assert response.status_code == 201, response.text
            voice = response.json()["voice"]
            assert voice["name"] == "narrator"
            # The designed voice id, not the base model: that is what synthesis must ask for
            # to get this timbre back rather than the model's default one.
            assert voice["voiceModel"] == "voice-narrator"
            assert voice["voiceProvider"] == "qwen"
            # The audition is stored, so the profile can join the merged sheet immediately.
            assert voice["audioUrl"] is not None

            with database.db() as session:
                from sqlmodel import select

                saved = session.exec(select(UserVoice).where(UserVoice.user_id == user_id)).all()
            assert [item.voice_id for item in saved] == ["voice-narrator"]
            assert saved[0].is_saved is True


def test_designing_a_voice_needs_a_prompt_and_an_audition_line() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            project_id = _project(client, headers)

            refused = client.post(
                f"/api/projects/{project_id}/voices/design",
                json={"name": "narrator", "voicePrompt": "", "previewText": ""},
                headers=headers,
            )

            assert refused.status_code == 422, refused.text


def test_importing_copies_the_audition_so_the_series_survives_a_library_tidy_up() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, user_id):
            project_id = _project(client, headers)
            stored = artifact_service.store_artifact("voices", str(user_id), "library.wav", DESIGNED_AUDIO)
            with database.db() as session:
                session.add(
                    UserVoice(
                        id=new_id("user-voice"),
                        created_at=now(),
                        updated_at=now(),
                        user_id=user_id,
                        voice_id="voice-heroine",
                        target_model="qwen3-tts-vd-2026-01-26",
                        name="女主",
                        voice_prompt="清亮的少女声",
                        preview_text="你好呀。",
                        preview_audio_path=stored,
                        is_saved=True,
                    )
                )

            listed = client.get("/api/voices", headers=headers).json()["voices"]
            assert [item["name"] for item in listed] == ["女主"]

            response = client.post(
                f"/api/projects/{project_id}/voices/import",
                json={"userVoiceId": listed[0]["id"]},
                headers=headers,
            )

            assert response.status_code == 201, response.text
            voice = response.json()["voice"]
            assert voice["name"] == "女主"
            assert voice["voiceModel"] == "voice-heroine"
            assert voice["audioUrl"] is not None
            # A copy, not a reference: the library row's file is left where it was.
            assert artifact_service.artifact_absolute_path(stored).exists()


def test_importing_a_voice_that_is_not_yours_is_not_found() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers, _):
            project_id = _project(client, headers)

            response = client.post(
                f"/api/projects/{project_id}/voices/import",
                json={"userVoiceId": "user-voice-someone-else"},
                headers=headers,
            )

            assert response.status_code == 404, response.text


if __name__ == "__main__":
    test_designing_a_voice_binds_it_to_the_series_and_keeps_it_on_the_account()
    test_designing_a_voice_needs_a_prompt_and_an_audition_line()
    test_importing_copies_the_audition_so_the_series_survives_a_library_tidy_up()
    test_importing_a_voice_that_is_not_yours_is_not_found()
    print("test_voice_design_api ok")
