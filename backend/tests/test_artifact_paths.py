from __future__ import annotations

from pathlib import Path
import tempfile

from app.services import artifact_service
from app.services.artifact_service import (
    artifact_absolute_path,
    artifact_from_token,
    signed_url_for_stored,
    store_artifact,
    stored_relative_path,
)


def _isolated(directory: str) -> Path:
    artifact_service.PRIVATE_GENERATED_DIR = Path(directory)
    # Resolved because artifact_absolute_path resolves too, and on macOS the temp dir is a
    # symlink (/var -> /private/var) that would otherwise make the comparison fail.
    return Path(directory).resolve()


def test_stored_path_survives_resigning() -> None:
    """A row keeps the path; every response mints a new link from it."""
    original = artifact_service.PRIVATE_GENERATED_DIR
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = _isolated(directory)
            relative = store_artifact("projects", "proj_1", "scene_1.png", b"frame-bytes")

            assert not relative.startswith("http")
            assert artifact_absolute_path(relative).is_relative_to(root)

            first = signed_url_for_stored(relative, "scene-1")
            second = signed_url_for_stored(relative, "scene-1")
            for url in (first, second):
                path, filename, media_type, inline = artifact_from_token(url.rsplit("/", 1)[-1])
                assert path.read_bytes() == b"frame-bytes"
                # The extension follows the stored file, not the caller's naming.
                assert (filename, media_type, inline) == ("scene-1.png", "image/png", True)
    finally:
        artifact_service.PRIVATE_GENERATED_DIR = original


def test_legacy_signed_url_yields_its_stored_path() -> None:
    """The migration off stored URLs has to recover the path from an existing link."""
    original = artifact_service.PRIVATE_GENERATED_DIR
    try:
        with tempfile.TemporaryDirectory() as directory:
            _isolated(directory)
            relative = store_artifact("projects", "proj_1", "scene_1.mp3", b"voice")
            url = signed_url_for_stored(relative, "scene-1")

            assert stored_relative_path(url) == relative
    finally:
        artifact_service.PRIVATE_GENERATED_DIR = original


def test_stored_path_rejects_traversal() -> None:
    original = artifact_service.PRIVATE_GENERATED_DIR
    try:
        with tempfile.TemporaryDirectory() as directory:
            _isolated(directory)
            for value in ("", "../secrets.txt", "/etc/passwd", "projects/../../escape.png"):
                try:
                    artifact_absolute_path(value)
                except ValueError:
                    continue
                raise AssertionError(f"expected {value!r} to be rejected")
    finally:
        artifact_service.PRIVATE_GENERATED_DIR = original


if __name__ == "__main__":
    test_stored_path_survives_resigning()
    test_legacy_signed_url_yields_its_stored_path()
    test_stored_path_rejects_traversal()
