"""Shared machinery behind character sheets and prop sheets.

Characters and props follow the same three-step flow — draft a prompt the user reviews,
draw a reference image from the approved prompt, then tile the results into one sheet the
renderer can carry. The two routers differ only in wording and storage location, so the
steps live here rather than twice.
"""

from __future__ import annotations

import logging
import json
import time
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.llms.registry import models
from app.models import Asset, Character, CharacterState, Episode, Project, Prop, Scene, VoiceProfile
from app.services.artifact_service import artifact_absolute_path, store_artifact
from app.services.config_service import project_model_config
from app.services.media_service import SheetCell, merge_images
from app.services.usage_service import record_usage, require_model_balance
from app.utils.common import now


logger = logging.getLogger(__name__)

IMAGE_PROVIDERS = {"openai", "gemini", "qwen"}
REFERENCE_KINDS = {"character", "characterState", "prop", "tone", "sceneImage", "sceneVideo", "voice", "asset"}


def stored_generation_references(value: str | None) -> list[tuple[str, str]]:
    try:
        items = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(items, list):
        return []
    return [
        (str(item.get("kind")), str(item.get("id")))
        for item in items
        if isinstance(item, dict) and item.get("kind") in REFERENCE_KINDS and str(item.get("id") or "").strip()
    ]


def resolve_generation_references(
    session: Session,
    project_id: str,
    references: list[tuple[str, str]],
) -> dict[str, list[Any]]:
    """Resolve user-selected project assets to stored paths without trusting client URLs."""
    resolved: dict[str, list[Any]] = {"images": [], "videos": [], "audios": [], "labels": [], "items": []}
    seen: set[tuple[str, str]] = set()
    # ponytail: requests cap this at 64; batch by kind if reference-heavy projects make it hot.
    for kind, asset_id in references:
        key = (kind, asset_id)
        if key in seen:
            continue
        seen.add(key)
        stored: str | None = None
        label = ""
        bucket = "images"
        if kind == "character":
            character = session.exec(
                select(Character).where(
                    Character.id == asset_id,
                    Character.project_id == project_id,
                    Character.deleted_at.is_(None),
                )
            ).first()
            stored = (character.sheet_image_path or character.reference_image_path) if character else None
            label = character.name if character else ""
        elif kind == "characterState":
            state = session.exec(
                select(CharacterState)
                .join(Character, Character.id == CharacterState.character_id)
                .where(
                    CharacterState.id == asset_id,
                    CharacterState.deleted_at.is_(None),
                    Character.project_id == project_id,
                    Character.deleted_at.is_(None),
                )
            ).first()
            character = session.get(Character, state.character_id) if state else None
            stored = state.reference_image_path if state else None
            label = f"{character.name} · {state.name}" if state and character else ""
        elif kind == "prop":
            prop = session.exec(
                select(Prop).where(Prop.id == asset_id, Prop.project_id == project_id, Prop.deleted_at.is_(None))
            ).first()
            stored = prop.image_path if prop else None
            label = prop.name if prop else ""
        elif kind == "tone":
            episode = session.exec(
                select(Episode).where(
                    Episode.id == asset_id, Episode.project_id == project_id, Episode.deleted_at.is_(None)
                )
            ).first()
            stored = episode.tone_image_path if episode else None
            label = episode.title if episode else ""
        elif kind in {"sceneImage", "sceneVideo"}:
            scene = session.exec(
                select(Scene).where(Scene.id == asset_id, Scene.project_id == project_id, Scene.deleted_at.is_(None))
            ).first()
            stored = (scene.image_path if kind == "sceneImage" else scene.video_path) if scene else None
            label = f"分镜 {scene.order_num}" if scene else ""
            bucket = "images" if kind == "sceneImage" else "videos"
        elif kind == "voice":
            voice = session.exec(
                select(VoiceProfile).where(
                    VoiceProfile.id == asset_id,
                    VoiceProfile.project_id == project_id,
                    VoiceProfile.deleted_at.is_(None),
                )
            ).first()
            stored = voice.audio_path if voice else None
            label = voice.name if voice else ""
            bucket = "audios"
        elif kind == "asset":
            asset = session.exec(
                select(Asset).where(
                    Asset.id == asset_id,
                    Asset.project_id == project_id,
                    Asset.deleted_at.is_(None),
                )
            ).first()
            stored = asset.path if asset else None
            label = asset.name if asset else ""
            bucket = {"image": "images", "video": "videos", "audio": "audios"}.get(asset.kind, "") if asset else ""
            if not bucket:
                stored = None
        if not stored:
            raise HTTPException(400, "selected reference is unavailable")
        resolved[bucket].append((stored, label) if bucket == "images" else stored)
        resolved["labels"].append(label)
        resolved["items"].append({"kind": kind, "id": asset_id, "label": label, "media": bucket[:-1]})
    return resolved


