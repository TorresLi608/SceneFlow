from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import db
from app.api.deps import current_user_id
from app.llms.registry import models
from app.schemas.serializers import generation_record_json
from app.services.artifact_service import decode_image_data_url
from app.services.config_service import active_model_config, official_model_config_any, user_model_config_any
from app.services.generation_record_service import delete_generation_record, list_generation_records, save_generation_record
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


def persist_image(user_id: int, config: dict[str, Any], data: bytes, ext: str, *, prompt: str, source: str, options: dict[str, Any]) -> dict[str, Any]:
    """Store the result on the account's history and return its wire shape (with a signed URL)."""
    ext = "jpg" if ext.lower() in {"jpg", "jpeg"} else ext.lower()
    ext = ext if ext in {"png", "jpg", "webp"} else "png"
    media_type = "image/jpeg" if ext == "jpg" else f"image/{ext}"
    with db() as session:
        record = save_generation_record(
            session, user_id, "image", data, f"generated-image.{ext}", media_type, prompt=prompt, config=config, source=source, options=options
        )
        return generation_record_json(record)


@router.get("/history")
def list_image_history(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        return {"items": [generation_record_json(item) for item in list_generation_records(session, user_id, "image")]}


@router.delete("/history/{record_id}", status_code=204)
def delete_image_history(record_id: str, user_id: int = Depends(current_user_id)) -> None:
    with db() as session:
        delete_generation_record(session, user_id, "image", record_id)


@router.post("/generate")
async def generate_image(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt is required")

    references = payload.get("references") if isinstance(payload.get("references"), list) else []

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

    maximum = int(config.get("imageMaxReferenceImages", 4))
    if len(references) > maximum:
        raise HTTPException(400, f"selected model accepts at most {maximum} reference images")

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

    source = "image-to-image" if references else "text-to-image"
    record = persist_image(user_id, config, result.data, result.format, prompt=prompt, source=source, options={"resolution": resolution, "ratio": ratio})
    return {
        "image": {
            "url": record["url"],
            "model": config["model"],
            "source": source,
        },
        "history": record,
    }
