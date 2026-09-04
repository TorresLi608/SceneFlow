from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select

from app.api.deps import current_user_id
from app.core.database import db
from app.llms.registry import models
from app.models import Episode, Scene
from app.schemas.requests import CompilePromptRequest, OptimizePromptRequest
from app.services.config_service import active_model_config, project_model_config
from app.services.project_service import owned_project
from app.services.prompt_compiler import compile_prompt
from app.services.prompt_prefix_service import combined_prompt, combined_references, tone_prefix_item
from app.services.prompt_service import PRESETS
from app.services.reference_service import resolve_generation_references
from app.services.usage_service import record_usage, require_model_balance


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prompts", tags=["prompts"])

SYSTEM_PROMPTS = {
    "image": (
        "你是专业的 AI 图片提示词编辑。保留用户原意，补全主体、环境、构图、镜头、光线、色彩、"
        "风格与材质等可视细节，使提示词清晰且可直接用于图片生成。不要编造与原意冲突的内容。"
        "只输出最终提示词，不要标题、解释、引号或 Markdown。"
    ),
    "video": (
        "你是专业的 AI 视频提示词编辑。保留用户原意，补全主体动作、场景变化、镜头运动、节奏、"
        "光线与连续性，使提示词适合视频生成并符合给定时长和画面参数。"
        "只输出最终提示词，不要标题、解释、引号或 Markdown。"
    ),
    "voice": (
        "你是专业的 AI 声音与音色设计提示词编辑。保留用户原意，从性别、年龄段、音质音色（如清亮、沙哑、磁性、温润、浑厚等）、"
        "语调语速、情绪情感色彩、说话风格及适用场景等维度补充专业的声音听感特征描述，使提示词清晰精准且适合用于音色定制模型。"
        "只输出最终音色描述提示词，不要标题、解释、引号或 Markdown。"
    ),
    "audio": (
        "你是专业的配音文稿编辑。保留原意、事实、语言和人称，改善断句、标点、口语自然度与朗读节奏，"
        "并适配给定音色和语气；不要扩写新信息。只输出最终朗读文本，不要标题、解释、引号或 Markdown。"
    ),
    # The three below draw *setting sheets*, not frames, so unlike `image` they must keep the
    # on-image labelling the reference depends on rather than optimising it away.
    "character": (
        "你是动画角色设定师。把用户给的角色设定图提示词补全得更专业：明确三视图或多视图的排布、"
        "服装材质、体型比例、发型五官特征、配色、光照与背景处理。"
        "务必保留「画面中标注角色名称、角色简介与角色设定」这一要求，"
        "并说明文字排布在信息栏内、不遮挡角色。不要编造与原意冲突的设定。"
        "只输出最终提示词，不要标题、解释、引号或 Markdown。"
    ),
    "prop": (
        "你是美术道具设计师。把用户给的道具设定图提示词补全得更专业：明确物体的形制、材质、工艺、"
        "磨损痕迹、尺度参照、打光与背景处理。"
        "务必保留「画面中标注道具名称、归属角色、道具简介与道具设定」这一要求，"
        "并说明文字排布在信息栏内、不遮挡道具。不要编造与原意冲突的设定。"
        "只输出最终提示词，不要标题、解释、引号或 Markdown。"
    ),
    "cover": (
        "你是短剧海报设计师。把用户描述的封面画面补全成专业的竖屏海报提示词：明确单一主体、"
        "构图与视线、情绪张力、打光方案、色调与景深。海报画面本身不要出现文字或水印。"
        "不要编造与原意冲突的剧情。只输出最终提示词，不要标题、解释、引号或 Markdown。"
    ),
}

OUTPUT_LANGUAGES = {
    "auto": "跟随原始输入语言",
    "zh": "中文",
    "en": "英文",
}


