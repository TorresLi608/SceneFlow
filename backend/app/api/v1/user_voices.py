from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.api.deps import current_user_id
from app.core.database import db
from app.models import ModelConfig, UserVoice
from app.schemas.serializers import user_voice_json
from app.services.artifact_service import store_artifact
from app.services.config_service import QWEN_VD_MODEL, active_model_config, official_model_config, user_model_config
from app.services.qwen_voice_service import create_voice
from app.services.usage_service import record_usage, require_model_balance
from app.utils.common import new_id, now


router = APIRouter(prefix="/api/voices", tags=["user-voices"])


def _config(session, user_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    if payload.get("officialConfigId"):
        return official_model_config(session, int(payload["officialConfigId"]), "audio", "语音管理")
    if payload.get("configId"):
        return user_model_config(session, user_id, int(payload["configId"]), "audio", "语音管理")
    return active_model_config(session, user_id, "audio", "语音管理")


@router.get("")
def list_user_voices(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        voices = session.exec(select(UserVoice).where(UserVoice.user_id == user_id, UserVoice.is_saved.is_(True), UserVoice.deleted_at.is_(None)).order_by(UserVoice.created_at.desc())).all()
    return {"voices": [user_voice_json(voice) for voice in voices]}


@router.post("/design")
async def design_voice(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    prompt = str(payload.get("voicePrompt") or "").strip()
    preview_text = str(payload.get("previewText") or "").strip()
    name = str(payload.get("name") or "custom_voice").strip()
    if not prompt:
        raise HTTPException(400, "voicePrompt is required")
    if not preview_text:
        raise HTTPException(400, "previewText is required")
    if len(prompt) > 1000 or len(preview_text) > 1000 or len(name) > 80:
        raise HTTPException(400, "voice design fields are too long")
    with db() as session:
        config = _config(session, user_id, payload)
        require_model_balance(session, user_id, config)
    started_at = time.monotonic()
    try:
        voice_id, audio = create_voice(config, prompt, preview_text, name)
        if not audio:
            from app.services.tts_service import qwen_vd_tts
            preview_path = Path("/tmp") / f"sceneflow-voice-preview-{time.time_ns()}.wav"
            try:
                await qwen_vd_tts(preview_text, voice_id, {**config, "model": QWEN_VD_MODEL}, preview_path)
                audio = preview_path.read_bytes()
            finally:
                preview_path.unlink(missing_ok=True)
    except Exception as exc:
        raise HTTPException(502, f"音色设计失败：{str(exc)[:220]}") from exc
    stored = None
    if audio:
        stored = store_artifact("voices", str(user_id), f"{voice_id}.wav", audio)
    with db() as session:
        voice = UserVoice(
            id=new_id("user-voice"),
            created_at=now(),
            updated_at=now(),
            user_id=user_id,
            voice_id=voice_id,
            target_model=QWEN_VD_MODEL,
            name=name,
            voice_prompt=prompt,
            preview_text=preview_text,
            preview_audio_path=stored,
            is_saved=False,
        )
        session.add(voice)
        session.flush()
        data = user_voice_json(voice)
    record_usage(user_id, config, "voice_design", started_at, quantity=1)
    return {"voice": data}


@router.post("/{voice_id}/save")
def save_user_voice(voice_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        voice = session.exec(select(UserVoice).where(UserVoice.id == voice_id, UserVoice.user_id == user_id, UserVoice.deleted_at.is_(None))).first()
        if not voice:
            raise HTTPException(404, "voice not found")
        voice.is_saved = True
        voice.updated_at = now()
        session.add(voice)
        session.flush()
        return {"voice": user_voice_json(voice)}


@router.delete("/{voice_id}", status_code=204)
def delete_user_voice(voice_id: str, user_id: int = Depends(current_user_id)) -> None:
    with db() as session:
        voice = session.exec(select(UserVoice).where(UserVoice.id == voice_id, UserVoice.user_id == user_id, UserVoice.deleted_at.is_(None))).first()
        if not voice:
            raise HTTPException(404, "voice not found")
        voice.deleted_at = now()
        voice.updated_at = now()
        session.add(voice)
