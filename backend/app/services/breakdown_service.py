"""Splitting a script into shots that a renderer and a video model can both act on.

The old parse produced a narration line and a picture prompt per shot. That is a comic
storyboard: it says what is in the frame and nothing about how the camera gets there, how
one shot reaches the next, or how long any of it runs — so every clip generated from it was
a guess. This module produces the wider shape, and gives the model the series bible to work
against so a shot says "参照《林小满》三面图" instead of re-inventing a face the renderer
already has a reference for.

Three cases the assembled context has to keep apart, because they need different behaviour:

- a selected character **with** a drawn sheet — name it, and let the reference carry the look;
- a selected character with **only written setting** — reason from the text;
- anyone the bible has never heard of (walk-ons, 甲乙丙丁) — invent from the script.

Selecting nothing is a fourth, deliberate case: decide everything from the script alone.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.models import Character, CharacterState, Episode, Prop, VoiceProfile
from app.services.character_service import states_for
from app.services.prompt_service import BREAKDOWN_SYSTEM, breakdown_reference_block


def _selected(rows: list[Any], ids: list[str]) -> list[Any]:
    """The rows the user ticked, in the bible's own order rather than click order."""
    wanted = {value.strip() for value in ids if value.strip()}
    return [row for row in rows if row.id in wanted]


def character_context(
    session: Session,
    project_id: str,
    character_ids: list[str],
) -> list[dict[str, Any]]:
    """Selected characters, flattened with whether any of their states has been drawn."""
    if not character_ids:
        return []
    characters = _selected(
        list(
            session.exec(
                select(Character)
                .where(Character.project_id == project_id, Character.deleted_at.is_(None))
                .order_by(Character.order_num.asc(), Character.name.asc())
            ).all()
        ),
        character_ids,
    )
    states = states_for(session, [character.id for character in characters])
    context: list[dict[str, Any]] = []
    for character in characters:
        drawn = [state for state in states.get(character.id, []) if state.reference_image_path]
        context.append(
            {
                "name": character.name,
                "description": character.description or "",
                "appearance": character.appearance_prompt or "",
                # The card's own legacy portrait counts: a series from before states existed
                # still has a usable reference, and calling it "no image" would make the
                # breakdown re-describe a face the renderer is about to pin anyway.
                "hasImage": bool(drawn) or bool(character.reference_image_path),
                "states": [state.name for state in drawn],
            }
        )
    return context


def prop_context(session: Session, project_id: str, prop_ids: list[str]) -> list[dict[str, Any]]:
    if not prop_ids:
        return []
    props = _selected(
        list(
            session.exec(
                select(Prop)
                .where(Prop.project_id == project_id, Prop.deleted_at.is_(None))
                .order_by(Prop.order_num.asc(), Prop.name.asc())
            ).all()
        ),
        prop_ids,
    )
    owners = {
        character.id: character.name
        for character in session.exec(
            select(Character).where(Character.project_id == project_id, Character.deleted_at.is_(None))
        ).all()
    }
    return [
        {
            "name": prop.name,
            "description": prop.description or "",
            "owner": owners.get(prop.owner_character_id or "", ""),
            "hasImage": bool(prop.image_path),
        }
        for prop in props
    ]


def voice_context(session: Session, project_id: str, voice_ids: list[str]) -> list[str]:
    if not voice_ids:
        return []
    profiles = _selected(
        list(
            session.exec(
                select(VoiceProfile)
                .where(VoiceProfile.project_id == project_id, VoiceProfile.deleted_at.is_(None))
                .order_by(VoiceProfile.order_num.asc(), VoiceProfile.name.asc())
            ).all()
        ),
        voice_ids,
    )
    return [profile.name for profile in profiles]


# What each target asks the model to fill in. Split because the two halves have different
# lifetimes: re-deriving motion for shots whose frames are already rendered must not ask
# for — or overwrite — the frames themselves.
TARGET_INSTRUCTIONS = {
    "shots": (
        "本次只需要拆解画面分镜：填写 narration、dialogue、speaker、visualPrompt、shotType。"
        "cameraMove、transition、durationSeconds、videoPrompt 一律留空或填 0。"
    ),
    "video": (
        "本次只需要补充视频分镜：为下方已有的每个分镜，按原顺序填写 cameraMove、transition、"
        "durationSeconds、videoPrompt。narration 与 visualPrompt 请原样回填，不要改写。"
        "返回的分镜数量必须与已有分镜完全一致。"
    ),
    "both": "本次需要同时拆解画面分镜与视频分镜：所有字段都要填写完整。",
}

