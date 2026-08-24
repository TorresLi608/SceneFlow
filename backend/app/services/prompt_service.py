"""Built-in prompt templates for every AI-assisted authoring step.

Kept in one module rather than inline at each call site so a user-visible wording change
is a single edit, and so the presets a user may pick between sit next to the defaults they
fall back to.

These are instructions sent to a model, not user-facing UI copy, so they stay out of
`frontend/src/lib/i18n.ts`.
"""

from __future__ import annotations


COVER_SYSTEM = (
    "你是短剧海报设计师。根据用户描述的封面画面，写一段用于生成竖屏短剧封面海报的图像提示词。"
    "要求：单一清晰主体，强烈氛围感，电影级打光，高细节。"
    "只输出提示词正文本身，不要标题、不要解释、不要 Markdown 标记，控制在 300 字以内。"
)


def cover_prompt(prompt: str, title: str = "", style_prompt: str = "") -> str:
    """A series cover, drawn from what the user asked for.

    The user's own description is the subject; the title and house style are context the
    model may lean on. It used to be the other way round — title plus synopsis — which
    produced an illustration of the plot rather than a poster, and gave the user no way to
    ask for the picture they had in mind.

    Deliberately poster-shaped rather than storyboard-shaped: this image identifies the
    series in a list, so it wants one readable focal subject, not a scene.
    """
    parts = [
        "为一部竖屏短剧绘制封面海报。要求：单一清晰主体，强烈氛围感，电影级打光，高细节，"
        "画面中不要出现任何文字、字幕或水印。",
        f"封面画面：{prompt.strip()}。" if prompt.strip() else "",
        f"剧名：{title.strip()}。" if title.strip() else "",
        f"整体风格：{style_prompt.strip()}。" if style_prompt.strip() else "",
    ]
    return " ".join(part for part in parts if part)


# The default instructions for drafting a character state's image prompt. The draft is
# always shown to the user before it draws anything, which is why the wording insists on a
# single self-contained paragraph.
#
# The sheet is a *setting sheet*, not a frame: it carries the character's name and written
# setting alongside the drawing so the reference is self-describing. That text is why
# `shot_prompt` states so firmly that the rendered shot must carry none — a labelled
# reference passed image-to-image will otherwise leak its captions into the episode.
CHARACTER_SHEET_SYSTEM = (
    "你是动画角色设定师。根据用户给的角色信息，写一段用于生成【角色设定三面图】的图像提示词。"
    "三面图指同一角色的正面、四分之三侧面、正侧面并排排列，同一套服装、同一光照、同一比例，"
    "纯色背景，全身，中性表情，不要多余道具。"
    "画面中必须以清晰易读的排版标注：角色名称（作为标题）、角色简介、角色设定要点。"
    "文字排布在画面边缘或下方的信息栏内，不要遮挡角色本身。"
    "只输出提示词正文本身，不要标题、不要解释、不要 Markdown 标记，控制在 400 字以内。"
)

# Props are a single object rather than a turnaround, but they carry the same requirement:
# a neutral, well-lit reference the renderer can match against in any later shot — and the
# same labelling, including who it belongs to, since an unattributed object is the first
# thing continuity loses.
PROP_SYSTEM = (
    "你是美术道具设计师。根据用户给的道具信息，写一段用于生成【道具设定图】的图像提示词。"
    "要求：单一物体居中，纯色背景，均匀打光，展示材质与结构细节，不要人物。"
    "画面中必须以清晰易读的排版标注：道具名称（作为标题）、归属角色（这是谁的道具）、"
    "道具简介、道具设定要点。文字排布在画面边缘或下方的信息栏内，不要遮挡道具本身。"
    "只输出提示词正文本身，不要标题、不要解释、不要 Markdown 标记，控制在 300 字以内。"
)


