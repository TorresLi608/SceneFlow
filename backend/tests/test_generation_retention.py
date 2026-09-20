"""Admin-configured retention, one window per standalone menu.

Each of image, video, chat, and voice has its own `retentionDays` (whole days; 0 keeps
everything). The hourly sweeper re-reads all four, so this checks the pure purges, the
setting accessors, the split of the legacy single window, the admin endpoints, and that
every member-facing list carries its own window for the panel's cleanup notice. Project
media is asserted untouched throughout: nothing in the AI drama workbench expires.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile

from fastapi.testclient import TestClient
from sqlmodel import select

from app.core import database
from app.core.security import token_for
from app.models import ChatMessage, ChatSession, Episode, GenerationRecord, Project, Scene, SystemSetting, User, UserVoice, VoiceProfile
from app.services import artifact_service
from app.services.artifact_service import artifact_absolute_path, save_image_artifact, store_artifact
from app.services.generation_record_service import list_generation_records, save_generation_record
from app.services.retention_service import (
    expired_chat_session_count,
    expired_counts,
    expired_generation_count,
    expired_user_voice_count,
    purge_expired_chat_sessions,
    purge_expired_generation_records,
    purge_expired_user_voices,
    run_retention_sweep,
)
from app.services.system_setting_service import RETENTION_CATEGORIES, normalize_retention_days, retention_days, retention_policies_json, set_retention_days
from app.utils.common import new_id, now


def _user(username: str, role: str = "user") -> int:
    with database.db() as session:
        user = User(created_at=now(), updated_at=now(), username=username, password="x", role=role, is_disabled=False)
        session.add(user)
        session.flush()
        return int(user.id)


def _isolated(directory: str):
    original = (database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR)
    database.DB_PATH = str(Path(directory) / "retention.db")
    database._engines.pop(database.DB_PATH, None)
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "private_generated"
    return original


def _restore(original) -> None:
    database._engines.pop(str(database.DB_PATH), None)
    database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR = original


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _backdate(model, row_id: str, days: int, *columns: str) -> None:
    with database.db() as session:
        row = session.get(model, row_id)
        for column in columns or ("created_at",):
            setattr(row, column, _days_ago(days))
        session.add(row)


def _chat(user_id: int, title: str, idle_days: int, *, deleted: bool = False) -> tuple[str, Path]:
    """A session with one message and one tool-generated image, last active `idle_days` ago."""
    stamp = _days_ago(idle_days)
    session_id = new_id("chat")
    with database.db() as session:
        session.add(ChatSession(id=session_id, created_at=stamp, updated_at=stamp, deleted_at=stamp if deleted else None, user_id=user_id, title=title))
        # No ORM relationship links the two tables, so the parent must reach the database first.
        session.flush()
        session.add(ChatMessage(id=new_id("msg"), created_at=stamp, session_id=session_id, role="user", content=title))
    artifact = save_image_artifact(session_id, title, b"png", "png")
    artifact_dir = artifact_service.PRIVATE_GENERATED_DIR / "chat" / session_id
    assert artifact_dir.is_dir() and artifact["url"]
    return session_id, artifact_dir


def _voice(user_id: int, name: str, age_days: int, *, saved: bool) -> tuple[str, Path]:
    path = store_artifact("voices", str(user_id), f"{name}.wav", b"RIFF")
    with database.db() as session:
        voice = UserVoice(
            id=new_id("user-voice"),
            created_at=_days_ago(age_days),
            updated_at=_days_ago(age_days),
            user_id=user_id,
            voice_id=f"voice-{name}",
            name=name,
            preview_audio_path=path,
            is_saved=saved,
        )
        session.add(voice)
        session.flush()
        return voice.id, artifact_absolute_path(path)


def _project_media(user_id: int) -> tuple[str, list[Path]]:
    """An old series with a storyboard frame, a clip, and a project voice: never subject to retention."""
    stamp = _days_ago(400)
    project_id = new_id("proj")
    episode_id = new_id("ep")
    frame = store_artifact("projects", project_id, "shot.png", b"frame")
    clip = store_artifact("projects", project_id, "shot.mp4", b"clip")
    voice = store_artifact("voices", project_id, "narrator.wav", b"RIFF")
    with database.db() as session:
        session.add(Project(id=project_id, created_at=stamp, updated_at=stamp, user_id=user_id, title="旧剧"))
        session.flush()
        session.add(Episode(id=episode_id, created_at=stamp, updated_at=stamp, project_id=project_id, episode_number=1, title="第一集"))
        session.flush()
        session.add(Scene(id=new_id("scene"), created_at=stamp, updated_at=stamp, project_id=project_id, episode_id=episode_id, order_num=1, image_path=frame, video_path=clip))
        session.add(VoiceProfile(id=new_id("voice"), created_at=stamp, updated_at=stamp, project_id=project_id, name="旁白", audio_path=voice))
    return project_id, [artifact_absolute_path(item) for item in (frame, clip, voice)]


def test_retention_days_are_validated_and_zero_means_keep_forever() -> None:
    assert normalize_retention_days(0) == 0
    assert normalize_retention_days("30") == 30
    assert normalize_retention_days(30.0) == 30
    for bad in (-1, 1.5, "abc", True, None, 99999):
        try:
            normalize_retention_days(bad)
            raise AssertionError(f"{bad!r} must be rejected")
        except ValueError:
            pass


def test_image_and_video_windows_purge_independently() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            database.init_db()
            owner = _user("owner")
            config = {"provider": "openai", "model": "gpt-image-1"}
            with database.db() as session:
                old_image = save_generation_record(session, owner, "image", b"old", "generated-image.png", "image/png", prompt="old", config=config, source="text-to-image")
                old_video = save_generation_record(session, owner, "video", b"old", "generated-video.mp4", "video/mp4", prompt="old", config=config, source="text-to-video")
                fresh = save_generation_record(session, owner, "video", b"new", "generated-video.mp4", "video/mp4", prompt="new", config=config, source="text-to-video")
            _backdate(GenerationRecord, old_image.id, 31)
            _backdate(GenerationRecord, old_video.id, 31)
            files = {record.id: artifact_absolute_path(record.path) for record in (old_image, old_video, fresh)}

            with database.db() as session:
                assert all(retention_days(session, category) == 0 for category in RETENTION_CATEGORIES)
                assert purge_expired_generation_records(session, "image", 0) == 0
                assert expired_generation_count(session, "image", 30) == 1
                assert expired_generation_count(session, "video", 30) == 1
                # Only the image window fires; the equally old video waits for its own window.
                assert purge_expired_generation_records(session, "image", 30) == 1
            assert not files[old_image.id].exists()
            assert files[old_video.id].exists() and files[fresh.id].exists()
            with database.db() as session:
                assert session.get(GenerationRecord, old_image.id) is None
                assert purge_expired_generation_records(session, "video", 30) == 1
                assert [item.id for item in list_generation_records(session, owner, "video")] == [fresh.id]
            assert not files[old_video.id].exists()
        finally:
            _restore(original)


def test_chat_window_removes_idle_sessions_with_messages_and_tool_artifacts() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            database.init_db()
            owner = _user("owner")
            idle_id, idle_dir = _chat(owner, "idle", 40)
            removed_id, removed_dir = _chat(owner, "removed", 40, deleted=True)
            active_id, active_dir = _chat(owner, "active", 1)
            # Created long ago but used yesterday: activity, not age, is the clock.
            revived_id, revived_dir = _chat(owner, "revived", 1)
            _backdate(ChatSession, revived_id, 90, "created_at")

            with database.db() as session:
                assert expired_chat_session_count(session, 30) == 1  # the soft-deleted one is not "live"
                assert purge_expired_chat_sessions(session, 0) == 0
                assert purge_expired_chat_sessions(session, 30) == 2
            assert not idle_dir.exists() and not removed_dir.exists()
            assert active_dir.is_dir() and revived_dir.is_dir()
            with database.db() as session:
                assert session.get(ChatSession, idle_id) is None and session.get(ChatSession, removed_id) is None
                assert session.get(ChatSession, active_id) is not None and session.get(ChatSession, revived_id) is not None
                remaining = set(session.exec(select(ChatMessage.session_id)).all())
                assert remaining == {active_id, revived_id}
        finally:
            _restore(original)


def test_voice_window_removes_old_drafts_and_saved_voices_with_their_audio() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            database.init_db()
            owner = _user("owner")
            old_draft, old_draft_file = _voice(owner, "draft", 45, saved=False)
            old_saved, old_saved_file = _voice(owner, "kept", 45, saved=True)
            fresh, fresh_file = _voice(owner, "fresh", 2, saved=True)

            with database.db() as session:
                assert expired_user_voice_count(session, 30) == 2
                assert purge_expired_user_voices(session, 0) == 0
                assert purge_expired_user_voices(session, 30) == 2
            assert not old_draft_file.exists() and not old_saved_file.exists()
            assert fresh_file.exists()
            with database.db() as session:
                assert session.get(UserVoice, old_draft) is None and session.get(UserVoice, old_saved) is None
                assert session.get(UserVoice, fresh) is not None
        finally:
            _restore(original)


def test_sweep_applies_each_window_and_never_touches_project_media() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            database.init_db()
            admin_id = _user("boss", role="superAdmin")
            owner = _user("owner")
            _, project_files = _project_media(owner)
            config = {"provider": "openai", "model": "gpt-image-1"}
            with database.db() as session:
                image = save_generation_record(session, owner, "image", b"i", "generated-image.png", "image/png", prompt="i", config=config, source="text-to-image")
                video = save_generation_record(session, owner, "video", b"v", "generated-video.mp4", "video/mp4", prompt="v", config=config, source="text-to-video")
            _backdate(GenerationRecord, image.id, 400)
            _backdate(GenerationRecord, video.id, 400)
            _chat(owner, "old", 400)
            _voice(owner, "old", 400, saved=True)

            with database.db() as session:
                # Only chat and voice have windows; image and video stay "keep forever".
                set_retention_days(session, {"chat": 30, "voice": 7}, admin_id)
            with database.db() as session:
                assert expired_counts(session) == {"image": 0, "video": 0, "chat": 1, "voice": 1}
            assert run_retention_sweep() == {"image": 0, "video": 0, "chat": 1, "voice": 1}
            with database.db() as session:
                assert session.get(GenerationRecord, image.id) is not None
                assert session.get(GenerationRecord, video.id) is not None
                assert session.exec(select(ChatSession.id)).all() == []
                assert session.exec(select(UserVoice.id)).all() == []
                assert len(session.exec(select(Scene.id)).all()) == 1
                assert len(session.exec(select(VoiceProfile.id)).all()) == 1
            assert all(path.exists() for path in project_files)

            with database.db() as session:
                set_retention_days(session, {"image": 365, "video": 365}, admin_id)
            assert run_retention_sweep() == {"image": 1, "video": 1, "chat": 0, "voice": 0}
            assert all(path.exists() for path in project_files)
        finally:
            _restore(original)


def test_admin_endpoints_read_write_and_sweep_every_window() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            from app.main import app

            with TestClient(app) as client:
                admin_id = _user("boss", role="superAdmin")
                member_id = _user("member")
                admin = {"Authorization": f"Bearer {token_for(admin_id)}"}
                member = {"Authorization": f"Bearer {token_for(member_id)}"}

                assert client.get("/api/admin/generation-retention", headers=member).status_code == 403
                initial = client.get("/api/admin/generation-retention", headers=admin)
                assert initial.status_code == 200, initial.text
                assert set(initial.json()["policies"]) == set(RETENTION_CATEGORIES)
                assert all(policy["retentionDays"] == 0 and policy["expiredCount"] == 0 for policy in initial.json()["policies"].values())
                # Members never see the admin endpoint; each list carries its own window instead.
                assert client.get("/api/images/history", headers=member).json()["retentionDays"] == 0
                assert client.get("/api/videos/history", headers=member).json()["retentionDays"] == 0
                assert client.get("/api/chat/sessions", headers=member).json()["retentionDays"] == 0
                assert client.get("/api/voices", headers=member).json()["retentionDays"] == 0

                bad_bodies = (
                    {},
                    {"retentionDays": 7},
                    {"policies": {}},
                    {"policies": {"image": {"retentionDays": -3}}},
                    {"policies": {"image": 7}},
                    {"policies": {"exports": {"retentionDays": 7}}},
                    {"policies": {"image": {"retentionDays": 7}, "chat": {"retentionDays": "x"}}},
                )
                for body in bad_bodies:
                    assert client.patch("/api/admin/generation-retention", json=body, headers=admin).status_code == 400, body
                # A rejected batch writes nothing, including its valid entries.
                assert all(policy["retentionDays"] == 0 for policy in client.get("/api/admin/generation-retention", headers=admin).json()["policies"].values())

                config = {"provider": "openai", "model": "gpt-image-1"}
                with database.db() as session:
                    old = save_generation_record(session, member_id, "image", b"old", "generated-image.png", "image/png", prompt="old", config=config, source="text-to-image")
                _backdate(GenerationRecord, old.id, 10)
                _chat(member_id, "old", 10)

                updated = client.patch(
                    "/api/admin/generation-retention",
                    json={"policies": {"image": {"retentionDays": 7}, "chat": {"retentionDays": 3}, "voice": {"retentionDays": 0}}},
                    headers=admin,
                )
                assert updated.status_code == 200, updated.text
                policies = updated.json()["policies"]
                assert (policies["image"]["retentionDays"], policies["image"]["expiredCount"]) == (7, 1)
                assert (policies["chat"]["retentionDays"], policies["chat"]["expiredCount"]) == (3, 1)
                assert (policies["video"]["retentionDays"], policies["voice"]["retentionDays"]) == (0, 0)
                assert policies["image"]["updatedAt"] and policies["video"]["updatedAt"] is None
                with database.db() as session:
                    assert retention_days(session, "image") == 7 and retention_days(session, "video") == 0
                assert client.get("/api/images/history", headers=member).json()["retentionDays"] == 7
                assert client.get("/api/videos/history", headers=member).json()["retentionDays"] == 0
                assert client.get("/api/chat/sessions", headers=member).json()["retentionDays"] == 3
                assert client.get("/api/voices", headers=member).json()["retentionDays"] == 0

                swept = client.post("/api/admin/generation-retention/sweep", headers=admin)
                assert swept.status_code == 200, swept.text
                assert swept.json()["removedCount"] == 2
                assert swept.json()["policies"]["image"]["removedCount"] == 1
                assert swept.json()["policies"]["chat"]["removedCount"] == 1
                assert swept.json()["policies"]["video"]["removedCount"] == 0
                assert swept.json()["policies"]["image"]["expiredCount"] == 0
                assert client.get("/api/images/history", headers=member).json()["items"] == []
                assert client.get("/api/chat/sessions", headers=member).json()["sessions"] == []
        finally:
            _restore(original)


def test_settings_round_trip_per_category() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            database.init_db()
            admin_id = _user("boss", role="superAdmin")
            with database.db() as session:
                written = set_retention_days(session, {"video": 45}, admin_id)
                assert written["video"]["retentionDays"] == 45 and written["image"]["retentionDays"] == 0
            with database.db() as session:
                assert retention_days(session, "video") == 45
                assert retention_days(session, "image") == 0
                assert set_retention_days(session, {"video": 0}, admin_id)["video"]["retentionDays"] == 0
                try:
                    set_retention_days(session, {"exports": 1}, admin_id)
                    raise AssertionError("project categories must not be accepted")
                except ValueError:
                    pass
        finally:
            _restore(original)


def test_legacy_single_window_is_split_into_image_and_video_by_the_migration() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            # Build the schema at the previous head, then plant the legacy row and upgrade.
            from alembic import command
            from alembic.config import Config

            config = Config(database.ALEMBIC_CONFIG)
            with database.engine().connect() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "d9e2f3a4b5c6")
            connection = sqlite3.connect(database.DB_PATH)
            connection.execute("INSERT INTO system_settings (key, value, updated_at) VALUES ('generation_retention_days', '14', 't0')")
            connection.commit()
            connection.close()

            database.init_db()
            with database.db() as session:
                policies = retention_policies_json(session)
                assert policies["image"]["retentionDays"] == 14 and policies["image"]["updatedAt"] == "t0"
                assert policies["video"]["retentionDays"] == 14
                assert policies["chat"]["retentionDays"] == 0 and policies["voice"]["retentionDays"] == 0
                assert session.get(SystemSetting, "generation_retention_days") is None
        finally:
            _restore(original)


if __name__ == "__main__":
    test_retention_days_are_validated_and_zero_means_keep_forever()
    test_image_and_video_windows_purge_independently()
    test_chat_window_removes_idle_sessions_with_messages_and_tool_artifacts()
    test_voice_window_removes_old_drafts_and_saved_voices_with_their_audio()
    test_sweep_applies_each_window_and_never_touches_project_media()
    test_admin_endpoints_read_write_and_sweep_every_window()
    test_settings_round_trip_per_category()
    test_legacy_single_window_is_split_into_image_and_video_by_the_migration()
    print("test_generation_retention ok")
