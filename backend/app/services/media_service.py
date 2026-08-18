"""Contact sheets and size ceilings for everything the pipeline hands to a model.

Two problems this solves, both of them cost problems:

*Coherence.* A model given one sheet holding every character, or every prop, renders them
consistently with each other. Twenty separate reference images cannot be passed at all —
providers cap reference counts in the low single digits (`MAX_REFERENCE_IMAGES`).

*Payload size.* Providers reject oversized images, and tokens are billed by pixel area, so
sources are scaled to a uniform width **before** tiling rather than pasted at native size —
twenty 4K frames tiled raw is a file nobody can upload.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import logging
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

from app.core.config import CJK_FONT_PATH
from app.services.artifact_service import CJK_FONT_CANDIDATES


logger = logging.getLogger(__name__)

# What a provider will accept in one reference image, and the ceiling the plan calls for.
MAX_SHEET_BYTES = 10 * 1024 * 1024
# Wide enough that a face on a tiled sheet is still legible, small enough that a 20-cell
# sheet stays a few megabytes.
DEFAULT_CELL_WIDTH = 1080
LABEL_HEIGHT = 56
LABEL_PADDING = 12
SHEET_BACKGROUND = (255, 255, 255)
LABEL_BACKGROUND = (244, 244, 245)
LABEL_COLOR = (24, 24, 27)
GRID_COLOR = (212, 212, 216)
# Below this, further JPEG quality cuts stop buying much and just destroy the reference.
MIN_JPEG_QUALITY = 45


@dataclass(frozen=True)
class SheetCell:
    """One tile: the image bytes and the name the model should associate with them."""

    data: bytes
    label: str = ""


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """A font that can draw Chinese labels, falling back to Pillow's built-in.

    The label is a convenience for the model, not the payload, so an environment without a
    CJK font renders boxes rather than failing the whole sheet.
    """
    for candidate in (CJK_FONT_PATH, *CJK_FONT_CANDIDATES):
        if candidate and Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    logger.info("no CJK font available for sheet labels; falling back to the bitmap font")
    return ImageFont.load_default()


def _open(data: bytes) -> Image.Image:
    image = Image.open(BytesIO(data))
    image.load()
    # Sheets are flattened to RGB, so alpha is composited over the sheet background here
    # rather than turning into black boxes at save time.
    if image.mode in {"RGBA", "LA", "P"}:
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, SHEET_BACKGROUND)
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return image.convert("RGB")


def _scaled(image: Image.Image, width: int) -> Image.Image:
    """Uniform width, aspect preserved. Never upscales: enlarging adds bytes, not detail."""
    if image.width <= width:
        return image
    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), Image.LANCZOS)


def grid_columns(count: int) -> int:
    """A roughly square grid, which keeps the sheet from becoming a long thin strip."""
    return max(1, math.ceil(math.sqrt(count))) if count else 1


def merge_images(
    cells: list[SheetCell],
    *,
    columns: int = 0,
    cell_width: int = DEFAULT_CELL_WIDTH,
    limit: int = MAX_SHEET_BYTES,
) -> bytes:
    """Tile images into one labelled contact sheet, scaled first and capped at `limit`.

    Cells that cannot be decoded are skipped rather than failing the sheet: one unreadable
    portrait should not cost the user every other reference in the batch.
    """
    loaded: list[tuple[Image.Image, str]] = []
    for index, cell in enumerate(cells):
        try:
            loaded.append((_scaled(_open(cell.data), cell_width), cell.label.strip()))
        except (OSError, ValueError):
            logger.info("skipping undecodable sheet cell index=%d label=%s", index, cell.label)
    if not loaded:
        raise ValueError("no readable images to merge")

    labelled = any(label for _, label in loaded)
    label_height = LABEL_HEIGHT if labelled else 0
    column_count = columns if columns > 0 else grid_columns(len(loaded))
    column_count = min(column_count, len(loaded))
    row_count = math.ceil(len(loaded) / column_count)
    # A uniform cell height keeps the grid aligned when sources differ in aspect ratio.
    cell_height = max(image.height for image, _ in loaded)

    sheet = Image.new(
        "RGB",
        (column_count * cell_width, row_count * (cell_height + label_height)),
        SHEET_BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    font = _load_font(28) if labelled else None

    for index, (image, label) in enumerate(loaded):
        column, row = index % column_count, index // column_count
        left = column * cell_width
        top = row * (cell_height + label_height)
        # Centred inside its cell, so a portrait next to a landscape still reads as a grid.
        sheet.paste(image, (left + (cell_width - image.width) // 2, top + (cell_height - image.height) // 2))
        draw.rectangle(
            [left, top, left + cell_width - 1, top + cell_height + label_height - 1],
            outline=GRID_COLOR,
            width=2,
        )
        if label_height and font is not None:
            band_top = top + cell_height
            draw.rectangle([left, band_top, left + cell_width - 1, band_top + label_height - 1], fill=LABEL_BACKGROUND)
            draw.text(
                (left + LABEL_PADDING, band_top + LABEL_PADDING),
                label[:40],
                fill=LABEL_COLOR,
                font=font,
            )

    return compress_under(_encode(sheet, quality=92), limit=limit, image=sheet)


def _encode(image: Image.Image, *, quality: int) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True, subsampling=1)
    return buffer.getvalue()


def compress_under(data: bytes, *, limit: int = MAX_SHEET_BYTES, image: Image.Image | None = None) -> bytes:
    """Shrink an image until it fits `limit`: quality first, then resolution.

    Quality goes first because it costs the least detail per byte saved; only once quality
    has bottomed out does the sheet start losing pixels.
    """
    if len(data) <= limit:
        return data
    source = image or _open(data)
    quality = 85
    while quality >= MIN_JPEG_QUALITY:
        encoded = _encode(source, quality=quality)
        if len(encoded) <= limit:
            return encoded
        quality -= 10

    working = source
    encoded = _encode(working, quality=MIN_JPEG_QUALITY)
    # Each pass drops linear size by 20%, so area by ~36%; bounded so a pathological input
    # cannot spin here forever.
    for _ in range(12):
        if len(encoded) <= limit:
            return encoded
        width = max(320, int(working.width * 0.8))
        if width == working.width:
            break
        working = working.resize((width, max(1, round(working.height * width / working.width))), Image.LANCZOS)
        encoded = _encode(working, quality=MIN_JPEG_QUALITY)
    logger.warning("could not compress image under %d bytes; returning %d bytes", limit, len(encoded))
    return encoded


# Fixed output format for concatenation. Sources come from different TTS providers at
# different sample rates and codecs, so a stream copy would produce a file that plays only
# up to the first boundary — everything is re-encoded to one format instead.
CONCAT_SAMPLE_RATE = 24_000
CONCAT_BITRATE = "128k"
CONCAT_TIMEOUT_SECONDS = 120


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg is required to merge audio; install it or use the provided Docker image")
    return path


def concat_audio(sources: list[bytes], *, extension: str = "mp3") -> bytes:
    """Join clips end to end into one track.

    Used for the voice sheet: every voice in the show introducing itself, in order, as a
    single reference the video model can listen through.
    """
    if not sources:
        raise ValueError("no audio to merge")
    ffmpeg = _ffmpeg()
    with tempfile.TemporaryDirectory(prefix="sceneflow-concat-") as directory:
        root = Path(directory)
        parts = []
        for index, data in enumerate(sources):
            part = root / f"{index:04d}.{extension}"
            part.write_bytes(data)
            parts.append(part)
        # The concat demuxer takes a list file, and its paths must be quoted for names the
        # shell would otherwise split. These are generated names, but the quoting is free.
        listing = root / "parts.txt"
        listing.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
        output = root / "merged.mp3"
        result = subprocess.run(
            [
                ffmpeg, "-nostdin", "-y",
                "-f", "concat", "-safe", "0", "-i", str(listing),
                "-ac", "1", "-ar", str(CONCAT_SAMPLE_RATE), "-b:a", CONCAT_BITRATE,
                str(output),
            ],
            check=False,
            capture_output=True,
            timeout=CONCAT_TIMEOUT_SECONDS,
        )
        if result.returncode != 0 or not output.is_file():
            detail = result.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
            raise RuntimeError(f"failed to merge audio: {detail[0][:220]}")
        return output.read_bytes()


CONCAT_VIDEO_TIMEOUT_SECONDS = 900


def concat_videos(sources: list[bytes], *, width: int, height: int, fps: int) -> bytes:
    """Join clips end to end into one MP4, normalising every clip to the same geometry.

    Always re-encoded, never stream-copied. Clips come from different models and settings,
    and the concat demuxer silently produces a file that plays only up to the first mismatch
    — which looks like a truncated export rather than an error. Scaling letterboxes rather
    than crops, so nothing the user framed gets cut off.
    """
    if not sources:
        raise ValueError("no video to merge")
    ffmpeg = _ffmpeg()
    scale = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps}"
    )
    with tempfile.TemporaryDirectory(prefix="sceneflow-video-") as directory:
        root = Path(directory)
        parts = []
        for index, data in enumerate(sources):
            part = root / f"{index:04d}.mp4"
            part.write_bytes(data)
            parts.append(part)

        command = [ffmpeg, "-nostdin", "-y"]
        for part in parts:
            command += ["-i", str(part)]
        # Normalise each input, then concat the normalised streams in one graph. Doing it as
        # a filter rather than through the demuxer is what lets the geometry differ.
        chains = "".join(f"[{index}:v]{scale}[v{index}];" for index in range(len(parts)))
        inputs = "".join(f"[v{index}]" for index in range(len(parts)))
        output = root / "merged.mp4"
        command += [
            "-filter_complex", f"{chains}{inputs}concat=n={len(parts)}:v=1:a=0[out]",
            "-map", "[out]",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output),
        ]
        result = subprocess.run(command, check=False, capture_output=True, timeout=CONCAT_VIDEO_TIMEOUT_SECONDS)
        if result.returncode != 0 or not output.is_file():
            detail = result.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
            raise RuntimeError(f"failed to merge video: {detail[0][:220]}")
        return output.read_bytes()
