from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from sqlalchemy import update

from app.core.config import PRIVATE_GENERATED_DIR
from app.core.database import db
from app.core.realtime import broadcast
from app.llms.registry import models
from app.models import Episode, Project, Scene
from app.services.artifact_service import (
    artifact_absolute_path,
    artifact_relative_path,
    media_type_for,
    signed_url_for_stored,
    store_artifact,
)
from app.services.usage_service import record_usage, require_model_balance
from app.services.tts_service import synthesize
from app.services.video_service import generate_video
from app.utils.common import now


logger = logging.getLogger(__name__)

MAX_CONCURRENT_SCENES = 3
MAX_CONCURRENT_VIDEO_SCENES = 2
ERROR_DETAIL_CHARS = 220
# Providers cap how many reference images one request may carry, and a crowd scene would
# blow past it. The cast is ordered, so this keeps the characters that matter most.
MAX_REFERENCE_IMAGES = 4


def _update_scene(scene_id: str, **values: Any) -> None:
    with db() as session:
        session.execute(
            update(Scene).where(Scene.id == scene_id).values(updated_at=now(), **values),
            execution_options={"synchronize_session": False},
        )


def _update_project(project_id: str, **values: Any) -> None:
    with db() as session:
        session.execute(
            update(Project).where(Project.id == project_id).values(updated_at=now(), **values),
            execution_options={"synchronize_session": False},
        )


def _update_episode(episode_id: str, **values: Any) -> None:
    with db() as session:
        session.execute(
            update(Episode).where(Episode.id == episode_id).values(updated_at=now(), **values),
            execution_options={"synchronize_session": False},
        )


async def _scene_event(project_id: str, scene_id: str, **data: Any) -> None:
    await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene_id, "data": data})


def character_references(scene: dict[str, Any]) -> list[tuple[str, bytes, str]]:
    """Reference portraits for the cast of a shot, so a face carries across episodes.

    A portrait whose file is gone is skipped rather than failing the render: losing
    consistency is a smaller harm than losing the shot.
    """
    references: list[tuple[str, bytes, str]] = []
    for character in scene.get("characters") or []:
        stored = character.get("reference_image_path")
        if not stored:
            continue
        try:
            path = artifact_absolute_path(stored)
            data = path.read_bytes()
        except (ValueError, OSError):
            logger.info("skipping unreadable reference portrait character=%s", character.get("id"))
            continue
        references.append((path.name, data, media_type_for(path.name)))
        if len(references) == MAX_REFERENCE_IMAGES:
            break
    return references


async def _generate_scene_image(project_id: str, scene: dict[str, Any], config: dict[str, Any], user_id: int) -> bool:
    scene_id = scene["id"]
    _update_scene(scene_id, image_status="generating", error_message=None)
    await _scene_event(project_id, scene_id, imageStatus="generating", imageProgress=5, errorMsg="")
    try:
        started_at = time.monotonic()
        with db() as session:
            require_model_balance(session, user_id, config)
        if config["provider"] not in {"openai", "gemini", "qwen"}:
            raise ValueError("image generation currently only supports provider openai/gemini/qwen")
        await _scene_event(project_id, scene_id, imageStatus="generating", imageProgress=20, errorMsg="")
        references = character_references(scene)
        if references:
            # Image-to-image with the cast's portraits: the appearance prompt alone drifts
            # over a long series, the reference is what actually holds a face steady.
            image = await models.edit_image(
                config["apiKey"],
                config["model"],
                build_image_prompt(scene),
                references,
                base_url=config.get("baseUrl", ""),
                provider=config["provider"],
            )
        else:
            image = await models.generate_image(
                config["apiKey"],
                config["model"],
                build_image_prompt(scene),
                base_url=config.get("baseUrl", ""),
                provider=config["provider"],
            )
        record_usage(user_id, config, "storyboard_image", started_at, quantity=1)
        image_path = persist_scene_image(project_id, scene_id, image.data, image.format)
    except Exception as exc:
        detail = str(exc)[:ERROR_DETAIL_CHARS]
        logger.warning("scene image generation failed project=%s scene=%s: %s", project_id, scene_id, detail)
        # Persisted, not just broadcast: a reload used to lose the reason the shot is blank.
        _update_scene(scene_id, image_status="error", error_message=f"AI 图片生成失败：{detail}")
        await _scene_event(project_id, scene_id, imageStatus="error", imageProgress=0, errorMsg=f"AI 图片生成失败：{detail}")
        return False

    _update_scene(scene_id, image_status="success", image_path=image_path, error_message=None)
    await _scene_event(
        project_id,
        scene_id,
        imageStatus="success",
        imageProgress=100,
        imageUrl=signed_url_for_stored(image_path, f"scene-{scene.get('order_num') or 0}"),
        errorMsg="",
    )
    return True


