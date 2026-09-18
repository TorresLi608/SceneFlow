from __future__ import annotations

from typing import Any
import time

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import db
from app.api.deps import current_user_id
from app.schemas.serializers import generation_record_json
from app.services.config_service import active_model_config, official_model_config, user_model_config
from app.services.generation_record_service import delete_generation_record, list_generation_records, save_generation_record
from app.services.system_setting_service import generation_retention_days
from app.services.usage_service import record_usage, require_model_balance
from app.services.video_service import generate_video, resolve_qwen_video_quality, resolve_video_options, resolve_video_settings, validate_qwen_video_input, validate_video_inputs


router = APIRouter(prefix="/api/videos", tags=["videos"])


def persist_video(user_id: int, config: dict[str, Any], data: bytes, *, prompt: str, source: str, options: dict[str, Any]) -> dict[str, Any]:
    """Store the result on the account's history and return its wire shape (with a signed URL)."""
    with db() as session:
        record = save_generation_record(
            session, user_id, "video", data, "generated-video.mp4", "video/mp4", prompt=prompt, config=config, source=source, options=options
        )
        return generation_record_json(record)


@router.get("/history")
def list_video_history(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """The account's video results plus the admin retention window (0 = kept forever); see `images.py`."""
    with db() as session:
        return {
            "items": [generation_record_json(item) for item in list_generation_records(session, user_id, "video")],
            "retentionDays": generation_retention_days(session),
        }


@router.delete("/history/{record_id}", status_code=204)
def delete_video_history(record_id: str, user_id: int = Depends(current_user_id)) -> None:
    with db() as session:
        delete_generation_record(session, user_id, "video", record_id)


@router.post("/generate")
async def generate_video_route(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt is required")

    references = payload.get("references") or ([payload["reference"]] if payload.get("reference") else [])
    reference_videos = payload.get("referenceVideos") or ([payload["referenceVideo"]] if payload.get("referenceVideo") else [])
    reference_audios = payload.get("referenceAudios") or ([payload.get("referenceAudio") or payload.get("drivingAudio")] if payload.get("referenceAudio") or payload.get("drivingAudio") else [])
    if not isinstance(references, list) or any(not isinstance(item, dict) for item in references):
        raise HTTPException(400, "references must be image data URLs")
    if not isinstance(reference_videos, list) or any(not isinstance(item, dict) for item in reference_videos):
        raise HTTPException(400, "referenceVideos must be a list of video inputs")
    if not isinstance(reference_audios, list) or any(not isinstance(item, dict) for item in reference_audios):
        raise HTTPException(400, "referenceAudios must be a list of audio inputs")

    config_id = payload.get("configId")
    official_config_id = payload.get("officialConfigId")
    with db() as session:
        if official_config_id:
            config = official_model_config(session, int(official_config_id), "video", "视频生成")
        elif config_id:
            config = user_model_config(session, user_id, int(config_id), "video", "视频生成")
        else:
            config = active_model_config(session, user_id, "video", "视频生成")
        require_model_balance(session, user_id, config)

    started_at = time.monotonic()
    try:
        quality, aspect_ratio, fps, duration, prompt_extend = resolve_video_options(payload, config["videoCapabilities"])
        validate_video_inputs(config["videoCapabilities"], references, reference_videos, reference_audios)
        if config["provider"] == "qwen":
            if quality:
                quality = resolve_qwen_video_quality(str(quality))
            validate_qwen_video_input(config["model"], references, reference_videos)
        elif aspect_ratio:
            resolve_video_settings(config["provider"], aspect_ratio, str(quality or "720p"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)[:220]) from exc

    try:
        result = await generate_video(
            provider=config["provider"],
            api_key=config["apiKey"],
            model=config["model"],
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            fps=fps,
            duration=duration,
            quality=quality,
            prompt_extend=prompt_extend,
            references=references,
            reference_videos=reference_videos,
            reference_audios=reference_audios,
            base_url=config.get("baseUrl", ""),
        )
    except Exception as exc:
        raise HTTPException(502, "AI 视频生成失败：" + str(exc)[:220]) from exc
    record_usage(user_id, config, "video", started_at, quantity=duration)

    source = "video-to-video" if reference_videos else ("image-to-video" if references else "text-to-video")
    record = persist_video(
        user_id,
        config,
        result.data,
        prompt=prompt,
        source=source,
        options={"quality": quality, "aspectRatio": aspect_ratio, "duration": duration, "fps": fps},
    )
    video = {
        "url": record["url"],
        "model": config["model"],
        "source": source,
    }
    if fps is not None:
        video["fps"] = fps
    if quality is not None:
        video["quality"] = quality
    return {"video": video, "history": record}
