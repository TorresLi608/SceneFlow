"""Built-in prompt templates for every AI-assisted authoring step.

Kept in one module rather than inline at each call site so a user-visible wording change
is a single edit, and so the templates a user may override (a character state's system
prompt) sit next to the defaults they fall back to.

These are instructions sent to a model, not user-facing UI copy, so they stay out of
`frontend/src/lib/i18n.ts`.
"""

from __future__ import annotations


SYNOPSIS_SYSTEM = (
    "你是短剧的策划编辑。把用户给的项目简介改写得更吸引人：突出核心冲突与看点，"
    "保留原意与已有设定，不要编造原文没有的情节。只输出简介正文，不要标题、不要解释、"
    "不要 Markdown 标记，控制在 200 字以内。"
)


def synopsis_prompt(title: str, description: str) -> str:
    """The user turn for a synopsis polish. Title is context, description is the subject."""
    title = title.strip()
    header = f"剧名：{title}\n" if title else ""
    return f"{header}当前简介：\n{description.strip()}"


def cover_prompt(title: str, description: str, style_prompt: str = "") -> str:
    """A series cover, drawn from whatever the project already knows about itself.

    Deliberately poster-shaped rather than storyboard-shaped: this image identifies the
    series in a list, so it wants one readable focal subject, not a scene.
    """
    parts = [
        "为一部竖屏短剧绘制封面海报。要求：单一清晰主体，强烈氛围感，电影级打光，高细节，"
        "画面中不要出现任何文字、字幕或水印。",
        f"剧名：{title.strip()}。" if title.strip() else "",
        f"故事简介：{description.strip()}。" if description.strip() else "",
        f"整体风格：{style_prompt.strip()}。" if style_prompt.strip() else "",
    ]
    return " ".join(part for part in parts if part)


# The default instructions for drafting a character state's image prompt. A state may
# override this with its own `system_prompt`; the draft is always shown to the user before
# it draws anything, which is why the wording insists on a single self-contained paragraph.
CHARACTER_SHEET_SYSTEM = (
    "你是动画角色设定师。根据用户给的角色信息，写一段用于生成【三面图】的图像提示词。"
    "三面图指同一角色的正面、四分之三侧面、正侧面并排排列，同一套服装、同一光照、同一比例，"
    "纯色背景，全身，中性表情，不要文字、不要水印、不要多余道具。"
    "只输出提示词正文本身，不要标题、不要解释、不要 Markdown 标记，控制在 300 字以内。"
)

# Props are a single object rather than a turnaround, but they carry the same requirement:
# a neutral, well-lit reference the renderer can match against in any later shot.
PROP_SYSTEM = (
    "你是美术道具设计师。根据用户给的道具信息，写一段用于生成道具参考图的图像提示词。"
    "要求：单一物体居中，纯色背景，均匀打光，展示材质与结构细节，不要人物、不要文字、不要水印。"
    "只输出提示词正文本身，不要标题、不要解释、不要 Markdown 标记，控制在 200 字以内。"
)


def character_sheet_prompt(
    character_name: str,
    character_description: str,
    appearance_prompt: str,
    state_name: str,
    state_description: str,
) -> str:
    """The user turn for drafting a state's turnaround prompt.

    Everything the bible knows about the character goes in together: the model needs the
    card's own look to keep 幼年 and 老年 recognisably the same person.
    """
    lines = [f"角色名称：{character_name.strip()}"]
    if character_description.strip():
        lines.append(f"角色描述：{character_description.strip()}")
    if appearance_prompt.strip():
        lines.append(f"角色固定外观：{appearance_prompt.strip()}")
    lines.append(f"当前状态：{state_name.strip()}")
    if state_description.strip():
        lines.append(f"状态描述：{state_description.strip()}")
    return "\n".join(lines)


def prop_prompt(name: str, description: str) -> str:
    lines = [f"道具名称：{name.strip()}"]
    if description.strip():
        lines.append(f"道具描述：{description.strip()}")
    return "\n".join(lines)


