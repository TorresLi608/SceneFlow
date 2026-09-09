"""Video export: assembling chosen shots into one file."""

from __future__ import annotations

from pathlib import Path
import json
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


def _clip(seconds: float = 0.5, width: int = 320, height: int = 240, *, with_audio: bool = False) -> bytes:
    """A real MP4, so the concat path is exercised rather than mocked."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "clip.mp4"
        cmd = [
            "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
            "-i", f"testsrc=size={width}x{height}:rate=12:duration={seconds}",
        ]
        if with_audio:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
            cmd += ["-c:v", "libx264", "-c:a", "aac"]
        cmd += ["-pix_fmt", "yuv420p", str(path)]
        subprocess.run(
            cmd,
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


def test_deleting_an_export_record_removes_it() -> None:
    if not HAS_FFMPEG:
        print("skipping export test: ffmpeg is not installed")
        return
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            project_id, scene_ids = _project_with_clips(client, headers, [_clip()])
            started = client.post(
                f"/api/projects/{project_id}/exports",
                json={"sceneIds": scene_ids, "rangeLabel": "待删除"},
                headers=headers,
            )
            export_id = started.json()["export"]["id"]
            _wait_for(client, headers, project_id, export_id)

            # Deleting the export succeeds
            deleted = client.delete(f"/api/projects/{project_id}/exports/{export_id}", headers=headers)
            assert deleted.status_code == 200, deleted.text
            assert deleted.json() == {"success": True}

            # Fetching the deleted export returns 404
            missing = client.get(f"/api/projects/{project_id}/exports/{export_id}", headers=headers)
            assert missing.status_code == 404

            # Listing exports returns empty
            listed = client.get(f"/api/projects/{project_id}/exports", headers=headers).json()["exports"]
            assert len(listed) == 0


def test_merging_clips_with_audio_preserves_audio_stream() -> None:
    if not HAS_FFMPEG:
        print("skipping export test: ffmpeg is not installed")
        return
    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            clip1 = _clip(seconds=0.5, with_audio=True)
            clip2 = _clip(seconds=0.5, with_audio=False)
            project_id, scene_ids = _project_with_clips(client, headers, [clip1, clip2])

            started = client.post(
                f"/api/projects/{project_id}/exports",
                json={"sceneIds": scene_ids, "rangeLabel": "有音频合并"},
                headers=headers,
            )
            assert started.status_code == 202, started.text
            finished = _wait_for(client, headers, project_id, started.json()["export"]["id"])
            assert finished["status"] == "succeeded"

            with database.db() as session:
                from app.models import ExportJob
                job_row = session.get(ExportJob, started.json()["export"]["id"])
                assert job_row is not None and job_row.output_path is not None
                output_file = artifact_service.artifact_absolute_path(job_row.output_path)
            assert output_file.is_file()

            ffprobe = shutil.which("ffprobe")
            if ffprobe:
                probe_res = subprocess.run(
                    [
                        ffprobe, "-v", "error",
                        "-select_streams", "a",
                        "-show_entries", "stream=index,codec_name",
                        "-of", "json",
                        str(output_file),
                    ],
                    capture_output=True,
                    check=True,
                )
                info = json.loads(probe_res.stdout)
                streams = info.get("streams") or []
                assert len(streams) >= 1
                assert streams[0]["codec_name"] == "aac"



def test_episode_composition_then_series_export_preserves_order_and_audio() -> None:
    if not HAS_FFMPEG:
        print("skipping two-stage export: ffmpeg is not installed")
        return
    from app.models import Episode, ExportJob, Project
    from app.services import export_service
    from sqlmodel import select

    with tempfile.TemporaryDirectory() as directory:
        with _app(directory) as (client, headers):
            first_clip, second_clip = _clip(with_audio=True), _clip(seconds=0.75)
            project_id, ids = _project_with_clips(client, headers, [first_clip, second_clip, None])
            with database.db() as session:
                episode_id = session.get(Scene, ids[0]).episode_id
                project = session.get(Project, project_id)
                project.width, project.height, project.fps = 320, 240, 12
                session.add(project)
            second = client.post(f"/api/projects/{project_id}/episodes", headers=headers, json={"title": "第二集"}).json()["episode"]["id"]
            url = f"/api/projects/{project_id}/episodes/{episode_id}/video"
            for payload, status in (([], 422), ([ids[0], ids[0]], 422), ([ids[2]], 400), (["missing"], 400)):
                response = client.post(url, headers=headers, json={"sceneIds": payload})
                assert response.status_code == status, response.text
            wrong_episode = client.post(f"/api/projects/{project_id}/episodes/{second}/video", headers=headers, json={"sceneIds": ids[:1]})
            assert wrong_episode.status_code == 400, wrong_episode.text
            absent = client.post(f"/api/projects/{project_id}/exports", headers=headers, json={"episodeIds": [second]})
            assert absent.status_code == 400, absent.text

            original = export_service.concat_videos
            captured = []
            entered, release = threading.Event(), threading.Event()
            def recording(clips, **kwargs):
                captured.append(list(clips))
                entered.set()
                assert release.wait(10)
                return original(clips, **kwargs)
            export_service.concat_videos = recording
            try:
                started = client.post(url, headers=headers, json={"sceneIds": ids[1::-1]})
                assert started.status_code == 202, started.text
                job_id = started.json()["export"]["id"]
                assert entered.wait(10)
                duplicate = client.post(url, headers=headers, json={"sceneIds": ids[:1]})
                assert duplicate.status_code == 409, duplicate.text
                assert client.delete(f"/api/projects/{project_id}/exports/{job_id}", headers=headers).status_code == 409
                release.set()
                completed = _wait_for(client, headers, project_id, job_id)
                assert completed["status"] == "succeeded", completed
                assert captured[0] == [second_clip, first_clip]
            finally:
                release.set()
                export_service.concat_videos = original
            with database.db() as session:
                first_path = session.get(Episode, episode_id).video_path
                assert first_path == session.get(ExportJob, job_id).output_path
                other = session.get(Episode, second)
                other.video_path = artifact_service.store_artifact("exports", project_id, "second.mp4", second_clip)
                session.add(other)
            series = client.post(f"/api/projects/{project_id}/exports", headers=headers, json={"episodeIds": [second, episode_id]})
            assert series.status_code == 202, series.text
            assert series.json()["export"]["episodeIds"] == [second, episode_id]
            with database.db() as session:
                assert export_service.resolve_episode_videos(session, project_id, [second, episode_id]) == [session.get(Episode, second).video_path, first_path]
            finished = _wait_for(client, headers, project_id, series.json()["export"]["id"])
            assert finished["status"] == "succeeded", finished
            with database.db() as session:
                output = artifact_service.artifact_absolute_path(session.get(ExportJob, finished["id"]).output_path)
            streams = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)], check=True, capture_output=True, text=True).stdout)["streams"]
            assert any(stream["codec_type"] == "audio" for stream in streams)
            assert client.get(f"/api/projects/{project_id}/episodes", headers=headers).json()["episodes"][0]["videoUrl"]

            def fail(*args, **kwargs):
                raise ValueError("test composition failure")
            export_service.concat_videos = fail
            try:
                retry = client.post(url, headers=headers, json={"sceneIds": ids[:1]}).json()["export"]
                assert _wait_for(client, headers, project_id, retry["id"])["status"] == "failed"
                with database.db() as session:
                    assert session.get(Episode, episode_id).video_path == first_path
            finally:
                export_service.concat_videos = original
            with database.db() as session:
                stale = export_service.create_export(session, 1, project_id, ids[:1], "interrupted", target_episode_id=episode_id)
                stale_id = stale.id
            export_service.recover_interrupted_exports()
            with database.db() as session:
                assert session.get(ExportJob, stale_id).status == "failed"
                assert session.get(Episode, episode_id).video_path == first_path

if __name__ == "__main__":
    test_merging_clips_produces_one_downloadable_file()
    test_clips_of_different_sizes_still_merge()
    test_the_requested_order_is_the_output_order()
    test_a_shot_without_a_rendered_video_is_refused_up_front()
    test_a_shot_from_another_project_is_refused()
    test_an_empty_selection_is_refused()
    test_history_lists_newest_first_with_the_label_that_was_asked_for()
    test_deleting_an_export_record_removes_it()
    test_merging_clips_with_audio_preserves_audio_stream()
    test_episode_composition_then_series_export_preserves_order_and_audio()
    print("test_exports_api ok")
