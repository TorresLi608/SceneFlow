"""What the generation-job worker actually runs.

One module rather than a handler per service because these all have the same three-beat
shape, and the shape is the interesting part:

1. **Short session** — re-resolve the target row and the model configuration.
2. **`await` the provider** — no session held, per `docs/architecture/boundaries.md`.
3. **Short session** — write the result, then broadcast the same event the synchronous
   endpoint used to broadcast, so no UI that was already listening needs to change.

The configuration is resolved *here*, not carried in `input_json`, and that is deliberate:
a resolved config holds a decrypted provider API key, and the jobs table is long-lived rows
the user can list over the API. Only ids, prompts, and options travel in the payload.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.core.config import PRIVATE_GENERATED_DIR
from app.core.database import db
from app.core.realtime import broadcast
from app.models import UserVoice
from app.schemas.serializers import voice_profile_json
from app.services.artifact_service import artifact_relative_path, store_artifact
from app.services.character_service import character_payload, owned_character, owned_state
from app.services.config_service import project_model_config
from app.services.job_worker import register
from app.services.project_service import owned_project
from app.services.prop_service import owned_prop, prop_payload
from app.services.qwen_voice_service import create_voice
from app.services.prompt_service import (
    CHARACTER_SHEET_SYSTEM,
    NARRATOR_SAMPLE_TEXT,
    PROP_SYSTEM,
)
from app.services.reference_service import draft_prompt, draw_reference, image_config, image_options, script_config
from app.services.tts_service import BUILTIN_TTS, synthesize
from app.services.usage_service import record_usage, require_model_balance
from app.services.voice_service import create_voice_profile, owned_voice_profile
from app.utils.common import new_id, now


logger = logging.getLogger(__name__)


@register("reference_image")
async def draw_reference_image(job: dict[str, Any]) -> dict[str, Any]:
    """Draw a prop image or a character state's turnaround sheet and store it.

    The prompt was resolved and reviewed when the job was queued; re-deriving it here would
    quietly ignore the edit the user made in the dialog before pressing generate.
    """
    payload = job["input"]
    project_id = job["projectId"]
    user_id = job["userId"]
    target = payload["target"]
    prompt = str(payload["prompt"])

    with db() as session:
        project = owned_project(session, project_id, user_id)
        purpose = "道具参考图" if target == "prop" else "角色三面图"
        # `image_config` re-checks the balance, which matters here and not just at enqueue: a
        # queue means time passes, and what covered this job when it was queued may be spent.
        config = image_config(session, user_id, purpose, project)
        size, quality = image_options(project)

    usage_kind = "prop_image" if target == "prop" else "character_state_image"
    data, extension = await draw_reference(config, user_id, prompt, usage_kind, size, quality)

    if target == "prop":
        prop_id = payload["propId"]
        stored = store_artifact("props", project_id, f"{prop_id}.{extension}", data)
        with db() as session:
            owned_project(session, project_id, user_id)
            prop = owned_prop(session, project_id, prop_id)
            prop.image_path = stored
            # Remember what was actually drawn, so a reload shows the prompt behind the image.
            prop.final_prompt = prompt[:4000]
            prop.updated_at = now()
            session.add(prop)
            session.flush()
            result = prop_payload(session, project_id, prop)
        await broadcast(project_id, {"type": "PROP_UPDATE", "projectId": project_id, "data": result})
        return {"prop": result}

    character_id = payload["characterId"]
    state_id = payload["stateId"]
    stored = store_artifact("characters", project_id, f"{state_id}.{extension}", data)
    with db() as session:
        owned_project(session, project_id, user_id)
        state = owned_state(session, character_id, state_id)
        state.reference_image_path = stored
        state.final_prompt = prompt[:4000]
        state.updated_at = now()
        session.add(state)
        character = owned_character(session, project_id, character_id)
        # Freeze what produced it: changing the account default later must not restyle a
        # character the rest of the series has already been matched against.
        character.image_provider = config["provider"]
        character.image_model = config["model"]
        character.image_base_url = config.get("baseUrl", "")
        character.updated_at = now()
        session.add(character)
        session.flush()
        result = character_payload(session, project_id, character_id)
    await broadcast(project_id, {"type": "CHARACTER_UPDATE", "projectId": project_id, "data": result})
    return {"character": result}


@register("prompt_draft")
async def draft_reference_prompt(job: dict[str, Any]) -> dict[str, Any]:
    """Draft an image prompt for review. Returned in the job result, never saved.

    Saving it would make the review step decorative — the user is meant to read and edit
    this before it draws anything.
    """
    payload = job["input"]
    project_id = job["projectId"]
    user_id = job["userId"]
    target = payload["target"]

    with db() as session:
        project = owned_project(session, project_id, user_id)
        purpose = "道具提示词" if target == "prop" else "角色状态提示词"
        # Re-checks the balance; see `draw_reference_image`.
        config = script_config(session, user_id, purpose, project)

    system = PROP_SYSTEM if target == "prop" else CHARACTER_SHEET_SYSTEM
    usage_kind = "prop_prompt" if target == "prop" else "character_state_prompt"
    prompt = await draft_prompt(
        config, user_id, system, str(payload["userText"]), payload.get("model") or "", usage_kind
    )
    return {"prompt": prompt, "target": target, "targetId": payload.get("targetId")}


@register("voice_design")
async def design_voice(job: dict[str, Any]) -> dict[str, Any]:
    """Design a timbre, bind it to this series, and keep it in the account's library.

    The library copy is the point of the second write: a timbre that took a paid request to
    produce should be reusable in the next series without paying again.
    """
    payload = job["input"]
    project_id = job["projectId"]
    user_id = job["userId"]

    with db() as session:
        project = owned_project(session, project_id, user_id)
        config = project_model_config(session, user_id, project, "audio", "音色设计")
        require_model_balance(session, user_id, config)

    started_at = time.monotonic()
    voice_id, audio = await create_voice(
        config, payload["voicePrompt"], payload["previewText"], payload["name"]
    )
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
                name=payload["name"],
                voice_prompt=payload["voicePrompt"],
                preview_text=payload["previewText"],
                preview_audio_path=stored,
                is_saved=True,
            )
        )
        profile = create_voice_profile(
            session,
            project_id,
            name=payload["name"],
            note=payload.get("note") or str(payload["voicePrompt"])[:200],
            voice_provider=config["provider"],
            # The designed voice id, not the base model: this is what synthesis has to ask
            # for to get this timbre back rather than the model's default one.
            voice_model=voice_id,
            sample_text=payload.get("sampleText") or NARRATOR_SAMPLE_TEXT,
            audio_path=stored,
        )
        result = voice_profile_json(profile)
    await broadcast(project_id, {"type": "VOICE_UPDATE", "projectId": project_id, "data": result})
    return {"voice": result}


@register("preview")
async def preview_voice_profile(job: dict[str, Any]) -> dict[str, Any]:
    """Synthesise a profile's sample line so the user can hear it before binding it."""
    payload = job["input"]
    project_id = job["projectId"]
    user_id = job["userId"]
    voice_id = payload["voiceId"]

    with db() as session:
        owned_project(session, project_id, user_id)
        profile = owned_voice_profile(session, project_id, voice_id)
        line = (profile.sample_text or NARRATOR_SAMPLE_TEXT).strip()
        config = dict(BUILTIN_TTS)
        if profile.voice_provider in {"edge", "system"}:
            config.update(provider=profile.voice_provider, model=profile.voice_model or "")

    target = PRIVATE_GENERATED_DIR / "voices" / project_id / f"{voice_id}.mp3"
    target, _ = await synthesize(line, config, target)
    target.chmod(0o600)
    stored = artifact_relative_path(target)

    with db() as session:
        owned_project(session, project_id, user_id)
        profile = owned_voice_profile(session, project_id, voice_id)
        profile.audio_path = stored
        profile.updated_at = now()
        session.add(profile)
        session.flush()
        result = voice_profile_json(profile)
    await broadcast(project_id, {"type": "VOICE_UPDATE", "projectId": project_id, "data": result})
    return {"voice": result}