DETAIL_INSTRUCTIONS = {
    "concise": "拆分粒度：精简。只保留推动主要剧情的关键镜头，合并连续的次要动作与过渡，通常控制在约 3-8 个分镜。",
    "standard": "拆分粒度：普通。保留主要剧情、关键动作和必要的反应镜头，在镜头数量与叙事完整性之间保持平衡，通常控制在约 4-20 个分镜。",
    "detailed": "拆分粒度：细节。尽可能拆出有叙事价值的动作、反应、台词节奏、视线和镜头变化，通常控制在约 8-40 个分镜，但不要为了凑数量制造重复镜头。",
}
STANDARD_DETAIL_INSTRUCTION = DETAIL_INSTRUCTIONS["standard"]


def build_user_prompt(
    *,
    episode: Episode,
    script: str,
    target: str,
    detail_level: str = "standard",
    detail_prompt: str | None = None,
    characters: list[dict[str, Any]],
    props: list[dict[str, Any]],
    voices: list[str],
    use_cast_sheet: bool,
    use_prop_sheet: bool,
    use_voice_sheet: bool,
    existing_shots: list[dict[str, Any]] | None = None,
) -> str:
    """The user turn: what to produce, what to lean on, and the script itself."""
    characters = [item for item in (characters or []) if isinstance(item, dict)]
    props = [item for item in (props or []) if isinstance(item, dict)]
    voices = [str(item).strip() for item in (voices or []) if item is not None and str(item).strip()]
    existing_shots = [item for item in (existing_shots or []) if isinstance(item, dict)]
    parts = [TARGET_INSTRUCTIONS.get(target, TARGET_INSTRUCTIONS["both"])]
    parts.append("连续性要求：按镜头顺序保持同场景中的人物外观、服装、道具、空间位置、视线、光线和情绪变化连贯；切换场景时写明转场并保留人物形象设定。")
    if detail_level == "custom" and (detail_prompt or "").strip():
        parts.append(f"自定义拆分要求（优先遵守）：\n{detail_prompt.strip()[:6000]}")
    else:
        parts.append(DETAIL_INSTRUCTIONS.get(detail_level, STANDARD_DETAIL_INSTRUCTION))
    parts.append(f"剧集标题：{(episode.title or '').strip()}")
    if (episode.synopsis or "").strip():
        parts.append(f"本集简介：{episode.synopsis.strip()}")
    parts.append(
        breakdown_reference_block(
            characters,
            props,
            voices,
            use_cast_sheet=use_cast_sheet,
            use_prop_sheet=use_prop_sheet,
            use_voice_sheet=use_voice_sheet,
        )
    )
    if target == "video" and existing_shots:
        # Narration alone is not enough to write a 承接块 against: the continuity the video
        # pass has to honour lives in the frame prompt the storyboard already rendered from.
        numbered = "\n".join(
            "\n".join(
                line
                for line in (
                    f"{index}. 剧情：{str(shot.get('narration') or '').strip()}",
                    f"   画面提示词：{str(shot.get('visual_prompt') or '').strip()}"
                    if str(shot.get("visual_prompt") or "").strip()
                    else "",
                    f"   现有视频提示词：{str(shot.get('video_prompt') or '').strip()}"
                    if str(shot.get("video_prompt") or "").strip()
                    else "",
                )
                if line
            )
            for index, shot in enumerate(existing_shots, start=1)
            if isinstance(shot, dict)
        )
        parts.append(f"已有分镜（共 {len(existing_shots)} 个，请逐一对应补充视频分镜）：\n{numbered}")
    else:
        parts.append("请按上述拆分粒度把剧本拆解成合适数量的分镜，按剧情顺序排列。精简档应明显少于普通档，细节档应明显多于普通档；不要为了凑数量制造重复镜头。")
    parts.append(f"剧本：\n{script.strip()}")
    return "\n\n".join(part for part in parts if part)


def system_prompt() -> str:
    return BREAKDOWN_SYSTEM


def resolve_speaker(session: Session, project_id: str, speaker: str) -> str | None:
    """Match a name the model wrote back to a character card, aliases included.

    Best-effort by design: the breakdown invents walk-ons the bible has never heard of, and
    an unmatched speaker is that working as intended, not an error. The dialogue keeps the
    name as written either way.
    """
    speaker = (speaker or "").strip()
    if not speaker:
        return None
    characters = session.exec(
        select(Character).where(Character.project_id == project_id, Character.deleted_at.is_(None))
    ).all()
    for character in characters:
        names = {character.name.strip()}
        names.update(part.strip() for part in (character.aliases or "").replace("，", ",").split(",") if part.strip())
        if speaker in names:
            return character.id
    # A script writing 林小满 where the card says 小满 (or the reverse) is the common case,
    # and an exact-match-only lookup silently drops every one of them.
    for character in characters:
        if character.name.strip() and (speaker in character.name or character.name in speaker):
            return character.id
    return None


__all__ = [
    "TARGET_INSTRUCTIONS",
    "build_user_prompt",
    "character_context",
    "prop_context",
    "resolve_speaker",
    "system_prompt",
    "voice_context",
]
