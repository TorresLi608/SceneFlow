from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.api.deps import current_user_id
from app.core.database import db
from app.models import UserVoice
from app.services.artifact_service import save_binary_artifact
from app.services.config_service import QWEN_VD_MODEL, active_model_config, official_model_config, user_model_config
from app.services.tts_service import synthesize
from app.services.usage_service import record_usage, require_model_balance


router = APIRouter(prefix="/api/audio", tags=["audio"])

FORMAT_OPTIONS = {"wav_24000": (".wav", "audio/wav")}


@router.post("/generate")
async def generate_audio(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    text = str(payload.get("text") or "").strip()
    voice = str(payload.get("voice") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    if not voice:
        raise HTTPException(400, "voice is required")
    if len(text) > 10_000:
        raise HTTPException(400, "text must be 10000 characters or fewer")

    config_id = payload.get("configId")
    official_config_id = payload.get("officialConfigId")
    with db() as session:
        if official_config_id:
            config = official_model_config(session, int(official_config_id), "audio", "音色生成")
        elif config_id:
            config = user_model_config(session, user_id, int(config_id), "audio", "音色生成")
        else:
            config = active_model_config(session, user_id, "audio", "音色生成")
        require_model_balance(session, user_id, config)
        saved_voice = session.exec(
            select(UserVoice).where(
                UserVoice.id == voice,
                UserVoice.user_id == user_id,
                UserVoice.is_saved.is_(True),
                UserVoice.deleted_at.is_(None),
            )
        ).first()
        if saved_voice:
            provider_voice = saved_voice.voice_id
        elif voice.startswith("user-voice_"):
            raise HTTPException(404, "voice not found")
        else:
            provider_voice = voice

    if config["provider"] != "qwen":
        raise HTTPException(400, "语音生成目前只支持千问模型")

    model = QWEN_VD_MODEL
    format_key = "wav_24000"
    suffix, media_type = FORMAT_OPTIONS.get(format_key, ("", ""))
    if not suffix:
        raise HTTPException(400, "unsupported audio format")

    started_at = time.monotonic()
    target = Path("/tmp") / f"sceneflow-audio-{time.time_ns()}{suffix}"
    try:
        output, duration = await synthesize(
            text,
            {**config, "model": model, "voice": provider_voice},
            target,
            None,
        )
        data = output.read_bytes()
    except Exception as exc:
        raise HTTPException(502, "AI 音色生成失败：" + str(exc)[:220]) from exc
    finally:
        target.unlink(missing_ok=True)
        if "output" in locals() and output != target:
            output.unlink(missing_ok=True)

    record_usage(user_id, config, "audio_generation", started_at, quantity=duration)
    return {
        "audio": {
            "url": save_binary_artifact("audio", f"generated-audio{suffix}", data, media_type),
            "model": model,
            "voice": voice,
            "duration": duration,
            "format": format_key,
        }
    }
