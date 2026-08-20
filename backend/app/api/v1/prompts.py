from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user_id
from app.core.database import db
from app.llms.registry import models
from app.schemas.requests import OptimizePromptRequest
from app.services.config_service import active_model_config
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
}

OUTPUT_LANGUAGES = {
    "auto": "跟随原始输入语言",
    "zh": "中文",
    "en": "英文",
}


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
    if body.kind in {"image", "video"}:
        user_prompt += f"\n\n输出语言：{OUTPUT_LANGUAGES[output_language]}"
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
