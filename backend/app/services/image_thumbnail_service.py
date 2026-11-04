"""Small, private derivatives for standalone image history; originals stay untouched."""

from __future__ import annotations

from io import BytesIO
import logging
from pathlib import Path, PurePosixPath
import tempfile

from PIL import Image, ImageOps

from app.services.artifact_service import artifact_absolute_path


logger = logging.getLogger(__name__)


def image_thumbnail_path(relative: str) -> str:
    return str(PurePosixPath(relative).with_suffix(".thumb.webp"))


def create_image_thumbnail(data: bytes) -> bytes | None:
    """Run before opening the write transaction, in the image request's worker thread."""
    try:
        with Image.open(BytesIO(data)) as image:
            oriented = ImageOps.exif_transpose(image)
            thumbnail = ImageOps.fit(oriented.convert("RGBA"), (128, 128), method=Image.Resampling.LANCZOS)
            output = BytesIO()
            thumbnail.save(output, format="WEBP", quality=75)
            return output.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        # A derivative failure must not discard an already paid-for original.
        logger.warning("image thumbnail encoding failed error_type=%s", type(exc).__name__)
        return None


def store_image_thumbnail(relative: str, data: bytes) -> None:
    temporary: Path | None = None
    try:
        path = artifact_absolute_path(image_thumbnail_path(relative))
        # Atomic replacement keeps the file endpoint from serving an incomplete WebP.
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".thumbnail-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        temporary.replace(path)
    except (OSError, ValueError) as exc:
        logger.warning("image thumbnail storage failed error_type=%s", type(exc).__name__)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("image thumbnail temporary file cleanup failed")
