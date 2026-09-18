"""Admin-configured retention for standalone image/video results.

`retentionDays` is whole days; 0 keeps everything. The hourly sweeper re-reads the setting,
so this checks the pure purge, the setting accessors, the admin endpoints, and that the
member-facing history lists carry the window for the panels' cleanup notice.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from app.core import database
from app.core.security import token_for
from app.models import GenerationRecord, User
from app.services import artifact_service
from app.services.artifact_service import artifact_absolute_path
from app.services.generation_record_service import expired_generation_count, list_generation_records, purge_expired_generation_records, save_generation_record
from app.services.system_setting_service import generation_retention_days, normalize_retention_days, set_generation_retention_days
from app.utils.common import now


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


def _backdate(record_id: str, days: int) -> None:
    with database.db() as session:
        record = session.get(GenerationRecord, record_id)
        record.created_at = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        session.add(record)


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


def test_purge_removes_only_rows_older_than_the_window_and_their_files() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            database.init_db()
            owner = _user("owner")
            config = {"provider": "openai", "model": "gpt-image-1"}
            with database.db() as session:
                old = save_generation_record(session, owner, "image", b"old", "generated-image.png", "image/png", prompt="old", config=config, source="text-to-image")
                fresh = save_generation_record(session, owner, "video", b"new", "generated-video.mp4", "video/mp4", prompt="new", config=config, source="text-to-video")
            _backdate(old.id, 31)
            old_file, fresh_file = artifact_absolute_path(old.path), artifact_absolute_path(fresh.path)

            with database.db() as session:
                assert generation_retention_days(session) == 0
                assert purge_expired_generation_records(session, 0) == 0
                assert expired_generation_count(session, 30) == 1
                assert purge_expired_generation_records(session, 30) == 1
            assert not old_file.exists()
            assert fresh_file.exists()
            with database.db() as session:
                assert session.get(GenerationRecord, old.id) is None
                assert [item.id for item in list_generation_records(session, owner, "video")] == [fresh.id]
        finally:
            _restore(original)


def test_admin_endpoints_read_write_and_sweep_the_policy() -> None:
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
                assert initial.json()["retentionDays"] == 0
                # Members never see the admin endpoint; their history lists carry the window instead.
                assert client.get("/api/images/history", headers=member).json()["retentionDays"] == 0
                assert client.get("/api/videos/history", headers=member).json()["retentionDays"] == 0

                assert client.patch("/api/admin/generation-retention", json={"retentionDays": -3}, headers=admin).status_code == 400
                assert client.patch("/api/admin/generation-retention", json={}, headers=admin).status_code == 400

                config = {"provider": "openai", "model": "gpt-image-1"}
                with database.db() as session:
                    old = save_generation_record(session, member_id, "image", b"old", "generated-image.png", "image/png", prompt="old", config=config, source="text-to-image")
                _backdate(old.id, 10)

                updated = client.patch("/api/admin/generation-retention", json={"retentionDays": 7}, headers=admin)
                assert updated.status_code == 200, updated.text
                assert updated.json()["retentionDays"] == 7
                assert updated.json()["expiredCount"] == 1
                with database.db() as session:
                    assert generation_retention_days(session) == 7
                assert client.get("/api/images/history", headers=member).json()["retentionDays"] == 7
                assert client.get("/api/videos/history", headers=member).json()["retentionDays"] == 7

                swept = client.post("/api/admin/generation-retention/sweep", headers=admin)
                assert swept.status_code == 200, swept.text
                assert swept.json()["removedCount"] == 1
                assert swept.json()["expiredCount"] == 0
                assert client.get("/api/images/history", headers=member).json()["items"] == []
        finally:
            _restore(original)


def test_setting_round_trips_through_the_service() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            database.init_db()
            admin_id = _user("boss", role="superAdmin")
            with database.db() as session:
                assert set_generation_retention_days(session, 45, admin_id)["retentionDays"] == 45
            with database.db() as session:
                assert generation_retention_days(session) == 45
                assert set_generation_retention_days(session, 0, admin_id)["retentionDays"] == 0
        finally:
            _restore(original)


if __name__ == "__main__":
    test_retention_days_are_validated_and_zero_means_keep_forever()
    test_purge_removes_only_rows_older_than_the_window_and_their_files()
    test_admin_endpoints_read_write_and_sweep_the_policy()
    test_setting_round_trips_through_the_service()
    print("test_generation_retention ok")
