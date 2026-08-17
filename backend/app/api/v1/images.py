from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import db
from app.api.deps import current_user_id
from app.llms.registry import models
from app.services.artifact_service import decode_image_data_url, save_binary_artifact
from app.services.config_service import active_model_config, official_model_config_any, user_model_config_any
from app.services.usage_service import record_usage, require_model_balance


router = APIRouter(prefix="/api/images", tags=["images"])

QUALITY = {"1K": "low", "2K": "medium", "4K": "high"}
RATIO = {
    "1:1": "1024x1024",
    "2:3": "1024x1536",
    "3:2": "1536x1024",
    "3:4": "1024x1536",
    "4:3": "1536x1024",
    "16:9": "1536x1024",
    "9:16": "1024x1536",
    "21:9": "1536x1024",
    "9:21": "1024x1536",
}


def parse_reference(value: dict[str, Any], index: int) -> tuple[str, bytes, str]:
    try:
        data, mime_type, ext = decode_image_data_url(str(value.get("data", "")))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    name = str(value.get("name") or f"reference-{index}.{ext}")[:120]
    return name, data, mime_type


def persist_image(data: bytes, ext: str) -> str:
    ext = "jpg" if ext.lower() in {"jpg", "jpeg"} else ext.lower()
    ext = ext if ext in {"png", "jpg", "webp"} else "png"
    media_type = "image/jpeg" if ext == "jpg" else f"image/{ext}"
    return save_binary_artifact("images", f"generated-image.{ext}", data, media_type)


@router.post("/generate")
async def generate_image(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt is required")

    references = payload.get("references") if isinstance(payload.get("references"), list) else []
    if len(references) > 4:
        raise HTTPException(400, "at most 4 reference images are supported")

    config_id = payload.get("configId")
    official_config_id = payload.get("officialConfigId")
    with db() as session:
        if official_config_id:
            config = official_model_config_any(session, int(official_config_id), ("image", "general"), "图片生成")
        elif config_id:
            config = user_model_config_any(session, user_id, int(config_id), ("image", "general"), "图片生成")
        else:
            config = active_model_config(session, user_id, "image", "图片生成")
        require_model_balance(session, user_id, config)

    if config["provider"] not in {"openai", "gemini", "qwen"}:
        raise HTTPException(400, "image generation currently only supports provider openai/gemini/qwen")

    ratio = str(payload.get("ratio") or "auto")
    resolution = str(payload.get("resolution") or "2K")
    size = ratio if config["provider"] in {"gemini", "qwen"} else RATIO.get(ratio, "auto")
    quality = resolution if config["provider"] in {"gemini", "qwen"} else QUALITY.get(resolution, "medium")
    started_at = time.monotonic()
    try:
        if references:
            images = [parse_reference(item, index + 1) for index, item in enumerate(references)]
            result = await models.edit_image(config["apiKey"], config["model"], prompt, images, size, quality, config.get("baseUrl", ""), config["provider"])
        else:
            result = await models.generate_image(config["apiKey"], config["model"], prompt, size, quality, config.get("baseUrl", ""), config["provider"])
    except Exception as exc:
        raise HTTPException(502, "AI 图片生成失败：" + str(exc)[:220]) from exc
    record_usage(user_id, config, "image", started_at, quantity=1)

    return {
        "image": {
            "url": persist_image(result.data, result.format),
            "model": config["model"],
            "source": "image-to-image" if references else "text-to-image",
        }
    }