def fallback_character_sheet_prompt(character_name: str, state_name: str, traits: str) -> str:
    """Drawn straight from the bible when the user never ran the drafting step.

    Plainer than a drafted prompt on purpose: this image is used as an image-to-image
    reference, so any drama baked into it would leak into every shot the character is in.
    """
    return (
        "Create a clean character turnaround reference sheet for an anime short drama. "
        "Show the same character three times side by side: front view, three-quarter view, "
        "and side profile. Identical outfit, identical proportions, even neutral lighting, "
        "plain neutral background, full body, neutral expression, no text, no watermark, "
        f"no props. Character: {character_name.strip()}. State: {state_name.strip()}. "
        f"Appearance: {traits.strip()}."
    )


def fallback_prop_prompt(name: str, description: str) -> str:
    return (
        "Create a clean prop reference image for an anime short drama. Single object, "
        "centred, plain neutral background, even lighting, material and construction "
        "clearly readable, no characters, no text, no watermark. "
        f"Prop: {name.strip()}. Details: {description.strip()}."
    )


# What a voice says in the merged reference track. The wording matters: this line is the
# only thing telling the video model *when* to use the timbre it just heard, so it names
# the role rather than merely demonstrating the voice. Both are editable per profile.
NARRATOR_SAMPLE_TEXT = "我是旁白。需要旁白配音的时候，请使用我这种声音。"


def character_sample_text(name: str) -> str:
    name = name.strip() or "这个角色"
    return f"我是{name}。{name}说台词的时候，请使用我这种声音。"


def tone_sheet_prompt(
    episode_title: str,
    script: str,
    shots: list[str],
    style_prompt: str = "",
    negative_prompt: str = "",
) -> str:
    """The single image that fixes an episode's look before any shot is rendered.

    Asked for as a labelled thumbnail grid on purpose. The grid is never a deliverable —
    every cell is far too small — but generating all of it in one sampling is exactly what
    makes lighting, palette, and render style agree, and the per-shot renders then carry it
    as a reference. The whole script goes in so the model can pace the look across the arc.
    """
    numbered = "\n".join(f"{index}. {shot.strip()}" for index, shot in enumerate(shots, start=1) if shot.strip())
    parts = [
        f"为短剧《{episode_title.strip()}》绘制一张分镜基调总览图。",
        "把下列分镜按顺序排成网格缩略图，每格画出该分镜的构图与氛围，格子左上角标注分镜序号。",
        "要求：所有格子共用同一套光线、色调、材质与渲染风格；不要出现字幕、水印或说明文字（序号除外）。",
        f"整体风格：{style_prompt.strip()}。" if style_prompt.strip() else "",
        f"避免出现：{negative_prompt.strip()}。" if negative_prompt.strip() else "",
        f"剧本：\n{script.strip()}" if script.strip() else "",
        f"分镜：\n{numbered}" if numbered else "",
    ]
    return "\n".join(part for part in parts if part)


def shot_prompt(
    shot_text: str,
    order: int,
    total: int,
    episode_title: str,
    style_prompt: str = "",
    negative_prompt: str = "",
) -> str:
    """One full-resolution frame, told explicitly to match the references it is given.

    The reference images do the heavy lifting; this names what they are for, because a model
    handed four unlabelled references will happily average them.
    """
    parts = [
        f"为短剧《{episode_title.strip()}》绘制第 {order}/{total} 个分镜的成片画面。",
        "参考图依次是：整集基调图（决定光线、色调与渲染风格）、角色三面图（决定人物长相与服饰）、"
        "道具图（决定道具外观）、上一个分镜的成图（决定场景与镜头的连续性）。"
        "请严格沿用它们，不要重新设计人物或场景。",
        "只画这一个分镜，单幅完整画面，不要拼图、不要网格、不要文字或水印。",
        f"分镜内容：{shot_text.strip()}",
        f"整体风格：{style_prompt.strip()}。" if style_prompt.strip() else "",
        f"避免出现：{negative_prompt.strip()}。" if negative_prompt.strip() else "",
    ]
    return "\n".join(part for part in parts if part)