# Presets the user picks between before drafting. They are starting points rather than
# finished prompts: each is dropped into the prompt field for editing, and the drafting
# step can rewrite one from the character's actual details.
CHARACTER_PRESETS: tuple[dict[str, str], ...] = (
    {
        "key": "turnaround",
        "label": "三面图设定",
        "template": (
            "角色设定三面图：同一角色的正面、四分之三侧面、正侧面并排排列，同一套服装、同一光照、"
            "同一比例，全身，中性表情，纯色背景。画面下方信息栏标注角色名称、角色简介与角色设定要点，"
            "排版清晰易读，不遮挡角色。电影级柔和打光，高细节。"
        ),
    },
    {
        "key": "expressions",
        "label": "表情设定",
        "template": (
            "角色表情设定图：同一角色的六个半身表情（平静、微笑、愤怒、悲伤、惊讶、冷笑）排成两行三列，"
            "同一套服装、同一光照、同一画风，纯色背景。每格下方标注表情名称，画面顶部标注角色名称，"
            "底部信息栏写角色简介与设定要点。"
        ),
    },
    {
        "key": "outfit",
        "label": "服装设定",
        "template": (
            "角色服装设定图：同一角色的全身正面立绘，重点展示服装的剪裁、材质、配饰与细节特写，"
            "旁边附两到三个局部放大图。纯色背景，均匀打光。画面标注角色名称、服装名称与设定要点。"
        ),
    },
)

PROP_PRESETS: tuple[dict[str, str], ...] = (
    {
        "key": "single",
        "label": "单体道具图",
        "template": (
            "道具设定图：单一物体居中，纯色背景，均匀打光，清晰展示材质、结构与工艺细节，不要人物。"
            "画面下方信息栏标注道具名称、归属角色、道具简介与设定要点，排版清晰易读，不遮挡道具。"
        ),
    },
    {
        "key": "multiview",
        "label": "多角度道具图",
        "template": (
            "道具多角度设定图：同一物体的正面、侧面、背面与一个细节特写并排排列，同一光照与比例，"
            "纯色背景。画面标注道具名称、归属角色、道具简介与设定要点。"
        ),
    },
)

COVER_PRESETS: tuple[dict[str, str], ...] = (
    {
        "key": "portrait",
        "label": "人物特写海报",
        "template": "主角半身特写，眼神直视镜头，强烈情绪张力，电影级侧逆光，浅景深虚化背景，竖屏构图。",
    },
    {
        "key": "scene",
        "label": "场景氛围海报",
        "template": "故事核心场景的全景，人物背影置于画面下方三分之一，环境氛围压迫感强烈，冷暖对比打光，竖屏构图。",
    },
    {
        "key": "duo",
        "label": "双人对峙海报",
        "template": "两名主要角色一前一后错位站位，视线不交汇，中间留出戏剧性空隙，高对比打光，竖屏构图。",
    },
)

PRESETS: dict[str, tuple[dict[str, str], ...]] = {
    "character": CHARACTER_PRESETS,
    "prop": PROP_PRESETS,
    "cover": COVER_PRESETS,
}


def preset_template(kind: str, key: str) -> str:
    """The named preset's text, or the kind's first preset when the key is unknown."""
    presets = PRESETS.get(kind, ())
    if not presets:
        return ""
    for preset in presets:
        if preset["key"] == key:
            return preset["template"]
    return presets[0]["template"]


def character_sheet_prompt(
    character_name: str,
    character_description: str,
    appearance_prompt: str,
    state_name: str,
    state_description: str,
    preset: str = "",
) -> str:
    """The user turn for drafting a state's turnaround prompt.

    Everything the bible knows about the character goes in together: the model needs the
    card's own look to keep 幼年 and 老年 recognisably the same person, and the same
    details are what the sheet prints alongside the drawing.
    """
    lines = [f"角色名称：{character_name.strip()}"]
    if character_description.strip():
        lines.append(f"角色描述：{character_description.strip()}")
    if appearance_prompt.strip():
        lines.append(f"角色固定外观：{appearance_prompt.strip()}")
    lines.append(f"当前状态：{state_name.strip()}")
    if state_description.strip():
        lines.append(f"状态描述：{state_description.strip()}")
    if preset.strip():
        lines.append(f"参考版式：{preset_template('character', preset.strip())}")
    return "\n".join(lines)