def clear_generation_reference(session: Session, project_id: str, kind: str, asset_id: str) -> list[str]:
    """Detach one generated reference while preserving its character, prop, or voice card."""
    project = session.exec(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    ).first()
    if not project:
        raise HTTPException(404, "project not found")

    paths: list[str] = []
    stamp = now()

    def clear(row: Any, *columns: str) -> None:
        for column in columns:
            stored = getattr(row, column)
            if stored:
                paths.append(stored)
                setattr(row, column, None)
        row.updated_at = stamp
        session.add(row)

    def clear_project_sheet(column: str) -> None:
        stored = getattr(project, column)
        if stored:
            paths.append(stored)
            setattr(project, column, None)

    if kind == "character":
        row = session.exec(
            select(Character).where(
                Character.id == asset_id,
                Character.project_id == project_id,
                Character.deleted_at.is_(None),
            )
        ).first()
        if row:
            clear(row, "reference_image_path", "sheet_image_path")
            clear_project_sheet("character_sheet_path")
    elif kind == "characterState":
        row = session.exec(
            select(CharacterState)
            .join(Character, Character.id == CharacterState.character_id)
            .where(
                CharacterState.id == asset_id,
                CharacterState.deleted_at.is_(None),
                Character.project_id == project_id,
                Character.deleted_at.is_(None),
            )
        ).first()
        if row:
            clear(row, "reference_image_path")
            character = session.get(Character, row.character_id)
            if character:
                clear(character, "sheet_image_path")
            clear_project_sheet("character_sheet_path")
    elif kind == "prop":
        row = session.exec(
            select(Prop).where(Prop.id == asset_id, Prop.project_id == project_id, Prop.deleted_at.is_(None))
        ).first()
        if row:
            clear(row, "image_path")
            clear_project_sheet("prop_sheet_path")
    elif kind == "tone":
        row = session.exec(
            select(Episode).where(
                Episode.id == asset_id,
                Episode.project_id == project_id,
                Episode.deleted_at.is_(None),
            )
        ).first()
        if row:
            clear(row, "tone_image_path")
            row.tone_image_status = "idle"
            row.error_message = None
    elif kind in {"sceneImage", "sceneVideo"}:
        row = session.exec(
            select(Scene).where(Scene.id == asset_id, Scene.project_id == project_id, Scene.deleted_at.is_(None))
        ).first()
        if row:
            column = "image_path" if kind == "sceneImage" else "video_path"
            clear(row, column)
            setattr(row, "image_status" if kind == "sceneImage" else "video_status", "idle")
            row.error_message = None
    elif kind == "voice":
        row = session.exec(
            select(VoiceProfile).where(
                VoiceProfile.id == asset_id,
                VoiceProfile.project_id == project_id,
                VoiceProfile.deleted_at.is_(None),
            )
        ).first()
        if row:
            clear(row, "audio_path")
            clear_project_sheet("voice_sheet_path")
    elif kind == "asset":
        row = session.exec(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.project_id == project_id,
                Asset.deleted_at.is_(None),
            )
        ).first()
        if row:
            if row.path:
                paths.append(row.path)
            row.deleted_at = stamp
            row.updated_at = stamp
            session.add(row)
    else:
        row = None

    if not row:
        raise HTTPException(404, "reference asset not found")
    for scene in session.exec(
        select(Scene).where(Scene.project_id == project_id, Scene.deleted_at.is_(None))
    ).all():
        changed = False
        for column in ("image_references_json", "video_references_json"):
            references = stored_generation_references(getattr(scene, column))
            filtered = [item for item in references if item != (kind, asset_id)]
            if len(filtered) != len(references):
                setattr(
                    scene,
                    column,
                    json.dumps([{"kind": item_kind, "id": item_id} for item_kind, item_id in filtered], separators=(",", ":")),
                )
                changed = True
        if changed:
            scene.updated_at = stamp
            session.add(scene)
    project.updated_at = stamp
    session.add(project)
    return paths


def image_config(
    session: Session,
    user_id: int,
    purpose_label: str,
    project: Project | None = None,
) -> dict[str, Any]:
    """The image model this project draws with, refused early if it cannot draw."""
    config = project_model_config(session, user_id, project, "image", purpose_label)
    require_model_balance(session, user_id, config)
    if config["provider"] not in IMAGE_PROVIDERS:
        raise HTTPException(400, "image generation currently only supports provider openai/gemini/qwen")
    return config


def script_config(
    session: Session,
    user_id: int,
    purpose_label: str,
    project: Project | None = None,
) -> dict[str, Any]:
    config = project_model_config(session, user_id, project, "script", purpose_label)
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


async def draw_reference(
    config: dict[str, Any],
    user_id: int,
    prompt: str,
    usage_kind: str,
    size: str = "",
    quality: str = "",
) -> tuple[bytes, str]:
    """Draw one reference image and hand back its bytes and file extension.

    Size and quality come from the project's image defaults when it has them, and are
    passed through as the ratio/resolution vocabulary the user picked — `ModelRouter`
    already translates those per provider. They used to be omitted entirely, so a series
    configured for 4K portraits still got the provider's default resolution for every sheet.
    """
    started_at = time.monotonic()
    options: dict[str, Any] = {}
    if size:
        options["size"] = size
    if quality:
        options["quality"] = quality
    try:
        image = await models.generate_image(
            config["apiKey"],
            config["model"],
            prompt,
            base_url=config.get("baseUrl", ""),
            provider=config["provider"],
            **options,
        )
    except Exception as exc:
        logger.warning("%s image generation failed user=%s: %s", usage_kind, user_id, exc)
        raise HTTPException(502, f"failed to generate image: {str(exc)[:220]}") from exc
    record_usage(user_id, config, usage_kind, started_at, quantity=1)
    extension = (image.format or "png").strip().lower()
    extension = "jpg" if extension in {"jpg", "jpeg"} else extension if extension in {"png", "webp"} else "png"
    return image.data, extension


def image_options(project: Project | None) -> tuple[str, str]:
    """The (size, quality) a project's reference images are drawn at."""
    if project is None:
        return "", ""
    return (project.image_ratio or "").strip(), (project.image_resolution or "").strip()


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
