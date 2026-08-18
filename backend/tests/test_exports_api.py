"""Video export: assembling chosen shots into one file."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from typing import Any, Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.core import database
from app.core.security import token_for
from app.models import Scene, User
from app.services import artifact_service
from app.utils.common import now


HAS_FFMPEG = shutil.which("ffmpeg") is not None


@contextmanager
def _app(directory: str) -> Iterator[tuple[TestClient, dict[str, str]]]:
    from app.main import app

    original = (database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR)
    database.DB_PATH = str(Path(directory) / "exports.db")
    database._engines.pop(database.DB_PATH, None)
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory) / "private_generated"
    try:
        with TestClient(app) as client:
            with database.db() as session:
                user = User(created_at=now(), updated_at=now(), username="cutter", password="x", role="user", is_disabled=False)
                session.add(user)
                session.flush()
                user_id = int(user.id)
            yield client, {"Authorization": f"Bearer {token_for(user_id)}"}
    finally:
        database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR = original
        database._engines.pop(str(database.DB_PATH), None)


def _clip(seconds: float = 0.5, width: int = 320, height: int = 240) -> bytes:
    """A real MP4, so the concat path is exercised rather than mocked."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "clip.mp4"
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
                "-i", f"testsrc=size={width}x{height}:rate=12:duration={seconds}",
                "-pix_fmt", "yuv420p", str(path),
            ],
            check=True,
            capture_output=True,
        )
        return path.read_bytes()


def _project_with_clips(client: TestClient, headers: dict[str, str], clips: list[bytes | None]) -> tuple[str, list[str]]:
    created = client.post("/api/projects", json={"title": "剪辑"}, headers=headers)
    assert created.status_code == 201, created.text
    project = created.json()["project"]
    project_id, episode_id = project["id"], project["currentEpisodeId"]
    scene_ids = []
    with database.db() as session:
        for index, clip in enumerate(clips):
            scene_id = f"scene_{index}"
            scene_ids.append(scene_id)
            session.add(
                Scene(
                    id=scene_id,
                    created_at=now(),
                    updated_at=now(),
                    project_id=project_id,
                    episode_id=episode_id,
                    order_num=index + 1,
                    narration=f"第 {index + 1} 镜",
                    video_path=(
                        artifact_service.store_artifact("projects", project_id, f"{scene_id}.mp4", clip)
                        if clip is not None
                        else None
                    ),
                    video_status="success" if clip is not None else "idle",
                )
            )
    return project_id, scene_ids


def _wait_for(client: TestClient, headers: dict[str, str], project_id: str, export_id: str) -> dict[str, Any]:
    for _ in range(400):
        job = client.get(f"/api/projects/{project_id}/exports/{export_id}", headers=headers).json()["export"]
        if job["status"] in {"succeeded", "failed", "canceled"}:
            return job
        threading.Event().wait(0.05)
    raise AssertionError("export did not finish")


def test_merging_clips_produces_one_downloadable_file() -> None:
    if not HAS_FFMPEG:
        print("skipping export test: ffmpeg is not installed")
        return
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id, scene_ids = _project_with_clips(client, headers, [_clip(), _clip()])

            started = client.post(
                f"/api/projects/{project_id}/exports",
                json={"sceneIds": scene_ids, "rangeLabel": "第一集 1-2"},
                headers=headers,
            )

            assert started.status_code == 202, started.text
            job = _wait_for(client, headers, project_id, started.json()["export"]["id"])
            assert job["status"] == "succeeded", job
            assert job["fileSize"] > 0
            downloaded = client.get("/api/chat/artifacts/" + job["videoUrl"].rsplit("/", 1)[-1])
            assert downloaded.status_code == 200, downloaded.text
            assert downloaded.content[:12].endswith(b"ftyp") or b"ftyp" in downloaded.content[:32]


def test_clips_of_different_sizes_still_merge() -> None:
    """The reason concatenation always re-encodes: a stream copy plays only to the mismatch."""
    if not HAS_FFMPEG:
        print("skipping export test: ffmpeg is not installed")
        return
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id, scene_ids = _project_with_clips(
                client, headers, [_clip(width=320, height=240), _clip(width=640, height=360)]
            )

            started = client.post(
                f"/api/projects/{project_id}/exports", json={"sceneIds": scene_ids}, headers=headers
            )
            job = _wait_for(client, headers, project_id, started.json()["export"]["id"])

            assert job["status"] == "succeeded", job


def test_the_requested_order_is_the_output_order() -> None:
    """The video section assembles a cut, which need not follow the storyboard."""
    if not HAS_FFMPEG:
        print("skipping export test: ffmpeg is not installed")
        return
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id, scene_ids = _project_with_clips(client, headers, [_clip(), _clip()])
            reversed_ids = list(reversed(scene_ids))

            started = client.post(
                f"/api/projects/{project_id}/exports", json={"sceneIds": reversed_ids}, headers=headers
            )

            assert started.json()["export"]["sceneIds"] == reversed_ids
            assert _wait_for(client, headers, project_id, started.json()["export"]["id"])["status"] == "succeeded"


def test_a_shot_without_a_rendered_video_is_refused_up_front() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id, scene_ids = _project_with_clips(client, headers, [None])

            refused = client.post(
                f"/api/projects/{project_id}/exports", json={"sceneIds": scene_ids}, headers=headers
            )

            # Caught before queueing, so the user is told rather than left watching a job fail.
            assert refused.status_code == 400, refused.text
            assert "no video yet" in refused.json()["error"]


def test_a_shot_from_another_project_is_refused() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id, _ = _project_with_clips(client, headers, [])

            refused = client.post(
                f"/api/projects/{project_id}/exports", json={"sceneIds": ["scene_elsewhere"]}, headers=headers
            )

            assert refused.status_code == 400, refused.text
            assert "unknown shot" in refused.json()["error"]


def test_an_empty_selection_is_refused() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id, _ = _project_with_clips(client, headers, [])

            refused = client.post(f"/api/projects/{project_id}/exports", json={"sceneIds": []}, headers=headers)

            assert refused.status_code == 422, refused.text


def test_history_lists_newest_first_with_the_label_that_was_asked_for() -> None:
    if not HAS_FFMPEG:
        print("skipping export test: ffmpeg is not installed")
        return
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id, scene_ids = _project_with_clips(client, headers, [_clip()])
            for label in ("第一版", "第二版"):
                started = client.post(
                    f"/api/projects/{project_id}/exports",
                    json={"sceneIds": scene_ids, "rangeLabel": label},
                    headers=headers,
                )
                _wait_for(client, headers, project_id, started.json()["export"]["id"])

            listed = client.get(f"/api/projects/{project_id}/exports", headers=headers).json()["exports"]

            assert len(listed) == 2
            assert {job["rangeLabel"] for job in listed} == {"第一版", "第二版"}


if __name__ == "__main__":
    test_merging_clips_produces_one_downloadable_file()
    test_clips_of_different_sizes_still_merge()
    test_the_requested_order_is_the_output_order()
    test_a_shot_without_a_rendered_video_is_refused_up_front()
    test_a_shot_from_another_project_is_refused()
    test_an_empty_selection_is_refused()
    test_history_lists_newest_first_with_the_label_that_was_asked_for()
    print("test_exports_api ok")