def prop_prompt(name: str, description: str, owner_name: str = "", preset: str = "") -> str:
    lines = [f"道具名称：{name.strip()}"]
    if owner_name.strip():
        lines.append(f"归属角色：{owner_name.strip()}")
    if description.strip():
        lines.append(f"道具描述：{description.strip()}")
    if preset.strip():
        lines.append(f"参考版式：{preset_template('prop', preset.strip())}")
    return "\n".join(lines)


def fallback_character_sheet_prompt(character_name: str, state_name: str, traits: str) -> str:
    """Drawn straight from the bible when the user never ran the drafting step.

    Plainer than a drafted prompt on purpose: this image is used as an image-to-image
    reference, so any *drama* baked into it would leak into every shot the character is in.
    The printed name and traits are the deliberate exception — they make the reference
    self-describing, and `shot_prompt` is what keeps them out of the rendered frame.
    """
    return (
        "Create a clean character turnaround reference sheet for an anime short drama. "
        "Show the same character three times side by side: front view, three-quarter view, "
        "and side profile. Identical outfit, identical proportions, even neutral lighting, "
        "plain neutral background, full body, neutral expression, no props. "
        "Print the character's name as a heading and the traits in a caption bar along the "
        "bottom edge, clearly legible and not overlapping the figure. "
        f"Character: {character_name.strip()}. State: {state_name.strip()}. "
        f"Appearance: {traits.strip()}."
    )


def fallback_prop_prompt(name: str, description: str, owner_name: str = "") -> str:
    owner = f" Belongs to: {owner_name.strip()}." if owner_name.strip() else ""
    return (
        "Create a clean prop reference image for an anime short drama. Single object, "
        "centred, plain neutral background, even lighting, material and construction "
        "clearly readable, no characters. Print the prop's name as a heading and the "
        "details in a caption bar along the bottom edge, clearly legible and not "
        f"overlapping the object. Prop: {name.strip()}.{owner} Details: {description.strip()}."
    )


# What a voice says in the merged reference track. The wording matters: this line is the
# only thing telling the video model *when* to use the timbre it just heard, so it names
# the role rather than merely demonstrating the voice. Both are editable per profile.
NARRATOR_SAMPLE_TEXT = "我是旁白。需要旁白配音的时候，请使用我这种声音。"


def character_sample_text(name: str) -> str:
    name = name.strip() or "这个角色"
    return f"我是{name}。{name}说台词的时候，请使用我这种声音。"


# Splitting a script used to produce a narration line and a picture prompt, which is a
# storyboard for a comic, not for a drama: nothing said how the camera moved, how one shot
# reached the next, or how long any of it ran. These are the fields a shot actually needs
# before a clip can be generated from it.
BREAKDOWN_SYSTEM = (
    "你是短剧分镜导演。把剧本拆解成可直接用于生成画面与视频的分镜表，返回严格的 JSON。\n"
    "字段说明：\n"
    "- narration：这一分镜发生了什么，简洁的画面叙述。\n"
    "- dialogue：这一分镜的台词原文；没有台词就留空字符串。\n"
    "- speaker：说这句台词的角色名；没有台词或是旁白就留空字符串。\n"
    "- visualPrompt：静态画面提示词，描述构图、环境、人物姿态、光线、氛围。\n"
    "- shotType：景别，如 远景 / 全景 / 中景 / 近景 / 特写 / 过肩。\n"
    "- cameraMove：运镜手法，如 固定 / 推镜 / 拉镜 / 摇镜 / 跟拍 / 手持晃动 / 升降。\n"
    "- transition：从上一个分镜进入这一分镜的转场方式，如 硬切 / 叠化 / 淡入 / 淡出 / 闪白；"
    "第一个分镜通常是 淡入。\n"
    "- durationSeconds：这一分镜预计生成多少秒视频，整数，通常 2 到 10 秒，按台词长度与动作复杂度估算。\n"
    "- videoPrompt：动态提示词，描述这几秒内人物与镜头如何运动、表情与情绪如何变化；"
    "它描述的是一段时间，不是一张静止画面，不要照抄 visualPrompt。\n"
    "只输出 JSON，不要解释、不要 Markdown 代码块。"
)


