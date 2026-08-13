from __future__ import annotations

from typing import Any
import time

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import db
from app.api.deps import current_user_id
from app.services.artifact_service import save_binary_artifact
from app.services.config_service import active_model_config, official_model_config, user_model_config
from app.services.usage_service import record_usage, require_model_balance
from app.services.video_service import generate_video, resolve_qwen_video_quality, resolve_video_options, resolve_video_settings, validate_qwen_video_input, validate_video_inputs


router = APIRouter(prefix="/api/videos", tags=["videos"])


def persist_video(data: bytes) -> str:
    return save_binary_artifact("videos", "generated-video.mp4", data, "video/mp4")


@router.post("/generate")
async def generate_video_route(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt is required")

    references = payload.get("references") or ([payload["reference"]] if payload.get("reference") else [])
    reference_video = payload.get("referenceVideo")
    driving_audio = payload.get("drivingAudio")
    if not isinstance(references, list) or any(not isinstance(item, dict) for item in references):
        raise HTTPException(400, "references must be image data URLs")
    if reference_video is not None and not isinstance(reference_video, dict):
        raise HTTPException(400, "referenceVideo must be a video data URL")
    if driving_audio is not None and not isinstance(driving_audio, dict):
        raise HTTPException(400, "drivingAudio must be an audio data URL")

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
        quality, resolution, fps, duration, prompt_extend = resolve_video_options(payload, config["videoCapabilities"])
        validate_video_inputs(config["videoCapabilities"], references, reference_video, driving_audio)
        if config["provider"] == "qwen":
            if quality:
                quality = resolve_qwen_video_quality(str(quality))
            validate_qwen_video_input(config["model"], references, reference_video)
        elif resolution:
            resolve_video_settings(config["provider"], resolution)
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
            quality=quality,
            prompt_extend=prompt_extend,
            references=references,
            reference_video=reference_video,
            driving_audio=driving_audio,
            base_url=config.get("baseUrl", ""),
        )
    except Exception as exc:
        raise HTTPException(502, "AI 视频生成失败：" + str(exc)[:220]) from exc
    record_usage(user_id, config, "video", started_at, quantity=duration)

    video = {
        "url": persist_video(result.data),
        "model": config["model"],
        "source": "video-to-video" if reference_video else ("image-to-video" if references else "text-to-video"),
    }
    if fps is not None:
        video["fps"] = fps
    if quality is not None:
        video["quality"] = quality
    return {"video": video}
