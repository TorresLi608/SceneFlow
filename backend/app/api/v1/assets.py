"""Project-owned custom media library."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.api.deps import current_user_id
from app.core.database import db
from app.models import Asset, Scene
from app.schemas.requests import CreateAssetRequest, MergeAssetsRequest, UpdateAssetRequest
from app.schemas.serializers import asset_json
from app.services.artifact_service import artifact_absolute_path, decode_image_data_url, remove_stored_artifacts, store_artifact
from app.services.media_service import SheetCell, merge_images
from app.services.project_service import owned_project
from app.services.reference_service import resolve_generation_references
from app.utils.common import new_id, now


router = APIRouter(prefix="/api/projects", tags=["assets"])
ALLOWED_KINDS = {"image", "video", "audio"}


def _remote_url(value: str) -> str | None:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        return None
    return value.strip()


def _media_type_for_url(value: str, kind: str) -> str:
    guessed = mimetypes.guess_type(urlparse(value).path)[0]
    return guessed or {"image": "image/*", "video": "video/*", "audio": "audio/*"}[kind]


def _store_data(project_id: str, asset_id: str, kind: str, data: str) -> tuple[str, str]:
    remote = _remote_url(data)
    if remote:
        if kind == "image":
            try:
                request = Request(remote, headers={"User-Agent": "SceneFlow/1.0"})
                with urlopen(request, timeout=20) as response:  # noqa: S310 - validated http(s) URL
                    raw = response.read(12 * 1024 * 1024)
                if not raw:
                    raise ValueError("empty image")
                media_type = _media_type_for_url(remote, kind)
                extension = (media_type.split("/", 1)[-1] if "/" in media_type else "png").replace("jpeg", "jpg")
                extension = extension if extension in {"png", "jpg", "webp"} else "png"
                return store_artifact("assets", project_id, f"{asset_id}.{extension}", raw), media_type
            except Exception as exc:
                raise HTTPException(400, "unable to read image URL") from exc
        return remote, _media_type_for_url(remote, kind)
    if kind != "image":
        raise HTTPException(400, "video and audio assets require a valid http(s) URL")
    try:
        raw, mime, extension = decode_image_data_url(data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return store_artifact("assets", project_id, f"{asset_id}.{extension}", raw), mime


def _owned_asset(session, project_id: str, asset_id: str) -> Asset:
    asset = session.exec(
        select(Asset).where(Asset.id == asset_id, Asset.project_id == project_id, Asset.deleted_at.is_(None))
    ).first()
    if not asset:
        raise HTTPException(404, "asset not found")
    return asset


def _read_image(value: str) -> bytes:
    remote = _remote_url(value)
    if remote:
        try:
            request = Request(remote, headers={"User-Agent": "SceneFlow/1.0"})
            with urlopen(request, timeout=20) as response:  # noqa: S310 - user supplied URL is validated above
                data = response.read(12 * 1024 * 1024)
            if not data:
                raise ValueError("empty image")
            return data
        except Exception as exc:
            raise HTTPException(400, "unable to read image URL") from exc
    try:
        return artifact_absolute_path(value).read_bytes()
    except (ValueError, OSError) as exc:
        raise HTTPException(400, "image asset is unavailable") from exc


@router.get("/{project_id}/assets")
def list_assets(project_id: str, kind: str | None = None, user_id: int = Depends(current_user_id)) -> dict:
    with db() as session:
        owned_project(session, project_id, user_id)
        query = select(Asset).where(Asset.project_id == project_id, Asset.deleted_at.is_(None)).order_by(Asset.created_at)
        if kind in ALLOWED_KINDS:
            query = query.where(Asset.kind == kind)
        assets = session.exec(query).all()
        return {"assets": [asset_json(asset) for asset in assets]}


@router.post("/{project_id}/assets", status_code=201)
def create_asset(project_id: str, body: CreateAssetRequest, user_id: int = Depends(current_user_id)) -> dict:
    stamp = now()
    asset_id = new_id("asset")
    path, media_type = _store_data(project_id, asset_id, body.kind, body.data)
    with db() as session:
        owned_project(session, project_id, user_id)
        asset = Asset(
            id=asset_id,
            project_id=project_id,
            name=body.name,
            description=body.description,
            kind=body.kind,
            media_type=media_type,
            path=path,
            created_at=stamp,
            updated_at=stamp,
        )
        session.add(asset)
        session.flush()
        return {"asset": asset_json(asset)}


@router.patch("/{project_id}/assets/{asset_id}")
def update_asset(project_id: str, asset_id: str, body: UpdateAssetRequest, user_id: int = Depends(current_user_id)) -> dict:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "no fields to update")
    with db() as session:
        owned_project(session, project_id, user_id)
        asset = _owned_asset(session, project_id, asset_id)
        old_path = asset.path
        if body.name is not None:
            asset.name = body.name
        if body.description is not None:
            asset.description = body.description
        if body.data is not None:
            asset.path, asset.media_type = _store_data(project_id, asset.id, asset.kind, body.data)
        asset.updated_at = now()
        session.add(asset)
        session.flush()
        result = {"asset": asset_json(asset)}
    if body.data is not None and old_path != asset.path and not _remote_url(old_path):
        remove_stored_artifacts([old_path])
    return result


@router.delete("/{project_id}/assets/{asset_id}", status_code=204)
def delete_asset(project_id: str, asset_id: str, user_id: int = Depends(current_user_id)) -> None:
    with db() as session:
        owned_project(session, project_id, user_id)
        asset = _owned_asset(session, project_id, asset_id)
        asset.deleted_at = now()
        asset.updated_at = asset.deleted_at
        session.add(asset)
        path = asset.path
        for scene in session.exec(select(Scene).where(Scene.project_id == project_id, Scene.deleted_at.is_(None))).all():
            for column in ("image_references_json", "video_references_json"):
                try:
                    refs = json.loads(getattr(scene, column) or "[]")
                except (TypeError, ValueError):
                    refs = []
                filtered = [ref for ref in refs if not (isinstance(ref, dict) and ref.get("kind") == "asset" and ref.get("id") == asset_id)]
                if len(filtered) != len(refs):
                    setattr(scene, column, json.dumps(filtered, separators=(",", ":")))
                    setattr(scene, f"{column.removesuffix('_json')}_explicit", True)
                    scene.updated_at = asset.updated_at
                    session.add(scene)
    if not _remote_url(path):
        remove_stored_artifacts([path])


@router.post("/{project_id}/assets/merge", status_code=201)
def merge_assets(project_id: str, body: MergeAssetsRequest, user_id: int = Depends(current_user_id)) -> dict:
    if body.kind != "image":
        raise HTTPException(400, "only image assets can be merged")
    with db() as session:
        owned_project(session, project_id, user_id)
        selected_assets: list[tuple[str, str, str]] = []
        for asset_id in body.asset_ids:
            if asset_id.startswith("scene:"):
                asset_id = asset_id.removeprefix("scene:")
                scene = session.exec(select(Scene).where(Scene.id == asset_id, Scene.project_id == project_id, Scene.deleted_at.is_(None))).first()
                if not scene or not scene.image_path:
                    raise HTTPException(404, "scene image not found")
                selected_assets.append((scene.image_path, f"分镜 {scene.order_num}", "image"))
            elif ":" in asset_id:
                ref_kind, ref_id = asset_id.split(":", 1)
                resolved = resolve_generation_references(session, project_id, [(ref_kind, ref_id)])
                if len(resolved["images"]) != 1:
                    raise HTTPException(404, "reference image not found")
                path, label = resolved["images"][0]
                selected_assets.append((path, label, "image"))
            else:
                asset = _owned_asset(session, project_id, asset_id)
                selected_assets.append((asset.path, asset.name, asset.kind))
        if any(kind != "image" for _, _, kind in selected_assets):
            raise HTTPException(400, "only image assets can be merged")
        cells = [SheetCell(_read_image(path), name) for path, name, _ in selected_assets]
        try:
            merged = merge_images(cells)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        asset_id = new_id("asset")
        path = store_artifact("assets", project_id, f"{asset_id}.jpg", merged)
        stamp = now()
        asset = Asset(
            id=asset_id,
            project_id=project_id,
            name=body.name,
            description=body.description,
            kind="image",
            media_type="image/jpeg",
            path=path,
            created_at=stamp,
            updated_at=stamp,
        )
        session.add(asset)
        session.flush()
        return {"asset": asset_json(asset)}
