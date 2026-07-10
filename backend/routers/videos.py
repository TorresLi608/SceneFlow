from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from config import GENERATED_DIR, PUBLIC_BASE_URL
from config_service import active_model_config, official_model_config, user_model_config
from database import db
from security import current_user_id
from utils import new_id
from video_service import generate_video, parse_reference, resolve_video_settings


router = APIRouter(prefix="/api/videos", tags=["videos"])


def persist_video(data: bytes) -> str:
    video_dir = GENERATED_DIR / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    path = video_dir / f"{new_id('video')}.mp4"
    path.write_bytes(data)
    return f"{PUBLIC_BASE_URL}/generated/videos/{path.name}"


@router.post("/generate")
async def generate_video_route(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt is required")

    reference = payload.get("reference")
    if reference is not None and not isinstance(reference, dict):
        raise HTTPException(400, "reference must be an image data URL")

    config_id = payload.get("configId")
    official_config_id = payload.get("officialConfigId")
    with db() as conn:
        if official_config_id:
            config = official_model_config(conn, int(official_config_id), "video", "视频生成")
        elif config_id:
            config = user_model_config(conn, user_id, int(config_id), "video", "视频生成")
        else:
            config = active_model_config(conn, user_id, "video", "视频生成")

    resolution = str(payload.get("resolution") or "1280x720")
    try:
        fps = int(payload.get("fps") or 24)
        duration = int(payload.get("duration") or 4)
        resolve_video_settings(config["provider"], resolution, fps, duration)
        if reference:
            parse_reference(reference)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)[:220]) from exc

    try:
        result = await generate_video(
            provider=config["provider"],
            api_key=config["apiKey"],
            model=config["model"],
            prompt=prompt,
            resolution=resolution,
            fps=fps,
            duration=duration,
            reference=reference,
            base_url=config.get("baseUrl", ""),
        )
    except Exception as exc:
        raise HTTPException(502, "AI 视频生成失败：" + str(exc)[:220]) from exc

    return {
        "video": {
            "url": persist_video(result.data),
            "model": config["model"],
            "source": "image-to-video" if reference else "text-to-video",
            "fps": fps,
        }
    }
