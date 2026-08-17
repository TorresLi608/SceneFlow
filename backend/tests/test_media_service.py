"""Contact sheets: the size and layout guarantees the reference pipeline depends on."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from app.services.media_service import (
    DEFAULT_CELL_WIDTH,
    LABEL_HEIGHT,
    SheetCell,
    compress_under,
    grid_columns,
    merge_images,
)


def _png(width: int, height: int, color: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _noisy_jpeg(width: int, height: int) -> bytes:
    """Incompressible content, so a size test exercises the real shrink path."""
    image = Image.frombytes("RGB", (width, height), bytes((index * 7919) % 256 for index in range(width * height * 3)))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=100, subsampling=0)
    return buffer.getvalue()


def test_sources_are_scaled_to_one_width_before_tiling() -> None:
    """The whole point of pre-scaling: a 4K source must not enter the sheet at 4K."""
    sheet = merge_images(
        [SheetCell(_png(3840, 2160), "青年"), SheetCell(_png(512, 512), "幼年")],
        columns=2,
    )

    image = Image.open(BytesIO(sheet))
    assert image.width == 2 * DEFAULT_CELL_WIDTH


def test_a_smaller_source_is_not_upscaled() -> None:
    """Enlarging buys bytes, not detail, so the cell keeps its source's height."""
    sheet = Image.open(BytesIO(merge_images([SheetCell(_png(320, 240), "道具")], columns=1)))

    assert sheet.width == DEFAULT_CELL_WIDTH
    # Row height follows the tallest source. Had the 240px image been stretched to the
    # 1080px cell width, this would be 810 + the label band instead.
    assert sheet.height == 240 + LABEL_HEIGHT


def test_the_grid_stays_roughly_square() -> None:
    assert grid_columns(0) == 1
    assert grid_columns(1) == 1
    assert grid_columns(4) == 2
    assert grid_columns(9) == 3
    assert grid_columns(10) == 4


def test_rows_wrap_when_no_column_count_is_given() -> None:
    cells = [SheetCell(_png(400, 400), f"角色{index}") for index in range(4)]

    sheet = Image.open(BytesIO(merge_images(cells)))

    # Four cells fall into 2x2, so the sheet is two cells wide rather than one long strip.
    assert sheet.width == 2 * DEFAULT_CELL_WIDTH


def test_an_oversized_sheet_is_compressed_under_the_ceiling() -> None:
    limit = 200 * 1024
    cells = [SheetCell(_noisy_jpeg(1600, 1600), f"角色{index}") for index in range(4)]

    sheet = merge_images(cells, columns=2, limit=limit)

    assert len(sheet) <= limit
    # Still a valid image after the shrink, not a truncated buffer.
    assert Image.open(BytesIO(sheet)).width > 0


def test_content_already_under_the_ceiling_is_returned_untouched() -> None:
    data = _png(64, 64)

    assert compress_under(data, limit=10 * 1024 * 1024) is data


def test_an_undecodable_cell_is_skipped_rather_than_failing_the_batch() -> None:
    """One broken portrait must not cost the user every other reference in the sheet."""
    sheet = merge_images(
        [SheetCell(b"not-an-image", "坏图"), SheetCell(_png(400, 400), "好图")],
        columns=1,
    )

    assert Image.open(BytesIO(sheet)).width == DEFAULT_CELL_WIDTH


def test_merging_nothing_readable_is_an_error() -> None:
    try:
        merge_images([SheetCell(b"not-an-image", "坏图")])
    except ValueError as exc:
        assert "no readable images" in str(exc)
    else:
        raise AssertionError("expected a sheet of only-broken images to fail")


def test_transparency_is_flattened_instead_of_turning_black() -> None:
    buffer = BytesIO()
    Image.new("RGBA", (200, 200), (255, 0, 0, 0)).save(buffer, format="PNG")

    sheet = Image.open(BytesIO(merge_images([SheetCell(buffer.getvalue(), "透明")], columns=1)))

    # The fully transparent source composites onto the white sheet, not onto black.
    pixel = sheet.convert("RGB").getpixel((DEFAULT_CELL_WIDTH // 2, 100))
    assert all(channel > 200 for channel in pixel), pixel


if __name__ == "__main__":
    test_sources_are_scaled_to_one_width_before_tiling()
    test_a_smaller_source_is_not_upscaled()
    test_the_grid_stays_roughly_square()
    test_rows_wrap_when_no_column_count_is_given()
    test_an_oversized_sheet_is_compressed_under_the_ceiling()
    test_content_already_under_the_ceiling_is_returned_untouched()
    test_an_undecodable_cell_is_skipped_rather_than_failing_the_batch()
    test_merging_nothing_readable_is_an_error()
    test_transparency_is_flattened_instead_of_turning_black()
    print("test_media_service ok")
