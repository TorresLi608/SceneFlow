"""Voice profiles: auditioning a timbre, binding it, and merging the reference track."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.core import database
from app.core.security import encrypt, token_for
from app.models import Character, ModelConfig, User
from app.services import artifact_service
from app.utils.common import now


CONFIGS = (
    ("script", "openai", "gpt-4o-mini"),
    ("image", "openai", "gpt-image-1"),
    ("audio", "edge", "zh-CN-XiaoxiaoNeural"),
)

HAS_FFMPEG = shutil.which("ffmpeg") is not None


async def _fake_synthesize(text: str, config: dict[str, str], output: Path) -> tuple[Path, float]:
    """Stand in for a provider: writes a real file so the artifact path round-trips."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(f"audio::{config['model']}::{text}".encode())
    return output, 2.5


@contextmanager
def _app(directory: str) -> Iterator[tuple[TestClient, dict[str, str]]]:
    from app.api.v1 import voices
    from app.main import app

    original = (database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR, voices.synthesize, voices.PRIVATE_GENERATED_DIR)
    database.DB_PATH = str(Path(directory) / "voices.db")
    database._engines.pop(database.DB_PATH, None)
    generated = Path(directory) / "private_generated"
    artifact_service.PRIVATE_GENERATED_DIR = generated
    voices.PRIVATE_GENERATED_DIR = generated
    voices.synthesize = _fake_synthesize
    try:
        with TestClient(app) as client:
            with database.db() as session:
                user = User(created_at=now(), updated_at=now(), username="sound", password="x", role="user", is_disabled=False)
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
            voices.synthesize,
            voices.PRIVATE_GENERATED_DIR,
        ) = original
        database._engines.pop(str(database.DB_PATH), None)


