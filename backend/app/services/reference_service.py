"""Shared machinery behind character sheets and prop sheets.

Characters and props follow the same three-step flow — draft a prompt the user reviews,
draw a reference image from the approved prompt, then tile the results into one sheet the
renderer can carry. The two routers differ only in wording and storage location, so the
steps live here rather than twice.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.llms.registry import models
from app.services.artifact_service import artifact_absolute_path, store_artifact
from app.services.config_service import active_model_config
from app.services.media_service import SheetCell, merge_images
from app.services.usage_service import record_usage, require_model_balance


logger = logging.getLogger(__name__)

IMAGE_PROVIDERS = {"openai", "gemini", "qwen"}


def image_config(session: Session, user_id: int, purpose_label: str) -> dict[str, Any]:
    """The account's active image configuration, refused early if it cannot draw."""
    config = active_model_config(session, user_id, "image", purpose_label)
    require_model_balance(session, user_id, config)
    if config["provider"] not in IMAGE_PROVIDERS:
        raise HTTPException(400, "image generation currently only supports provider openai/gemini/qwen")
    return config


def script_config(session: Session, user_id: int, purpose_label: str) -> dict[str, Any]:
    config = active_model_config(session, user_id, "script", purpose_label)
    require_model_balance(session, user_id, config)
    return config


async def draft_prompt(
    config: dict[str, Any],
    user_id: int,
    system: str,
    user_text: str,
    model: str | None,
    usage_kind: str,
) -> str:
    """Ask the model for an image prompt. Returned for review, never applied here."""
    started_at = time.monotonic()
    try:
        result = await models.complete_text(
            config["provider"],
            config["apiKey"],
            model or config["model"],
            system,
            user_text,
            config.get("baseUrl", ""),
        )
    except Exception as exc:
        logger.warning("%s prompt drafting failed user=%s: %s", usage_kind, user_id, exc)
        raise HTTPException(502, f"failed to draft prompt: {str(exc)[:220]}") from exc
    record_usage(user_id, config, usage_kind, started_at, result.usage)
    return result.text[:4000]


async def draw_reference(config: dict[str, Any], user_id: int, prompt: str, usage_kind: str) -> tuple[bytes, str]:
    """Draw one reference image and hand back its bytes and file extension."""
    started_at = time.monotonic()
    try:
        image = await models.generate_image(
            config["apiKey"],
            config["model"],
            prompt,
            base_url=config.get("baseUrl", ""),
            provider=config["provider"],
        )
    except Exception as exc:
        logger.warning("%s image generation failed user=%s: %s", usage_kind, user_id, exc)
        raise HTTPException(502, f"failed to generate image: {str(exc)[:220]}") from exc
    record_usage(user_id, config, usage_kind, started_at, quantity=1)
    extension = (image.format or "png").strip().lower()
    extension = "jpg" if extension in {"jpg", "jpeg"} else extension if extension in {"png", "webp"} else "png"
    return image.data, extension


def read_cells(entries: list[tuple[str | None, str]]) -> list[SheetCell]:
    """Load stored images for a sheet, skipping the ones that are gone.

    A missing file costs the sheet one cell rather than the whole merge: losing a reference
    is a smaller harm than losing every other reference alongside it.
    """
    cells: list[SheetCell] = []
    for stored, label in entries:
        if not stored:
            continue
        try:
            cells.append(SheetCell(artifact_absolute_path(stored).read_bytes(), label))
        except (ValueError, OSError):
            logger.info("skipping unreadable sheet source label=%s", label)
    return cells


def store_sheet(category: str, scope: str, filename: str, entries: list[tuple[str | None, str]]) -> str:
    """Tile the given images into one sheet and persist it, returning its relative path."""
    cells = read_cells(entries)
    if not cells:
        raise HTTPException(400, "generate at least one reference image before merging")
    try:
        sheet = merge_images(cells)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return store_artifact(category, scope, filename, sheet)
