"""Props: draft the prompt, review it, draw the reference, tile the results into one sheet."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
import tempfile
from typing import Any, Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from PIL import Image

from app.core import database
from app.core.security import encrypt, token_for
from app.llms.router import ImageResult, TextResult
from app.models import ModelConfig, Prop, User
from app.services import artifact_service
from app.services.media_service import DEFAULT_CELL_WIDTH
from app.utils.common import now
from tests.job_queue import drain_one, succeeded


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode("ascii")

CONFIGS = (
    ("script", "openai", "gpt-4o-mini"),
    ("image", "openai", "gpt-image-1"),
)


@contextmanager
def _app(directory: str) -> Iterator[tuple[TestClient, dict[str, str]]]:
    from app.main import app

    original = (database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR)
    database.DB_PATH = str(Path(directory) / "props.db")
    database._engines.pop(database.DB_PATH, None)
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "private_generated"
    try:
        with TestClient(app) as client:
            with database.db() as session:
                user = User(created_at=now(), updated_at=now(), username="propmaster", password="x", role="user", is_disabled=False)
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
        database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR = original
        database._engines.pop(str(database.DB_PATH), None)


def _project(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/projects", json={"title": "山海"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["project"]["id"]


def _prop(client: TestClient, headers: dict[str, str], project_id: str, **body: Any) -> dict[str, Any]:
    payload = {"name": "青铜锁", "description": "巴掌大小，缠着红绳", **body}
    response = client.post(f"/api/projects/{project_id}/props", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["prop"]


def test_props_round_trip_through_create_list_patch_and_delete() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            prop = _prop(client, headers, project_id)

            listed = client.get(f"/api/projects/{project_id}/props", headers=headers).json()["props"]
            assert [item["name"] for item in listed] == ["青铜锁"]
            assert listed[0]["imageUrl"] is None

            patched = client.patch(
                f"/api/projects/{project_id}/props/{prop['id']}",
                json={"description": "锁身有缺口"},
                headers=headers,
            )
            assert patched.status_code == 200, patched.text
            assert patched.json()["prop"]["description"] == "锁身有缺口"

            removed = client.delete(f"/api/projects/{project_id}/props/{prop['id']}", headers=headers)
            assert removed.status_code == 204, removed.text
            assert client.get(f"/api/projects/{project_id}/props", headers=headers).json()["props"] == []


def test_a_prop_from_another_project_is_not_reachable() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            outsider = _prop(client, headers, _project(client, headers), name="别的剧的道具")

            response = client.patch(
                f"/api/projects/{project_id}/props/{outsider['id']}",
                json={"description": "x"},
                headers=headers,
            )

            assert response.status_code == 404, response.text


def test_a_drafted_prompt_is_returned_for_review_and_not_saved() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            from app.services import reference_service

            project_id = _project(client, headers)
            prop = _prop(client, headers, project_id)

            async def _fake_text(*_args: Any, **_kwargs: Any) -> TextResult:
                return TextResult(text="单一物体居中，纯色背景", usage={"inputTokens": 4, "outputTokens": 7})

            original = reference_service.models.complete_text
            reference_service.models.complete_text = _fake_text
            try:
                queued = client.post(
                    f"/api/projects/{project_id}/props/{prop['id']}/prompt", json={}, headers=headers
                )
                # The provider call happens while the job drains, not during the POST, so the
                # stub has to still be in place here.
                drafted = succeeded(drain_one())
            finally:
                reference_service.models.complete_text = original

            assert queued.status_code == 202, queued.text
            assert queued.json()["job"]["status"] == "queued"
            assert drafted["prompt"] == "单一物体居中，纯色背景"
            listed = client.get(f"/api/projects/{project_id}/props", headers=headers).json()["props"]
            assert listed[0]["finalPrompt"] == ""


def test_the_drawn_image_and_the_prompt_behind_it_are_both_kept() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            from app.services import reference_service

            project_id = _project(client, headers)
            prop = _prop(client, headers, project_id)

            async def _fake_image(*_args: Any, **_kwargs: Any) -> ImageResult:
                return ImageResult(data=b"prop-bytes", format="png")

            original = reference_service.models.generate_image
            reference_service.models.generate_image = _fake_image
            try:
                queued = client.post(
                    f"/api/projects/{project_id}/props/{prop['id']}/image",
                    json={"prompt": "青铜锁参考图"},
                    headers=headers,
                )
                drawn = succeeded(drain_one())
            finally:
                reference_service.models.generate_image = original

            assert queued.status_code == 202, queued.text
            data = drawn["prop"]
            assert data["finalPrompt"] == "青铜锁参考图"
            # The row keeps a path; the response mints a link that resolves.
            fetched = client.get("/api/chat/artifacts/" + data["imageUrl"].rsplit("/", 1)[-1])
            assert fetched.content == b"prop-bytes"
            with database.db() as session:
                stored = session.exec(database.select(Prop).where(Prop.id == prop["id"])).first().image_path
            assert stored and not stored.startswith("http")


def test_an_image_can_be_uploaded_instead_of_drawn() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            prop = _prop(client, headers, project_id)

            uploaded = client.put(
                f"/api/projects/{project_id}/props/{prop['id']}/image",
                json={"imageData": PNG_DATA_URL},
                headers=headers,
            )

            assert uploaded.status_code == 200, uploaded.text
            url = uploaded.json()["prop"]["imageUrl"]
            assert client.get("/api/chat/artifacts/" + url.rsplit("/", 1)[-1]).content == PNG_BYTES


def test_an_upload_that_is_not_an_image_data_url_is_refused() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            prop = _prop(client, headers, project_id)

            refused = client.put(
                f"/api/projects/{project_id}/props/{prop['id']}/image",
                json={"imageData": "https://example.com/prop.png"},
                headers=headers,
            )

            assert refused.status_code == 400, refused.text


def test_merging_props_tiles_them_into_one_sheet_the_project_carries() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            for name in ("青铜锁", "断剑", "油纸伞", "铜镜"):
                prop = _prop(client, headers, project_id, name=name)
                client.put(
                    f"/api/projects/{project_id}/props/{prop['id']}/image",
                    json={"imageData": PNG_DATA_URL},
                    headers=headers,
                )

            merged = client.post(f"/api/projects/{project_id}/props/sheet", headers=headers)

            assert merged.status_code == 200, merged.text
            sheet_url = merged.json()["propSheetUrl"]
            downloaded = client.get("/api/chat/artifacts/" + sheet_url.rsplit("/", 1)[-1])
            assert downloaded.status_code == 200, downloaded.text
            # Four props in a 2x2 grid, so the sheet is two cells wide.
            assert Image.open(BytesIO(downloaded.content)).width == 2 * DEFAULT_CELL_WIDTH
            project = client.get("/api/projects", headers=headers).json()["projects"][0]
            assert project["propSheetUrl"]


def test_merging_with_nothing_drawn_yet_says_so() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            _prop(client, headers, project_id)

            refused = client.post(f"/api/projects/{project_id}/props/sheet", headers=headers)

            # Silently producing an empty sheet would read as a merge that worked.
            assert refused.status_code == 400, refused.text


def test_a_prop_carries_its_owner_and_the_sheet_says_whose_it_is() -> None:
    """An unattributed object is the first thing continuity loses, so the owner is drawn on."""
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id = _project(client, headers)
            character = client.post(
                f"/api/projects/{project_id}/characters",
                json={"name": "林小满"},
                headers=headers,
            ).json()["character"]

            owned = _prop(client, headers, project_id, ownerCharacterId=character["id"])
            assert owned["ownerCharacterId"] == character["id"]
            # Resolved server-side, so a card renders the owner without a second request.
            assert owned["ownerName"] == "林小满"

            listed = client.get(f"/api/projects/{project_id}/props", headers=headers).json()["props"]
            assert listed[0]["ownerName"] == "林小满"

            # "" unbinds; a JSON null would read as "leave it alone".
            cleared = client.patch(
                f"/api/projects/{project_id}/props/{owned['id']}",
                json={"ownerCharacterId": ""},
                headers=headers,
            )
            assert cleared.status_code == 200, cleared.text
            assert cleared.json()["prop"]["ownerCharacterId"] is None
            assert cleared.json()["prop"]["ownerName"] == ""


if __name__ == "__main__":
    test_props_round_trip_through_create_list_patch_and_delete()
    test_a_prop_from_another_project_is_not_reachable()
    test_a_drafted_prompt_is_returned_for_review_and_not_saved()
    test_the_drawn_image_and_the_prompt_behind_it_are_both_kept()
    test_an_image_can_be_uploaded_instead_of_drawn()
    test_an_upload_that_is_not_an_image_data_url_is_refused()
    test_merging_props_tiles_them_into_one_sheet_the_project_carries()
    test_merging_with_nothing_drawn_yet_says_so()
    test_a_prop_carries_its_owner_and_the_sheet_says_whose_it_is()
    print("test_props_api ok")