@router.post("/compile")
def preview_compiled_prompt(body: CompilePromptRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """What the editor's `@素材` labels turn into for the project's current model.

    `sceneId` matters for video: the render prepends the shot's storyboard frame when the
    model takes images, so `图1` there is the frame and the first selection is `图2`. The
    preview has to count the same way or it teaches the user the wrong number.
    """
    with db() as session:
        project = owned_project(session, body.project_id, user_id)
        config = project_model_config(session, user_id, project, body.kind, "最终提示词预览")
        prefixes = [item.model_dump() for item in body.prefixes]
        # Prefix-first, deduplicated — the same order the render resolves them in, so the
        # `图N` the user reads here is the `图N` the provider is asked for.
        resolved = resolve_generation_references(
            session,
            body.project_id,
            combined_references(prefixes, [(item.kind, item.id) for item in body.references]),
        )
        image_offset = 0
        speaker_name = ""
        if body.kind == "video" and body.scene_id:
            scene = session.exec(
                select(Scene).where(Scene.id == body.scene_id, Scene.project_id == body.project_id)
            ).first()
            capabilities = config.get("videoCapabilities") or {}
            has_explicit_references = bool(scene and scene.video_references_explicit)
            has_explicit_storyboard = any(item.kind == "sceneImage" and item.id == body.scene_id for item in body.references)
            image_offset = int(bool(scene and scene.image_path and capabilities.get("referenceImages") and not has_explicit_references and not has_explicit_storyboard))
            speaker_name = str((scene and scene.speaker_character_id) or "")
            if not speaker_name and body.dialogue:
                match = re.match(r"^\s*([^：:]{1,40})\s*[：:]", body.dialogue)
                if match:
                    from app.services.breakdown_service import resolve_speaker
                    speaker_name = resolve_speaker(session, body.project_id, match.group(1)) or ""
            if speaker_name:
                from app.services.character_service import cast_for_episode
                episode = session.get(Episode, scene.episode_id) if scene else None
                speaker = cast_for_episode(session, body.project_id, episode.episode_number if episode else 0).get(speaker_name)
                speaker_name = speaker.name if speaker else speaker_name
    return compile_prompt(
        combined_prompt(prefixes, body.prompt),
        provider=config["provider"],
        model=config["model"],
        references=resolved["items"],
        dialogue=body.dialogue,
        image_offset=image_offset,
        speaker_name=speaker_name,
    )


@router.get("/presets")
def list_prompt_presets(kind: str = "character") -> dict[str, Any]:
    """Starting points for a prompt field, so a blank box is never the only option.

    Public within the app and free of model calls — these are static templates, and gating
    them behind a balance check would make an empty form unusable for a user out of credit.
    """
    presets = PRESETS.get(kind.strip().lower())
    if presets is None:
        raise HTTPException(400, f"unknown preset kind: {kind[:40]}")
    return {"kind": kind.strip().lower(), "presets": [dict(preset) for preset in presets]}


@router.get("/prefix-presets")
def list_prompt_prefix_presets(
    # Aliased so the query string is camelCase like every request body, rather than this one
    # endpoint being the exception a client has to remember.
    project_id: str = Query(alias="projectId", max_length=64),
    scene_id: str = Query(alias="sceneId", max_length=64),
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Ready-to-insert preambles for one shot, for the editor's quick-fill bar.

    Served rather than templated in the browser because the wording is an instruction to a
    model, and the one the tone sheet writes on a successful anchor has to stay identical to
    the one this hands back — a user who deleted the automatic item is asking for that item,
    not for a copy of it that drifted.

    Only the tone preset exists today, and only once the episode has an anchor to point at:
    the text is entirely about locating this shot's cell in the grid, which is meaningless
    without a grid.
    """
    with db() as session:
        owned_project(session, project_id, user_id)
        scene = session.exec(
            select(Scene).where(
                Scene.id == scene_id, Scene.project_id == project_id, Scene.deleted_at.is_(None)
            )
        ).first()
        if not scene:
            raise HTTPException(404, "scene not found")
        episode = session.get(Episode, scene.episode_id) if scene.episode_id else None
        if not episode or not episode.tone_image_path:
            return {"presets": []}
        scenes = session.exec(
            select(Scene)
            .where(Scene.episode_id == episode.id, Scene.deleted_at.is_(None))
            .order_by(Scene.order_num)
        ).all()
        order = scene.order_num or 1
        # The label has to be the one `resolve_generation_references` gives a `tone`
        # reference, or the `@` in the preset never compiles to a numbered `图N`.
        item = tone_prefix_item(episode.id, str(episode.title or ""), order, len(scenes))
    return {"presets": [item]}


@router.post("/optimize")
async def optimize_prompt(
    body: OptimizePromptRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    with db() as session:
        config = active_model_config(session, user_id, "script", "提示词优化")
        require_model_balance(session, user_id, config)

    context = body.context.model_dump(by_alias=True, exclude_none=True)
    output_language = context.pop("outputLanguage", "auto")
    user_prompt = f"待优化内容：\n{body.prompt}"
    user_prompt += f"\n\n输出语言：{OUTPUT_LANGUAGES.get(output_language, '跟随原始输入语言')}"
    if context:
        user_prompt += "\n\n生成参数（仅作适配上下文）：\n" + json.dumps(context, ensure_ascii=False)

    started_at = time.monotonic()
    try:
        result = await models.complete_text(
            config["provider"],
            config["apiKey"],
            config["model"],
            SYSTEM_PROMPTS[body.kind],
            user_prompt,
            config.get("baseUrl", ""),
        )
    except Exception as exc:
        logger.warning("prompt optimize failed user=%s kind=%s: %s", user_id, body.kind, exc)
        raise HTTPException(502, f"failed to optimize prompt: {str(exc)[:220]}") from exc

    record_usage(user_id, config, f"{body.kind}_prompt_optimize", started_at, result.usage)
    return {"prompt": result.text[:10_000]}