def _project(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/projects", json={"title": "山海"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["project"]["id"]


def _voice(client: TestClient, headers: dict[str, str], project_id: str, **body: Any) -> dict[str, Any]:
    response = client.post(f"/api/projects/{project_id}/voices", json={"name": "旁白", **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["voice"]


def test_a_new_voice_gets_the_narrator_line_it_can_then_edit() -> None:
    """The sample line names the role, because that is what tells a video model when to use it."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)

            profile = _voice(client, headers, project_id)

            assert "旁白" in profile["sampleText"]
            edited = client.patch(
                f"/api/projects/{project_id}/voices/{profile['id']}",
                json={"sampleText": "我是林小满，林小满的台词请用我这种声音。"},
                headers=headers,
            )
            assert edited.status_code == 200, edited.text
            assert edited.json()["voice"]["sampleText"].startswith("我是林小满")


def test_previewing_stores_the_clip_by_path_and_serves_a_signed_link() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            profile = _voice(client, headers, project_id, voiceModel="zh-CN-YunxiNeural", voiceProvider="edge")

            response = client.post(
                f"/api/projects/{project_id}/voices/{profile['id']}/preview", headers=headers
            )

            assert response.status_code == 200, response.text
            audio_url = response.json()["voice"]["audioUrl"]
            assert "/api/chat/artifacts/" in audio_url
            downloaded = client.get("/api/chat/artifacts/" + audio_url.rsplit("/", 1)[-1])
            assert downloaded.status_code == 200, downloaded.text
            # The profile's own model won, since it matches the configured provider.
            assert b"zh-CN-YunxiNeural" in downloaded.content


def test_a_voice_from_an_unconfigured_provider_falls_back_to_the_default() -> None:
    """A profile stores a provider and a model but never credentials."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            profile = _voice(client, headers, project_id, voiceProvider="openai", voiceModel="alloy")

            client.post(f"/api/projects/{project_id}/voices/{profile['id']}/preview", headers=headers)

            listed = client.get(f"/api/projects/{project_id}/voices", headers=headers).json()["voices"]
            audio_url = listed[0]["audioUrl"]
            downloaded = client.get("/api/chat/artifacts/" + audio_url.rsplit("/", 1)[-1])
            # Honouring `alloy` would have failed on an OpenAI key the project does not have.
            assert b"zh-CN-XiaoxiaoNeural" in downloaded.content


def test_a_character_binds_to_a_voice_and_can_be_unbound() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            profile = _voice(client, headers, project_id)
            character = client.post(
                f"/api/projects/{project_id}/characters", json={"name": "林小满"}, headers=headers
            ).json()["character"]

            bound = client.patch(
                f"/api/projects/{project_id}/characters/{character['id']}",
                json={"voiceProfileId": profile["id"]},
                headers=headers,
            )
            assert bound.status_code == 200, bound.text
            assert bound.json()["character"]["voiceProfileId"] == profile["id"]

            # "" is how a client says "unbind": a JSON null would read as an absent field.
            unbound = client.patch(
                f"/api/projects/{project_id}/characters/{character['id']}",
                json={"voiceProfileId": ""},
                headers=headers,
            )
            assert unbound.status_code == 200, unbound.text
            assert unbound.json()["character"]["voiceProfileId"] is None


def test_a_voice_from_another_show_cannot_be_bound() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            outsider = _voice(client, headers, _project(client, headers), name="别的剧的旁白")
            character = client.post(
                f"/api/projects/{project_id}/characters", json={"name": "林小满"}, headers=headers
            ).json()["character"]

            refused = client.patch(
                f"/api/projects/{project_id}/characters/{character['id']}",
                json={"voiceProfileId": outsider["id"]},
                headers=headers,
            )

            # It would resolve to no voice at synthesis time and look like a silent bug.
            assert refused.status_code == 404, refused.text


def test_deleting_a_voice_releases_every_character_bound_to_it() -> None:
    """Stands in for ON DELETE SET NULL, which the plain column cannot enforce."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            profile = _voice(client, headers, project_id)
            character = client.post(
                f"/api/projects/{project_id}/characters", json={"name": "林小满"}, headers=headers
            ).json()["character"]
            client.patch(
                f"/api/projects/{project_id}/characters/{character['id']}",
                json={"voiceProfileId": profile["id"]},
                headers=headers,
            )

            removed = client.delete(f"/api/projects/{project_id}/voices/{profile['id']}", headers=headers)

            assert removed.status_code == 204, removed.text
            with database.db() as session:
                stored = session.exec(
                    database.select(Character).where(Character.id == character["id"])
                ).first()
            assert stored.voice_profile_id is None


def test_merging_without_a_single_preview_says_so() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            _voice(client, headers, project_id)

            refused = client.post(f"/api/projects/{project_id}/voices/merge", headers=headers)

            # Silently producing an empty track would read as a merge that worked.
            assert refused.status_code == 400, refused.text


def test_merging_concatenates_every_auditioned_voice() -> None:
    if not HAS_FFMPEG:
        print("skipping merge test: ffmpeg is not installed")
        return
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            from app.api.v1 import voices

            project_id = _project(client, headers)
            for name in ("旁白", "林小满"):
                profile = _voice(client, headers, project_id, name=name)
                client.post(f"/api/projects/{project_id}/voices/{profile['id']}/preview", headers=headers)

            # The fake synthesizer writes text, not audio, so the concat itself is stubbed;
            # what this asserts is the wiring around it.
            merged_bytes = b"merged-voice-track"
            original = voices.concat_audio
            voices.concat_audio = lambda clips, **_kwargs: merged_bytes if len(clips) == 2 else b""
            try:
                merged = client.post(f"/api/projects/{project_id}/voices/merge", headers=headers)
            finally:
                voices.concat_audio = original

            assert merged.status_code == 200, merged.text
            sheet_url = merged.json()["voiceSheetUrl"]
            downloaded = client.get("/api/chat/artifacts/" + sheet_url.rsplit("/", 1)[-1])
            assert downloaded.content == merged_bytes
            # The project carries it, which is what a video render reads.
            project = client.get("/api/projects", headers=headers).json()["projects"][0]
            assert project["voiceSheetUrl"]


def test_ffmpeg_really_joins_two_clips() -> None:
    """The one test that exercises the encoder rather than the wiring around it."""
    if not HAS_FFMPEG:
        print("skipping concat test: ffmpeg is not installed")
        return
    import subprocess

    from app.services.media_service import concat_audio

    with tempfile.TemporaryDirectory() as directory:
        clips = []
        for index, frequency in enumerate((440, 880)):
            path = Path(directory) / f"tone{index}.mp3"
            subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=1", str(path)],
                check=True,
                capture_output=True,
            )
            clips.append(path.read_bytes())

        merged = concat_audio(clips)

        # Two one-second clips make roughly two seconds; MP3 framing makes it inexact.
        probed = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "-"],
            input=merged,
            capture_output=True,
            check=True,
        )
        assert 1.7 < float(probed.stdout.decode().strip()) < 2.4


if __name__ == "__main__":
    test_a_new_voice_gets_the_narrator_line_it_can_then_edit()
    test_previewing_stores_the_clip_by_path_and_serves_a_signed_link()
    test_a_voice_from_an_unconfigured_provider_falls_back_to_the_default()
    test_a_character_binds_to_a_voice_and_can_be_unbound()
    test_a_voice_from_another_show_cannot_be_bound()
    test_deleting_a_voice_releases_every_character_bound_to_it()
    test_merging_without_a_single_preview_says_so()
    test_merging_concatenates_every_auditioned_voice()
    test_ffmpeg_really_joins_two_clips()
    print("test_voices_api ok")
