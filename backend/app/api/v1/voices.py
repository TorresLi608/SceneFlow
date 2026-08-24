"""Voice management: what each character and the narrator sound like.

The individual profiles exist so a user can audition and bind a timbre. The merged track is
what the pipeline actually consumes — every voice introducing itself in order, so a video
model given it as a reference can keep speakers apart.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.api.deps import current_user_id
from app.core.config import PRIVATE_GENERATED_DIR
from app.core.database import db
from app.core.realtime import broadcast
from app.models import UserVoice
from app.schemas.requests import (
    CreateVoiceProfileRequest,
    DesignVoiceProfileRequest,
    ImportVoiceProfileRequest,
    UpdateVoiceProfileRequest,
)
from app.schemas.serializers import project_json, voice_profile_json
from app.services.artifact_service import artifact_absolute_path, artifact_relative_path, store_artifact
from app.services.config_service import project_model_config
from app.services.media_service import concat_audio
from app.services.project_service import owned_project
from app.services.prompt_service import NARRATOR_SAMPLE_TEXT
from app.services.qwen_voice_service import create_voice
from app.services.tts_service import synthesize
from app.services.usage_service import record_usage, require_model_balance
from app.services.voice_service import (
    create_voice_profile,
    delete_voice_profile,
    owned_voice_profile,
    voice_profiles_for,
)
from app.utils.common import new_id, now


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["voices"])

BUILTIN_TTS = {"provider": "edge", "model": "zh-CN-XiaoxiaoNeural", "apiKey": "", "baseUrl": "", "source": "builtin"}


@router.get("/{project_id}/voices")
def list_voices(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        data = [voice_profile_json(profile) for profile in voice_profiles_for(session, project_id)]
    return {"voices": data}


@router.post("/{project_id}/voices", status_code=201)
async def add_voice(
    project_id: str,
    body: CreateVoiceProfileRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        profile = create_voice_profile(
            session,
            project_id,
            name=body.name,
            note=body.note,
            voice_provider=body.voice_provider,
            voice_model=body.voice_model,
            # The narrator template is the sensible default: it is the one voice every
            # series has, and the wording is editable either way.
            sample_text=body.sample_text or NARRATOR_SAMPLE_TEXT,
            order_num=body.order_num,
        )
        data = voice_profile_json(profile)
    await broadcast(project_id, {"type": "VOICE_UPDATE", "projectId": project_id, "data": data})
    return {"voice": data}


@router.post("/{project_id}/voices/design", status_code=201)
async def design_project_voice(
    project_id: str,
    body: DesignVoiceProfileRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Design a timbre from a description and bind it to this series in one step.

    The provider and model come from the project's audio configuration rather than the
    request. The old form asked the user to type them, which is how a series ended up with
    profiles naming a model no synthesiser here could actually voice.

    The designed voice is also saved to the account's library, because a timbre that took a
    paid request to produce should be reusable in the next series without paying again.
    """
    with db() as session:
        project = owned_project(session, project_id, user_id)
        config = project_model_config(session, user_id, project, "audio", "音色设计")
        require_model_balance(session, user_id, config)

    started_at = time.monotonic()
    try:
        voice_id, audio = await create_voice(config, body.voice_prompt, body.preview_text, body.name)
    except Exception as exc:
        logger.warning("voice design failed project=%s: %s", project_id, exc)
        raise HTTPException(502, f"音色设计失败：{str(exc)[:220]}") from exc
    record_usage(user_id, config, "voice_design", started_at, quantity=1)

    stored = store_artifact("voices", project_id, f"{voice_id}.wav", audio)
    stamp = now()
    with db() as session:
        owned_project(session, project_id, user_id)
        session.add(
            UserVoice(
                id=new_id("user-voice"),
                created_at=stamp,
                updated_at=stamp,
                user_id=user_id,
                voice_id=voice_id,
                target_model=str(config["model"]),
                name=body.name,
                voice_prompt=body.voice_prompt,
                preview_text=body.preview_text,
                preview_audio_path=stored,
                is_saved=True,
            )
        )
        profile = create_voice_profile(
            session,
            project_id,
            name=body.name,
            note=body.note or body.voice_prompt[:200],
            voice_provider=config["provider"],
            # The designed voice id, not the base model: this is what synthesis has to ask
            # for to get this timbre back rather than the model's default one.
            voice_model=voice_id,
            sample_text=body.sample_text or NARRATOR_SAMPLE_TEXT,
            audio_path=stored,
        )
        data = voice_profile_json(profile)
    await broadcast(project_id, {"type": "VOICE_UPDATE", "projectId": project_id, "data": data})
    return {"voice": data}


