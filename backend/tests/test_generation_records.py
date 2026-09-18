"""Account-level history for the standalone image/video panels.

History used to live in localStorage, so it was per-browser and kept a signed URL that
expired. These checks cover the replacement: rows keep a stored path, listing re-signs it,
users only see their own rows, and deleting a row removes its file.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from app.core import database
from app.core.security import token_for
from app.models import User
from app.schemas.serializers import generation_record_json
from app.services import artifact_service
from app.services.artifact_service import artifact_absolute_path
from app.services.generation_record_service import delete_generation_record, list_generation_records, save_generation_record
from app.utils.common import now


def _user(username: str) -> int:
    with database.db() as session:
        user = User(created_at=now(), updated_at=now(), username=username, password="x", role="user", is_disabled=False)
        session.add(user)
        session.flush()
        return int(user.id)


def _isolated(directory: str):
    original = (database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR)
    database.DB_PATH = str(Path(directory) / "history.db")
    database._engines.pop(database.DB_PATH, None)
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "private_generated"
    return original


def _restore(original) -> None:
    database._engines.pop(str(database.DB_PATH), None)
    database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR = original


def test_history_rows_keep_a_path_and_are_scoped_to_their_owner() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            database.init_db()
            owner, stranger = _user("owner"), _user("stranger")
            config = {"provider": "openai", "model": "gpt-image-1"}
            with database.db() as session:
                first = save_generation_record(session, owner, "image", b"png-1", "generated-image.png", "image/png", prompt="a fox", config=config, source="text-to-image", options={"ratio": "1:1", "resolution": None})
                save_generation_record(session, owner, "video", b"mp4", "generated-video.mp4", "video/mp4", prompt="a river", config=config, source="text-to-video", options={"duration": 5})
                save_generation_record(session, stranger, "image", b"png-2", "generated-image.png", "image/png", prompt="a cat", config=config, source="text-to-image")

            assert not first.path.startswith("http")
            assert artifact_absolute_path(first.path).read_bytes() == b"png-1"

            with database.db() as session:
                images = [generation_record_json(item) for item in list_generation_records(session, owner, "image")]
                videos = [generation_record_json(item) for item in list_generation_records(session, owner, "video")]
            assert [item["prompt"] for item in images] == ["a fox"]
            assert images[0]["options"] == {"ratio": "1:1"}
            assert images[0]["url"] and "/api/chat/artifacts/" in images[0]["url"]
            assert [item["prompt"] for item in videos] == ["a river"]
            assert videos[0]["options"] == {"duration": 5}
        finally:
            _restore(original)


def test_deleting_a_history_row_removes_its_file_and_refuses_other_owners() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            database.init_db()
            owner, stranger = _user("owner"), _user("stranger")
            config = {"provider": "openai", "model": "gpt-image-1"}
            with database.db() as session:
                record = save_generation_record(session, owner, "image", b"png", "generated-image.png", "image/png", prompt="a fox", config=config, source="text-to-image")
            file_path = artifact_absolute_path(record.path)
            assert file_path.exists()

            with database.db() as session:
                try:
                    delete_generation_record(session, stranger, "image", record.id)
                    raise AssertionError("another account must not delete the row")
                except Exception as exc:
                    assert getattr(exc, "status_code", None) == 404
            assert file_path.exists()

            with database.db() as session:
                delete_generation_record(session, owner, "image", record.id)
            assert not file_path.exists()
            with database.db() as session:
                assert list_generation_records(session, owner, "image") == []
        finally:
            _restore(original)


def test_history_endpoints_list_and_delete_for_the_signed_in_account() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            from app.main import app

            with TestClient(app) as client:
                user_id = _user("api-user")
                headers = {"Authorization": f"Bearer {token_for(user_id)}"}
                config = {"provider": "qwen", "model": "wan"}
                with database.db() as session:
                    record = save_generation_record(session, user_id, "video", b"mp4", "generated-video.mp4", "video/mp4", prompt="a river", config=config, source="text-to-video", options={"fps": 24})

                listed = client.get("/api/videos/history", headers=headers)
                assert listed.status_code == 200, listed.text
                assert [item["id"] for item in listed.json()["items"]] == [record.id]
                assert client.get("/api/images/history", headers=headers).json()["items"] == []

                # The same id under the other kind is not found; kinds are separate lists.
                assert client.delete(f"/api/images/history/{record.id}", headers=headers).status_code == 404
                assert client.delete(f"/api/videos/history/{record.id}", headers=headers).status_code == 204
                assert client.get("/api/videos/history", headers=headers).json()["items"] == []
        finally:
            _restore(original)


if __name__ == "__main__":
    test_history_rows_keep_a_path_and_are_scoped_to_their_owner()
    test_deleting_a_history_row_removes_its_file_and_refuses_other_owners()
    test_history_endpoints_list_and_delete_for_the_signed_in_account()
    print("test_generation_records ok")