def breakdown_reference_block(
    characters: list[dict[str, str]],
    props: list[dict[str, str]],
    voices: list[str],
    *,
    use_cast_sheet: bool = False,
    use_prop_sheet: bool = False,
    use_voice_sheet: bool = False,
) -> str:
    """The bible entries the breakdown may lean on, phrased so the model knows what to defer to.

    Three distinct cases, and the wording has to keep them apart:

    - a character with a drawn sheet — say so, so the prompt points at it rather than
      re-describing a face the renderer will get from the reference anyway;
    - a character with only written setting — the model reasons from the text;
    - anyone the bible has never heard of (walk-ons, 甲乙丙丁) — invented from the script.

    Selecting nothing at all is meaningful: it means decide everything from the script.
    """
    if not any((characters, props, voices, use_cast_sheet, use_prop_sheet, use_voice_sheet)):
        return (
            "本次没有提供任何角色、道具或音色参考资料。"
            "请完全依据剧本内容自行推断所有人物、道具与声音的设定。"
        )

    lines: list[str] = ["以下是本剧已有的设定资料，请在分镜提示词中优先沿用它们："]

    if use_cast_sheet:
        lines.append("【角色】已提供整体角色总图。涉及已知角色时，请写明「参照整体角色图」。")
    if characters:
        lines.append("【角色】")
        for character in characters:
            name = character.get("name", "").strip()
            detail = "；".join(
                part for part in (character.get("description", "").strip(), character.get("appearance", "").strip()) if part
            )
            if character.get("hasImage"):
                lines.append(f"- {name}：已有角色设定三面图。涉及该角色时请写明「参照《{name}》三面图」。{detail}")
            else:
                lines.append(f"- {name}：没有设定图，请依据以下文字设定推理其外观。{detail}")

    if use_prop_sheet:
        lines.append("【道具】已提供整体道具总图。涉及已知道具时，请写明「参照整体道具图」。")
    if props:
        lines.append("【道具】")
        for prop in props:
            name = prop.get("name", "").strip()
            owner = prop.get("owner", "").strip()
            owned = f"（{owner}的道具）" if owner else ""
            if prop.get("hasImage"):
                lines.append(f"- {name}{owned}：已有道具设定图，请写明「参照《{name}》道具图」。{prop.get('description', '').strip()}")
            else:
                lines.append(f"- {name}{owned}：没有设定图，请依据文字设定推理。{prop.get('description', '').strip()}")

    if use_voice_sheet:
        lines.append("【音色】已提供整体音色参考轨。")
    if voices:
        lines.append("【音色】已配置：" + "、".join(voices) + "。台词分镜请标注说话角色，便于后续配音对应。")

    lines.append(
        "剧本中出现但不在上述清单里的角色（配角、路人、甲乙丙丁等），"
        "以及未列出的道具与声音，请依据剧本描述自行推断生成，不要遗漏。"
    )
    return "\n".join(lines)


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

    The instruction against text is load-bearing rather than cosmetic: the cast and prop
    sheets now print names and setting notes next to the drawings, and without this the
    model copies those captions straight into the rendered shot.
    """
    parts = [
        f"为短剧《{episode_title.strip()}》绘制第 {order}/{total} 个分镜的成片画面。",
        "参考图依次是：整集基调图（决定光线、色调与渲染风格）、角色设定三面图（决定人物长相与服饰）、"
        "道具设定图（决定道具外观）、上一个分镜的成图（决定场景与镜头的连续性）。"
        "请严格沿用它们，不要重新设计人物或场景。",
        "重要：参考图上的角色名、道具名、简介与设定文字只是给你看的说明，"
        "成片画面里绝对不能出现任何文字、标注、信息栏、字幕或水印。",
        "只画这一个分镜，单幅完整画面，不要拼图、不要网格。",
        f"分镜内容：{shot_text.strip()}",
        f"整体风格：{style_prompt.strip()}。" if style_prompt.strip() else "",
        f"避免出现：{negative_prompt.strip()}。" if negative_prompt.strip() else "",
    ]
    return "\n".join(part for part in parts if part)
