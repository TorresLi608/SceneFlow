from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user_id
from app.core.database import db
from app.services.artifact_service import save_binary_artifact
from app.services.config_service import active_model_config, official_model_config, user_model_config
from app.services.tts_service import synthesize
from app.services.usage_service import record_usage, require_model_balance


router = APIRouter(prefix="/api/audio", tags=["audio"])

FORMAT_OPTIONS = {
    "mp3_24000": ("MP3_24000HZ_MONO_256KBPS", ".mp3", "audio/mpeg"),
    "wav_24000": ("WAV_24000HZ_MONO_16BIT", ".wav", "audio/wav"),
}


def _number(payload: dict[str, Any], name: str, minimum: float, maximum: float, integer: bool = False, default: int | float | None = None) -> int | float:
    value = payload.get(name)
    if value is None:
        return default if default is not None else (0 if integer else 1.0)
    try:
        parsed = int(value) if integer else float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"{name} is invalid") from exc
    if isinstance(value, bool) or not minimum <= parsed <= maximum:
        raise HTTPException(400, f"{name} must be between {minimum} and {maximum}")
    return parsed


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

    if config["provider"] != "qwen":
        raise HTTPException(400, "音色生成目前只支持千问音频模型")

    model = str(config["model"] or "").split(":", 1)[0].strip()
    if not model:
        raise HTTPException(400, "selected audio model is invalid")
    format_key = str(payload.get("format") or "mp3_24000")
    format_name, suffix, media_type = FORMAT_OPTIONS.get(format_key, ("", "", ""))
    if not format_name:
        raise HTTPException(400, "unsupported audio format")

    language_hints = payload.get("languageHints") or []
    if not isinstance(language_hints, list) or any(item not in {"zh", "en"} for item in language_hints):
        raise HTTPException(400, "languageHints must contain only zh or en")
    instruction = str(payload.get("instruction") or "").strip()
    if len(instruction) > 128:
        raise HTTPException(400, "instruction must be 128 characters or fewer")
    options = {
        "format": format_name,
        "volume": _number(payload, "volume", 0, 100, integer=True, default=50),
        "speech_rate": _number(payload, "speechRate", 0.5, 2),
        "pitch_rate": _number(payload, "pitchRate", 0.5, 2),
        "seed": _number(payload, "seed", 0, 65535, integer=True),
        "instruction": instruction or None,
        "language_hints": language_hints or None,
    }
    started_at = time.monotonic()
    target = Path("/tmp") / f"sceneflow-audio-{time.time_ns()}{suffix}"
    try:
        output, duration = await synthesize(
            text,
            {**config, "model": f"{model}:{voice}"},
            target,
            options,
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