def voice_config(audio_config: dict[str, Any], speaker: dict[str, Any] | None) -> dict[str, Any]:
    """Swap in a character's voice, but only one the account can actually synthesize.

    A character card stores a provider and a model, never credentials. Honouring a model
    from a provider the project is not configured for would fail on a key we do not have,
    so the default voice reads the line instead of the shot erroring out.
    """
    if not speaker:
        return audio_config
    model = str(speaker.get("voice_model") or "").strip()
    provider = str(speaker.get("voice_provider") or "").strip().lower()
    if not model or (provider and provider != audio_config["provider"]):
        return audio_config
    return {**audio_config, "model": model}


def spoken_line(scene: dict[str, Any], audio_config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """What a shot says, and in whose voice.

    A shot carries one audio track, so dialogue wins when there is any: it belongs to a
    character and should sound like them. With no dialogue the narrator reads the narration
    in the project's default voice.
    """
    dialogue = str(scene.get("dialogue") or "").strip()
    if dialogue:
        return dialogue, voice_config(audio_config, scene.get("speaker"))
    return str(scene.get("narration") or "").strip(), audio_config


async def _generate_scene_audio(project_id: str, scene: dict[str, Any], audio_config: dict[str, Any], user_id: int) -> bool:
    scene_id = scene["id"]
    await _scene_event(project_id, scene_id, audioStatus="generating", audioProgress=20, errorMsg="")
    try:
        line, config = spoken_line(scene, audio_config)
        extension = "mp3" if config["provider"] == "edge" else "wav"
        target = PRIVATE_GENERATED_DIR / "projects" / project_id / f"{scene_id}.{extension}"
        started_at = time.monotonic()
        target, duration = await synthesize(line, config, target)
        target.chmod(0o600)
        if config["provider"] not in {"edge", "system"}:
            record_usage(user_id, config, "scene_tts", started_at, quantity=duration)
        audio_path = artifact_relative_path(target)
    except Exception as exc:
        detail = str(exc)[:ERROR_DETAIL_CHARS]
        logger.warning("scene audio generation failed project=%s scene=%s: %s", project_id, scene_id, detail)
        _update_scene(scene_id, audio_status="error", error_message=f"AI 配音生成失败：{detail}")
        await _scene_event(project_id, scene_id, audioStatus="error", audioProgress=0, errorMsg=f"AI 配音生成失败：{detail}")
        return False

    _update_scene(scene_id, audio_status="success", audio_path=audio_path, audio_duration=duration)
    await _scene_event(
        project_id,
        scene_id,
        audioStatus="success",
        audioProgress=100,
        audioUrl=signed_url_for_stored(audio_path, f"scene-{scene.get('order_num') or 0}"),
        audioDuration=duration,
        errorMsg="",
    )
    return True


def terminal_status(outcomes: list[bool]) -> str:
    """Derive the project status from what actually landed.

    A run where every shot failed used to still report `done`, which told the user the
    opposite of the truth.
    """
    if not outcomes or all(outcomes):
        return "done"
    return "partial" if any(outcomes) else "failed"


async def run_generation(
    project_id: str,
    scenes: list[dict[str, Any]],
    config: dict[str, Any],
    audio_config: dict[str, Any],
    user_id: int,
    episode_id: str | None = None,
) -> None:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCENES)

    async def one(scene: dict[str, Any]) -> list[bool]:
        async with semaphore:
            image_ok = await _generate_scene_image(project_id, scene, config, user_id)
            audio_ok = await _generate_scene_audio(project_id, scene, audio_config, user_id)
            return [image_ok, audio_ok]

    results = await asyncio.gather(*(one(scene) for scene in scenes))
    status = terminal_status([outcome for scene_result in results for outcome in scene_result])
    logger.info(
        "generation finished project=%s episode=%s scenes=%d status=%s", project_id, episode_id, len(scenes), status
    )
    # Both levels carry the outcome: the project because it holds the busy lock, the
    # episode because that is what the user was actually rendering.
    _update_project(project_id, status=status)
    if episode_id:
        _update_episode(episode_id, status=status)
    await broadcast(
        project_id,
        {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": status, "episodeId": episode_id}},
    )


def build_image_prompt(scene: dict[str, Any]) -> str:
    narration = str(scene.get("narration") or "").strip()
    visual = str(scene.get("visual_prompt") or narration).strip()
    prompt = f"Create a cinematic anime storyboard frame for a short video. Keep one clear subject, strong composition, dramatic lighting, high detail, no text, no watermark. Scene narration: {narration}. Visual direction: {visual}."
    framing = ", ".join(
        part for part in (str(scene.get("shot_type") or "").strip(), str(scene.get("camera_move") or "").strip()) if part
    )
    if framing:
        prompt += f" Framing: {framing}."
    # Named, not just pictured: the model holds a described character steadier than an
    # unnamed one, and this is the only consistency lever on providers without references.
    cast = "; ".join(
        f"{character['name']}: {character['appearance_prompt']}"
        for character in scene.get("characters") or []
        if character.get("appearance_prompt")
    )
    if cast:
        prompt += f" Keep these characters consistent — {cast}."
    return prompt


def persist_scene_image(project_id: str, scene_id: str, data: bytes, ext: str) -> str:
    ext = (ext or "png").strip().lower()
    ext = "jpg" if ext in {"jpg", "jpeg"} else ext if ext in {"png", "webp"} else "png"
    return store_artifact("projects", project_id, f"{scene_id}.{ext}", data)


def build_portrait_prompt(name: str, appearance_prompt: str, description: str = "") -> str:
    """The reference portrait a character's later shots are matched against.

    Deliberately plain — front-facing, neutral light, no scene — because this image is used
    as an image-to-image reference, and any drama baked into it would leak into every shot
    the character appears in.
    """
    traits = appearance_prompt.strip() or description.strip()
    return (
        "Create a clean character reference portrait for an anime short drama. "
        "Single character, front-facing, head and shoulders, neutral expression, plain "
        "neutral background, even lighting, no text, no watermark, no props. "
        f"Character name: {name.strip()}. Appearance: {traits}."
    )


def persist_character_portrait(project_id: str, character_id: str, data: bytes, ext: str) -> str:
    ext = (ext or "png").strip().lower()
    ext = "jpg" if ext in {"jpg", "jpeg"} else ext if ext in {"png", "webp"} else "png"
    return store_artifact("characters", project_id, f"{character_id}.{ext}", data)


def _stored_media(stored: str) -> dict[str, str]:
    path = artifact_absolute_path(stored)
    data = path.read_bytes()
    return {
        "name": path.name,
        "data": f"data:{media_type_for(path.name)};base64,{base64.b64encode(data).decode('ascii')}",
    }


async def _generate_scene_video(
    project_id: str,
    scene: dict[str, Any],
    config: dict[str, Any],
    user_id: int,
    options: dict[str, Any],
) -> bool:
    scene_id = scene["id"]
    _update_scene(scene_id, video_status="generating", error_message=None)
    await _scene_event(project_id, scene_id, videoStatus="generating", videoProgress=5, errorMsg="")
    try:
        capabilities = config["videoCapabilities"]
        references = []
        if capabilities["maxReferenceImages"] and scene.get("image_path"):
            references.append(_stored_media(scene["image_path"]))
        if capabilities["referenceImagesRequired"] and not references:
            raise ValueError("该分镜缺少模型必需的参考图")
        for _, data, mime_type in character_references(scene):
            if len(references) >= capabilities["maxReferenceImages"]:
                break
            references.append({"name": "character.png", "data": f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"})
        driving_audio = _stored_media(scene["audio_path"]) if capabilities["drivingAudio"] and scene.get("audio_path") else None
        prompt = str(scene.get("visual_prompt") or scene.get("narration") or "").strip()
        if not prompt:
            raise ValueError("该分镜缺少画面提示词")
        started_at = time.monotonic()
        with db() as session:
            require_model_balance(session, user_id, config)
        await _scene_event(project_id, scene_id, videoStatus="generating", videoProgress=20, errorMsg="")
        result = await generate_video(
            provider=config["provider"],
            api_key=config["apiKey"],
            model=config["model"],
            prompt=prompt,
            quality=options["quality"],
            resolution=options["resolution"],
            fps=options["fps"],
            duration=options["duration"],
            prompt_extend=options["promptExtend"],
            references=references,
            driving_audio=driving_audio,
            base_url=config.get("baseUrl", ""),
        )
        record_usage(user_id, config, "scene_video", started_at, quantity=options["duration"])
        video_path = store_artifact("projects", project_id, f"{scene_id}.{result.format}", result.data)
    except Exception as exc:
        detail = str(exc)[:ERROR_DETAIL_CHARS]
        logger.warning("scene video generation failed project=%s scene=%s: %s", project_id, scene_id, detail)
        _update_scene(scene_id, video_status="error", error_message=f"AI 视频生成失败：{detail}")
        await _scene_event(project_id, scene_id, videoStatus="error", videoProgress=0, errorMsg=f"AI 视频生成失败：{detail}")
        return False

    _update_scene(scene_id, video_status="success", video_path=video_path, error_message=None)
    await _scene_event(
        project_id,
        scene_id,
        videoStatus="success",
        videoProgress=100,
        videoUrl=signed_url_for_stored(video_path, f"scene-{scene.get('order_num') or 0}"),
        errorMsg="",
    )
    return True


async def run_video_generation(
    project_id: str,
    scenes: list[dict[str, Any]],
    config: dict[str, Any],
    user_id: int,
    episode_id: str,
    options: dict[str, Any],
) -> None:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_VIDEO_SCENES)
    completed = 0
    completed_lock = asyncio.Lock()

    async def run(scene: dict[str, Any]) -> bool:
        nonlocal completed
        async with semaphore:
            succeeded = await _generate_scene_video(project_id, scene, config, user_id, options)
        async with completed_lock:
            completed += 1
            progress = round(completed / len(scenes) * 100)
            _update_project(project_id, video_progress=progress)
            _update_episode(episode_id, video_progress=progress)
            await broadcast(project_id, {"type": "VIDEO_UPDATE", "projectId": project_id, "data": {"videoStatus": "generating", "videoProgress": progress, "videoModel": config["model"]}})
        return succeeded

    results = await asyncio.gather(*(run(scene) for scene in scenes))
    successes = sum(results)
    status = "done" if successes == len(scenes) else "partial" if successes else "failed"
    video_status = "success" if status == "done" else "error"
    detail = "" if status == "done" else f"{len(scenes) - successes} 个分镜视频生成失败"
    _update_project(project_id, status=status, video_status=video_status, video_progress=100, video_url=None)
    _update_episode(episode_id, status=status, video_status=video_status, video_progress=100, error_message=detail or None)
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": status, "videoStatus": video_status, "videoProgress": 100, "videoModel": config["model"]}})