@router.post("/{project_id}/voices/import", status_code=201)
async def import_project_voice(
    project_id: str,
    body: ImportVoiceProfileRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Bind a timbre already in the account's library to this series.

    Copies the audition rather than referencing the library row: a series' voice sheet must
    keep working after the user tidies up their library, and the clip is small.
    """
    with db() as session:
        owned_project(session, project_id, user_id)
        voice = session.exec(
            select(UserVoice).where(
                UserVoice.id == body.user_voice_id,
                UserVoice.user_id == user_id,
                UserVoice.deleted_at.is_(None),
            )
        ).first()
        if not voice:
            raise HTTPException(404, "voice not found")
        source_path = voice.preview_audio_path
        name = body.name or voice.name or voice.voice_id
        note = body.note or voice.voice_prompt[:200]
        target_model = voice.voice_id

    stored = None
    if source_path:
        try:
            stored = store_artifact("voices", project_id, f"{target_model}.wav", artifact_absolute_path(source_path).read_bytes())
        except (ValueError, OSError):
            # A library entry whose audition is gone still binds; it just has to be
            # re-auditioned before it can join the merged sheet.
            logger.info("imported voice has no readable audition project=%s voice=%s", project_id, body.user_voice_id)

    with db() as session:
        owned_project(session, project_id, user_id)
        profile = create_voice_profile(
            session,
            project_id,
            name=name,
            note=note,
            voice_provider="qwen",
            voice_model=target_model,
            sample_text=body.sample_text or NARRATOR_SAMPLE_TEXT,
            audio_path=stored,
        )
        data = voice_profile_json(profile)
    await broadcast(project_id, {"type": "VOICE_UPDATE", "projectId": project_id, "data": data})
    return {"voice": data}


@router.patch("/{project_id}/voices/{voice_id}")
async def update_voice(
    project_id: str,
    voice_id: str,
    body: UpdateVoiceProfileRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    # exclude_unset, not "is not None": clearing a note is a real edit, and only an absent
    # key means "leave it alone".
    updates = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if not updates:
        raise HTTPException(400, "no fields to update")

    with db() as session:
        owned_project(session, project_id, user_id)
        profile = owned_voice_profile(session, project_id, voice_id)
        for key, value in updates.items():
            setattr(profile, key, value)
        profile.updated_at = now()
        session.add(profile)
        session.flush()
        data = voice_profile_json(profile)
    await broadcast(project_id, {"type": "VOICE_UPDATE", "projectId": project_id, "data": data})
    return {"voice": data}


@router.delete("/{project_id}/voices/{voice_id}", status_code=204)
async def remove_voice(project_id: str, voice_id: str, user_id: int = Depends(current_user_id)) -> None:
    with db() as session:
        owned_project(session, project_id, user_id)
        profile = owned_voice_profile(session, project_id, voice_id)
        delete_voice_profile(session, profile)
    await broadcast(project_id, {"type": "VOICE_DELETED", "projectId": project_id, "voiceId": voice_id})


@router.post("/{project_id}/voices/{voice_id}/preview")
async def preview_voice(project_id: str, voice_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """Synthesise the profile's sample line so the user can hear it before binding it."""
    with db() as session:
        owned_project(session, project_id, user_id)
        profile = owned_voice_profile(session, project_id, voice_id)
        line = (profile.sample_text or NARRATOR_SAMPLE_TEXT).strip()
        if not line:
            raise HTTPException(400, "sampleText is required")
        config = dict(BUILTIN_TTS)
        if profile.voice_provider in {"edge", "system"}:
            config.update(provider=profile.voice_provider, model=profile.voice_model or "")

    extension = "mp3"
    target = PRIVATE_GENERATED_DIR / "voices" / project_id / f"{voice_id}.{extension}"
    try:
        target, _ = await synthesize(line, config, target)
    except Exception as exc:
        logger.warning("voice preview failed project=%s voice=%s: %s", project_id, voice_id, exc)
        raise HTTPException(502, f"failed to synthesize voice: {str(exc)[:220]}") from exc
    target.chmod(0o600)
    stored = artifact_relative_path(target)

    with db() as session:
        owned_project(session, project_id, user_id)
        profile = owned_voice_profile(session, project_id, voice_id)
        profile.audio_path = stored
        profile.updated_at = now()
        session.add(profile)
        session.flush()
        data = voice_profile_json(profile)
    await broadcast(project_id, {"type": "VOICE_UPDATE", "projectId": project_id, "data": data})
    return {"voice": data}


@router.post("/{project_id}/voices/merge")
async def merge_voice_sheet(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """Concatenate every auditioned voice into the one track the video model listens to."""
    with db() as session:
        owned_project(session, project_id, user_id)
        stored_paths = [profile.audio_path for profile in voice_profiles_for(session, project_id) if profile.audio_path]

    clips: list[bytes] = []
    for stored in stored_paths:
        try:
            clips.append(artifact_absolute_path(stored).read_bytes())
        except (ValueError, OSError):
            # One missing clip costs the sheet a voice, not the whole merge.
            logger.info("skipping unreadable voice clip project=%s path=%s", project_id, stored)
    if not clips:
        raise HTTPException(400, "preview at least one voice before merging")

    try:
        merged = concat_audio(clips)
    except (RuntimeError, ValueError) as exc:
        logger.warning("voice merge failed project=%s: %s", project_id, exc)
        raise HTTPException(502, str(exc)[:220]) from exc
    stored = store_artifact("voices", project_id, f"{project_id}-voices.mp3", merged)

    with db() as session:
        project = owned_project(session, project_id, user_id)
        project.voice_sheet_path = stored
        project.updated_at = now()
        session.add(project)
        session.flush()
        data = project_json(project, [])
    await broadcast(
        project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": project_id,
            "data": {"voiceSheetUrl": data["voiceSheetUrl"], "updatedAt": data["updatedAt"]},
        },
    )
    return {"voiceSheetUrl": data["voiceSheetUrl"]}
