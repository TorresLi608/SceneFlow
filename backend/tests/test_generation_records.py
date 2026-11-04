"""Account-level history for the standalone image/video panels.

History used to live in localStorage, so it was per-browser and kept a signed URL that
expired. These checks cover the replacement: rows keep a stored path, listing re-signs it,
users only see their own rows, and deleting a row removes its file.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app.api.v1.images import persist_image
from app.core import database
from app.core.security import token_for
from app.models import User
from app.schemas.serializers import generation_record_json
from app.services import artifact_service
from app.services.artifact_service import artifact_absolute_path
from app.services.generation_record_service import delete_generation_record, list_generation_records, save_generation_record
from app.services.image_thumbnail_service import create_image_thumbnail, image_thumbnail_path
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
                # No retention policy configured: the panel's cleanup notice stays hidden.
                assert listed.json()["retentionDays"] == 0
                assert client.get("/api/images/history", headers=headers).json()["items"] == []

                # The same id under the other kind is not found; kinds are separate lists.
                assert client.delete(f"/api/images/history/{record.id}", headers=headers).status_code == 404
                assert client.delete(f"/api/videos/history/{record.id}", headers=headers).status_code == 204
                assert client.get("/api/videos/history", headers=headers).json()["items"] == []
        finally:
            _restore(original)


def test_new_image_thumbnail_is_private_and_deleted_with_original() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            from app.main import app

            with TestClient(app) as client:
                owner, stranger = _user("thumbnail-owner"), _user("thumbnail-stranger")
                headers = {"Authorization": f"Bearer {token_for(owner)}"}
                buffer = BytesIO()
                Image.effect_noise((1024, 768), 80).save(buffer, format="PNG")
                data = buffer.getvalue()
                # No database session/transaction may be open during CPU-heavy image work.
                encode = create_image_thumbnail
                inside_transaction = False
                real_db = database.db

                @contextmanager
                def tracked_db():
                    nonlocal inside_transaction
                    with real_db() as session:
                        inside_transaction = True
                        try:
                            yield session
                        finally:
                            inside_transaction = False

                def tracked_encode(value):
                    assert not inside_transaction
                    return encode(value)

                with patch("app.api.v1.images.db", tracked_db), patch("app.api.v1.images.create_image_thumbnail", tracked_encode):
                    result = persist_image(owner, {"provider": "openai", "model": "test"}, data, "png", prompt="test", source="text-to-image", options={})

                assert result["thumbnailUrl"] and result["thumbnailUrl"] != result["url"]
                with database.db() as session:
                    record = list_generation_records(session, owner, "image")[0]
                    stored = artifact_absolute_path(record.path)
                    thumbnail = artifact_absolute_path(image_thumbnail_path(record.path))
                assert stored.read_bytes() == data
                assert thumbnail.stat().st_mode & 0o777 == 0o600
                assert thumbnail.stat().st_size < len(data) // 10
                with Image.open(thumbnail) as image:
                    assert image.format == "WEBP" and image.size == (128, 128)
                # The existing file route must verify signatures and serve the correct type.
                fetched = client.get(result["thumbnailUrl"])
                assert fetched.status_code == 200, fetched.text
                assert fetched.headers["content-type"] == "image/webp"
                assert fetched.headers["cache-control"].startswith("private,")
                assert client.get("/api/chat/artifacts/not-a-token").status_code == 404
                stranger_headers = {"Authorization": f"Bearer {token_for(stranger)}"}
                assert client.get("/api/images/history", headers=stranger_headers).json()["items"] == []
                assert client.delete(f"/api/images/history/{record.id}", headers=stranger_headers).status_code == 404
                assert stored.exists() and thumbnail.exists()
                assert client.delete(f"/api/images/history/{record.id}", headers=headers).status_code == 204
                assert not stored.exists() and not thumbnail.exists()
                assert client.get(result["thumbnailUrl"]).status_code == 404
        finally:
            _restore(original)


def test_thumbnail_orientation_transparency_and_failure_preserve_original() -> None:
    buffer = BytesIO()
    source = Image.new("RGB", (240, 80), "red")
    source.paste("blue", (120, 0, 240, 80))
    exif = source.getexif()
    exif[274] = 6  # Rotate the stored horizontal image clockwise before cropping.
    source.save(buffer, format="JPEG", exif=exif)
    with Image.open(BytesIO(create_image_thumbnail(buffer.getvalue()))) as thumbnail:
        assert thumbnail.getpixel((64, 16))[0] > 200
        assert thumbnail.getpixel((64, 112))[2] > 200
    buffer = BytesIO()
    Image.new("RGBA", (256, 128), (255, 0, 0, 0)).save(buffer, format="PNG")
    with Image.open(BytesIO(create_image_thumbnail(buffer.getvalue()))) as thumbnail:
        assert thumbnail.getpixel((64, 64))[3] == 0
    assert create_image_thumbnail(b"invalid image") is None

    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            database.init_db()
            owner = _user("failed-thumbnail")
            result = persist_image(owner, {"provider": "openai", "model": "test"}, b"original", "png", prompt="test", source="text-to-image", options={})
            assert result["url"] and result["thumbnailUrl"] is None
            with database.db() as session:
                record = list_generation_records(session, owner, "image")[0]
            assert artifact_absolute_path(record.path).read_bytes() == b"original"
            with patch("app.services.image_thumbnail_service.tempfile.NamedTemporaryFile", side_effect=OSError("disk failure")):
                result = persist_image(owner, {"provider": "openai", "model": "test"}, buffer.getvalue(), "png", prompt="test", source="text-to-image", options={})
            assert result["url"] and result["thumbnailUrl"] is None
            with database.db() as session:
                stored = list_generation_records(session, owner, "image")[0]
            assert artifact_absolute_path(stored.path).read_bytes() == buffer.getvalue()
        finally:
            _restore(original)


def test_image_history_pages_survive_equal_timestamps_inserts_and_cursor_deletion() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original = _isolated(directory)
        try:
            from app.main import app

            with TestClient(app) as client:
                owner, stranger = _user("page-owner"), _user("page-stranger")
                headers = {"Authorization": f"Bearer {token_for(owner)}"}
                config = {"provider": "openai", "model": "test"}
                expected = set()
                with database.db() as session:
                    for index in range(55):
                        record = save_generation_record(session, owner, "image", b"old", "old.png", "image/png", prompt=str(index), config=config, source="text-to-image")
                        record.created_at = "2026-10-01T00:00:00+00:00" if index % 2 else None
                        expected.add(record.id)
                    save_generation_record(session, stranger, "image", b"other", "old.png", "image/png", prompt="private", config=config, source="text-to-image")
                    save_generation_record(session, owner, "video", b"mp4", "old.mp4", "video/mp4", prompt="video", config=config, source="text-to-video")
                # A list call must never try to encode the old originals.
                with patch("app.services.image_thumbnail_service.Image.open", side_effect=AssertionError("list must not encode")):
                    first = client.get("/api/images/history", headers=headers)
                assert first.status_code == 200, first.text
                page = first.json()
                assert len(page["items"]) == 20 and page["nextCursor"]
                assert all(item["thumbnailUrl"] is None for item in page["items"])
                seen = [item["id"] for item in page["items"]]
                # Delete the row that issued the cursor, and insert a newer result between pages.
                assert client.delete(f"/api/images/history/{seen[-1]}", headers=headers).status_code == 204
                with database.db() as session:
                    save_generation_record(session, owner, "image", b"new", "new.png", "image/png", prompt="new", config=config, source="text-to-image")
                while page["nextCursor"]:
                    response = client.get("/api/images/history", params={"cursor": page["nextCursor"]}, headers=headers)
                    assert response.status_code == 200, response.text
                    page = response.json()
                    assert len(page["items"]) <= 20
                    seen.extend(item["id"] for item in page["items"])
                assert len(seen) == len(set(seen)) == 55 and set(seen) == expected
                invalid_positions = ([1, "id"], ["\ud800", "id"])
                for bad in ("not-base64!", *(base64.urlsafe_b64encode(json.dumps(value).encode()).decode() for value in invalid_positions)):
                    assert client.get("/api/images/history", params={"cursor": bad}, headers=headers).status_code == 400
                for bad in (0, 51):
                    assert client.get("/api/images/history", params={"limit": bad}, headers=headers).status_code == 422
                assert client.get("/api/images/history").status_code == 401
        finally:
            _restore(original)


if __name__ == "__main__":
    test_history_rows_keep_a_path_and_are_scoped_to_their_owner()
    test_deleting_a_history_row_removes_its_file_and_refuses_other_owners()
    test_history_endpoints_list_and_delete_for_the_signed_in_account()
    test_new_image_thumbnail_is_private_and_deleted_with_original()
    test_thumbnail_orientation_transparency_and_failure_preserve_original()
    test_image_history_pages_survive_equal_timestamps_inserts_and_cursor_deletion()
    print("test_generation_records ok")
