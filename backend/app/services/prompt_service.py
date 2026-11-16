"""Built-in prompt templates for every AI-assisted authoring step.

Kept in one module rather than inline at each call site so a user-visible wording change
is a single edit, and so the presets a user may pick between sit next to the defaults they
fall back to.

These are instructions sent to a model, not user-facing UI copy, so they stay out of
`frontend/src/lib/i18n.ts`.
"""

from __future__ import annotations

import math
import re
from typing import Any


VISUAL_STYLE_PROMPTS = {
    "cinematic": "电影风格，真人电影质感，电影级构图与灯光，细腻真实材质，富有层次的景深与色彩分级",
    "anime": "动漫风格，二维动画画面，清晰线稿与赛璐璐上色，统一的动画角色造型，避免真人摄影或三维渲染质感",
    "realistic": "写实风格，自然真实的人物与环境，准确的比例和材质，自然光与纪实摄影质感，避免动漫线稿或卡通渲染",
    "3d": "3D 渲染风格，统一的三维角色与场景，立体建模、物理材质与体积光，精致的三维动画质感，避免二维线稿或真人摄影",
}


def visual_style_prompt(visual_style: str = "", style_prompt: str = "") -> str:
    """Resolve pure style parameters; legacy projects retain their custom prompt verbatim."""
    preset = VISUAL_STYLE_PROMPTS.get(visual_style, "")
    custom = style_prompt.strip()
    if not preset:
        return custom
    return preset + (f"。补充要求：{custom}" if custom else "") + "。整部作品保持此画面风格；冲突的风格描述以此配置为准"


def with_visual_style(prompt: str, style: str) -> str:
    """Apply the resolved project style without rewriting the user's subject or motion."""
    return f"{prompt}\n整体画面风格：{style}" if style else prompt


# The finish every rendered frame is held to. Worded without naming a look — "真实材质"
# would fight an anime project — so it sits under whichever visual style is configured.
# The defect list is the part that earns its place: image models drift toward exactly
# these failures on multi-character frames, and a storyboard frame with a sixth finger
# becomes the first frame of a clip.
IMAGE_QUALITY_DIRECTIVE = (
    "成片级完成度：主体清晰锐利、焦点落在本镜的戏剧重点上；构图有明确的视觉引导与前景、中景、背景层次；"
    "光线有明确的主光方向并与场景的时间、光源一致，明暗过渡自然；人物五官端正、比例准确，"
    "手部与肢体结构正确，表情与视线符合剧情。"
    "不要出现畸形或多余的手指与肢体、重复或融合的人物、面部崩坏、模糊、噪点、低清晰度、过曝或死黑。"
)

# The same bar for a clip. A video model left alone tends to do three things that break a
# drama: cut inside the shot, let a face drift over the seconds, and paint captions.
VIDEO_QUALITY_DIRECTIVE = (
    "成片要求：全片只有本镜这一个连续镜头，不在镜头内切换画面、不分屏；"
    "人物的长相、发型、服装与配饰从头到尾保持不变，五官与肢体不变形；"
    "动作自然连贯、符合物理规律，表演有细微的表情与眼神变化；镜头运动平稳，光线与色调稳定；"
    "画面中不出现字幕、文字或水印。"
)


COVER_SYSTEM = (
    "你是短剧海报设计师。根据用户描述的封面画面，写一段用于生成竖屏短剧封面海报的图像提示词。"
    "要求：单一清晰主体，强烈氛围感，电影级打光，高细节；写明主体的姿态与视线、构图与留白、"
    "主光方向与色调、景深；人物五官清晰端正、肢体结构准确。"
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
        "人物五官清晰端正、肢体结构准确，画面中不要出现任何文字、字幕或水印。",
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
#
# One image, three zones: the turnaround, an expression set, and a profile card. The
# expression close-ups are what lets a later shot ask for 怒 or 悲 and still get the same
# face; the profile card (name, age, role, the one or two features that make the character
# recognisable) is what the sheet says about itself when it is read as a reference.
CHARACTER_SHEET_SYSTEM = (
    "你是角色视觉设定师。根据用户给的角色信息，写一段用于生成【角色设定总图】的图像提示词，"
    "总图的全部内容绘制在同一张图上，分为三个区域："
    "①角色三面图：同一角色的正面、四分之三侧面、正侧面并排排列，同一套服装、同一光照、同一比例，"
    "全身，中性表情，不要多余道具；"
    "②角色多表情集：至少 4 个情绪反差鲜明的五官特写（如喜、怒、冷、悲），同一张脸、同一发型，每格下方标注情绪名称；"
    "③角色档案摘要：姓名、年龄、定位、核心外貌记忆点。年龄与定位依据用户给的角色信息填写，"
    "信息不足时按剧情合理推断并保持简短，不要编造与原意冲突的设定。"
    "三个区域里必须是同一个人：脸型、五官、发型发色、体型比例与服装细节完全一致；"
    "线条干净、五官清晰端正、手部与肢体结构准确，服装的材质、配色与配饰写具体，便于后续每个分镜对照。"
    "纯色背景。画面中必须以清晰易读的排版标注：角色名称（作为标题）、角色简介、角色设定要点与上述档案摘要。"
    "文字排布在画面边缘或下方的信息栏内，不要遮挡角色本身。"
    "只输出提示词正文本身，不要标题、不要解释、不要 Markdown 标记，控制在 500 字以内。"
)

# Props get a multi-angle sheet rather than a single view, and carry the same requirement:
# a neutral, well-lit reference the renderer can match against in any later shot — and the
# same labelling, including who it belongs to, since an unattributed object is the first
# thing continuity loses.
PROP_SYSTEM = (
    "你是美术道具设计师。根据用户给的道具信息，写一段用于生成【道具多角度设定图】的图像提示词。"
    "要求：同一物体的正面、侧面、背面与一个材质或结构细节特写并排排列，同一光照与比例，"
    "纯色背景，均匀打光，清晰展示材质、结构与工艺细节，各视角是同一件物体、形制与配色完全一致，不要人物。"
    "画面中必须以清晰易读的排版标注：道具名称（作为标题）、归属角色（这是谁的道具）、"
    "道具简介、道具设定要点。文字排布在画面边缘或下方的信息栏内，不要遮挡道具本身。"
    "只输出提示词正文本身，不要标题、不要解释、不要 Markdown 标记，控制在 400 字以内。"
)


# Presets the user picks between before drafting a cover. They are starting points rather
# than finished prompts: each is dropped into the prompt field for editing. Character and
# prop sheets no longer offer presets — their layout is fixed by the system prompts above,
# and the draft is written from the card's own details.
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
    "cover": COVER_PRESETS,
}


def character_sheet_prompt(
    character_name: str,
    character_description: str,
    appearance_prompt: str,
    state_name: str,
    state_description: str,
) -> str:
    """The user turn for drafting a state's sheet prompt.

    Everything the bible knows about the character goes in together: the model needs the
    card's own look to keep 幼年 and 老年 recognisably the same person, and the same
    details are what the sheet prints alongside the drawing — including the profile card,
    whose age and role the model has to read out of these lines.
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


def prop_prompt(name: str, description: str, owner_name: str = "") -> str:
    lines = [f"道具名称：{name.strip()}"]
    if owner_name.strip():
        lines.append(f"归属角色：{owner_name.strip()}")
    if description.strip():
        lines.append(f"道具描述：{description.strip()}")
    return "\n".join(lines)


def fallback_character_sheet_prompt(character_name: str, state_name: str, traits: str) -> str:
    """Drawn straight from the bible when the user never ran the drafting step.

    Plainer than a drafted prompt on purpose: this image is used as an image-to-image
    reference, so any *drama* baked into it would leak into every shot the character is in.
    The printed name and traits are the deliberate exception — they make the reference
    self-describing, and `shot_prompt` is what keeps them out of the rendered frame. The
    same three zones as the drafted sheet, so a card that skipped drafting is not the one
    card without an expression set.
    """
    return (
        "Create a clean character reference sheet for an anime short drama, all on one image "
        "in three zones. Zone 1, turnaround: the same character three times side by side — "
        "front view, three-quarter view, and side profile — identical outfit, identical "
        "proportions, full body, neutral expression, no props. Zone 2, expression set: at "
        "least four facial close-ups with strongly contrasting emotions (joy, anger, cold "
        "detachment, sorrow), same face and hairstyle, each labelled with its emotion. "
        "Zone 3, profile card: name, age, role, and the key visual traits that make the "
        "character recognisable; infer age and role from the details below and keep them "
        "short. Even neutral lighting, plain neutral background. Print the character's name "
        "as a heading and the profile card in a caption bar along the bottom edge, clearly "
        "legible and not overlapping the figures. "
        f"Character: {character_name.strip()}. State: {state_name.strip()}. "
        f"Appearance: {traits.strip()}."
    )


def fallback_prop_prompt(name: str, description: str, owner_name: str = "") -> str:
    owner = f" Belongs to: {owner_name.strip()}." if owner_name.strip() else ""
    return (
        "Create a clean multi-angle prop reference sheet for an anime short drama. Show the "
        "same object four times side by side: front view, side view, back view, and one "
        "close-up of its material or construction. Identical lighting and scale, plain "
        "neutral background, even lighting, no characters. Print the prop's name as a "
        "heading and its owner, description, and setting notes in a caption bar along the "
        "bottom edge, clearly legible and not overlapping the object. "
        f"Prop: {name.strip()}.{owner} Details: {description.strip()}."
    )


# Polishing a script is where dialogue gets better — the breakdown copies lines verbatim,
# so a flat line stays flat all the way to the clip. The brief is a short drama's: a hook
# in the first seconds, one goal per scene, lines short enough to be said in one shot.
# It names no visual style: the project's configured style is appended to the script by
# the caller, and a hardcoded "anime" here used to contradict a realistic or 3D project.
SCRIPT_POLISH_SYSTEM = (
    "你是短剧编剧与剧本医生。在不改变故事主线、人物关系、结局与原文语言的前提下打磨剧本，"
    "返回严格的 JSON：optimizedScript（字符串，打磨后的完整剧本）与 tips（字符串数组，3 到 5 条仍可改进的建议）。\n"
    "打磨要求：\n"
    "1. 结构：开场三句话内抛出悬念或冲突；每一场只有一个明确的目标和一次情绪转折；冲突逐场升级；"
    "结尾停在悬念或情绪顶点上。删掉不推动剧情的铺垫与重复。\n"
    "2. 场次：每一场用一行写明地点与时间（如「客厅·黄昏」），再写动作与台词，便于后续拆分镜头。\n"
    "3. 台词：口语化、短句为主，单句尽量不超过 25 个字；每个角色有自己的说话方式，不要所有人一个腔调；"
    "多用潜台词与动作代替直白的解释，删掉「正如你所知」式的说明性对白；关键台词要有记忆点。"
    "台词前标明说话角色，必要时在括号里写语气或动作。\n"
    "4. 动作与画面：把心理活动改写成拍得出来的动作、表情与细节；每段只写一个动作焦点；"
    "不要写镜头术语，镜头由分镜阶段决定。\n"
    "5. 不要新增与主线无关的人物和情节，不要改动专有名词。\n"
    "6. 剧本末尾若附有「整体画面风格：…」一行，那是画面风格说明而不是剧本正文：不要改写它，也不要写进 optimizedScript。\n"
    "只输出 JSON，不要解释、不要 Markdown 代码块。"
)

# The legacy single-screen parse. Style-neutral for the same reason as the polish above.
SCRIPT_PARSE_SYSTEM = (
    "You convert screenplay text into storyboard scenes. Return strict JSON only with schema: "
    '{"scenes":[{"narration":"...","visualPrompt":"..."}]}'
)
SCRIPT_PARSE_INSTRUCTION = (
    "Parse the script into 4-12 scenes in story order. Keep each narration to one concise sentence. "
    "For each scene write a visualPrompt for one finished frame: camera angle and shot size, who is in "
    "frame with their position, pose, expression and clothing, the location and time of day, the "
    "key-light direction and mood. Keep every character's look and each location's layout consistent "
    "across scenes, and write in the script's own language. Do not name an art style; the project "
    "supplies it. Script:\n"
)


def fallback_frame_prompt(narration: str) -> str:
    """A frame prompt for a shot the model described but never wrote a picture for."""
    return f"storyboard frame, cinematic composition, {narration}"


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
#
# The fields alone still produced shots that each looked fine and did not cut together:
# every shot was written as if it were the only one. The 导演工作法 block is what makes the
# model plan the episode before it writes a shot — fix each location's geography and light
# once, fix each character's look once, and then obey the handful of editing rules (axis,
# shot-size progression, match on action) that make consecutive clips read as one scene.
# It plans silently: asking for the plan in the JSON would spend the output budget on
# text nothing consumes.
#
# Dialogue is copied, never rewritten — the script is the author's, and polishing lines is
# a separate, explicit step. What the breakdown does own is pacing: one line per shot, a
# long line split across a cut, and a duration long enough to say it.
#
# The length caps are load-bearing. The reply is capped at 8192 output tokens and a
# detailed split can run to forty shots; uncapped prompts get the array truncated.
BREAKDOWN_SYSTEM = (
    "你是院线级短剧的分镜导演兼摄影指导。把剧本拆解成可直接用于生成画面与视频的分镜表，"
    '返回严格的 JSON，结构为 {"shots":[{...}, ...]}，按剧情顺序排列。\n'
    "【导演工作法】动笔前先在心里完成以下设计，不要输出设计过程，只输出 JSON：\n"
    "1. 场次：按「地点＋时间」把剧本分成若干场。为每一场确定固定的空间布局（每个人物在画面的左/右/前/后，"
    "门窗与主要陈设的位置）、时间与天气、主光源的方向与色温。同一场内的所有分镜必须沿用，不得无故改变。\n"
    "2. 造型：为每个出场人物确定本集固定的发型、服装、配饰与随身道具；除非剧本写明换装、受伤或弄脏，"
    "每个分镜都保持一致。人物一律用设定资料或剧本里的名字称呼，全程同一个称呼，不要换成「他」「男主」「老板」。\n"
    "3. 节奏：找出本集的钩子、冲突升级点与高潮。第 1 个分镜要在 3 秒内用强悬念、强冲突或强画面抓住观众；"
    "情绪逐镜递进；最后一个分镜落在情绪顶点或悬念上，不要平淡收尾。"
    "这些只能靠选取、编排和强调剧本已有的内容来实现，不要编造剧本里没有的情节、人物或台词。\n"
    "4. 镜头语言：\n"
    "   - 每一场的第一个分镜用远景或全景交代环境与人物的位置关系，之后再推近；\n"
    "   - 景别随情绪收紧：铺垫用全景、中景，对峙与爆发用近景、特写，关键信息（眼神、手部动作、关键道具）单独给特写；\n"
    "   - 相邻两个分镜的景别或机位角度要有明显变化，避免跳切；\n"
    "   - 对话遵守轴线：两人各自始终在画面固定一侧，视线相对；用正反打与过肩镜头，并穿插听者的反应镜头；\n"
    "   - 动作接动作：上一镜结束时的动作、位置、朝向与手持物，就是下一镜的起点；\n"
    "   - 一个分镜只表达一个动作或一次情绪转折，只用一个连续镜头，镜头内不切换画面。\n"
    "字段说明：\n"
    "- narration：这一分镜发生了什么，一句简洁的剧情叙述，不超过 40 字。\n"
    "- dialogue：这一分镜里说出的台词，逐字沿用剧本原文，不要改写、润色或补写；内心独白与画外音也写在这里。"
    "一个分镜最多一位角色的一句台词（或一小段连贯的话）；超过约 25 字的长台词按语气停顿拆到相邻分镜，"
    "中间可插入听者的反应镜头。没有台词就留空字符串。\n"
    "- speaker：说这句台词的角色名；没有台词或是旁白就留空字符串。\n"
    "- visualPrompt：静态画面提示词，定格这一分镜最有代表性的一瞬间。\n"
    "- shotType：景别，如 远景 / 全景 / 中景 / 近景 / 特写 / 过肩。\n"
    "- cameraMove：这一分镜的一种主要运镜，如 固定 / 缓慢推镜 / 拉镜 / 摇镜 / 跟拍 / 环绕 / 手持晃动 / 升降；"
    "运镜要有动机（推近强调情绪、跟拍跟随行动、固定承载对话），不要每个分镜都推拉。\n"
    "- transition：从上一个分镜进入这一分镜的转场方式，如 硬切 / 叠化 / 淡入 / 淡出 / 闪白。"
    "同一场内用 硬切；换场或时间跳跃才用 叠化、淡入淡出；第一个分镜通常是 淡入。\n"
    "- durationSeconds：这一分镜的视频秒数，整数，通常 2 到 10 秒。有台词时不少于「台词字数÷4＋1」秒；"
    "纯动作或反应镜头 2 到 5 秒；交代环境的镜头 3 到 4 秒。\n"
    "- videoPrompt：动态提示词，描述这几秒内人物与镜头如何运动、表情与情绪如何变化；"
    "它描述的是一段时间，不是一张静止画面，不要照抄 visualPrompt。\n"
    "写法要求（visualPrompt 与 videoPrompt 都必须遵守）：\n"
    "1. 开头写「分镜X：」，X 是这一分镜在本集中的序号，从 1 开始。\n"
    "2. 从第 2 个分镜起，紧接着写一个【】承接块，说明与上一镜的关系：是否同一场景、"
    "人物的样貌与衣着是否延续、上一镜结束时的姿态与位置朝向如何被接住。"
    "发生转场时在【】里写明切到的新场景（地点、时间、光线），并注明人物形象与服装保持不变。第 1 个分镜不写【】。\n"
    "3. 承接块要写出可执行的连续性约束（具体到发型、服装、配饰、手持物、左右站位、朝向、光线、环境），"
    "而不是只重复剧情。\n"
    "4.【】之后写这一分镜自己的内容。visualPrompt 依次写：机位角度（平视 / 俯拍 / 仰拍 / 过肩）；"
    "主体是谁、在画面的什么位置、姿态动作、表情与视线方向、衣着；地点与时间、前中后景的层次与关键陈设；"
    "主光方向、色温与明暗对比；色调与氛围；结尾带上景别。\n"
    "5. videoPrompt 依次写：起始状态（接住上一镜）；按时间先后的 1 到 3 个动作节拍，写清谁做什么、速度与力度；"
    "表情与情绪从什么变成什么；镜头的运动方向、速度与起止景别；结束时的姿态与位置（留给下一镜承接）。"
    "有台词时写明谁在说话以及说话时的神态，但不要把台词原文写进 videoPrompt；结尾带上景别。\n"
    "6. 只写镜头拍得到的东西：把「气氛紧张」「十分愤怒」这类抽象词换成看得见的细节（指节发白、下颌绷紧、眼眶泛红）。"
    "不要在画面里安排字幕、文字或对话气泡。\n"
    "7. visualPrompt 与 videoPrompt 各自控制在 60 到 130 字之间：信息要具体，但不要堆砌形容词。\n"
    "示例（visualPrompt 和 videoPrompt 都要带承接块）：\n"
    "分镜 1：\n"
    "  visualPrompt: 分镜 1：平视，陆沉站在客厅中央偏右，黑色衬衫袖口挽起，下颌绷紧，目光压向画面左侧沙发旁的苏晚；"
    "苏晚穿米色针织衫，双手攥着手机；落地窗在画面左后方，黄昏暖光从窗外斜射进来，在两人之间拉出长影，全景\n"
    "  videoPrompt: 分镜 1：陆沉站定不动，胸口起伏，右手缓缓握拳，目光始终锁住苏晚；苏晚后退半步，手机攥得更紧；"
    "镜头从全景缓慢推向两人之间，结束时陆沉仍在画面右侧，全景\n"
    "分镜 2：\n"
    "  visualPrompt: 分镜 2：【承接上一镜，同一客厅、同样的黄昏暖光；陆沉仍是黑色衬衫、袖口挽起，站在画面右侧，"
    "苏晚仍在左侧】过肩机位越过苏晚左肩拍陆沉，他右脚前迈一步，右手抓住苏晚左臂，眉头紧锁、眼眶泛红，近景\n"
    "  videoPrompt: 分镜 2：【承接上一镜结束姿态，陆沉从站定握拳开始】陆沉向前迈一步，右手抓住苏晚左臂并收紧，"
    "开口说话时嘴唇发抖，神情从压抑的愤怒变为激动；苏晚肩膀一缩，偏过头；镜头固定，结束时两人相距半步，近景\n"
    "只输出 JSON，不要解释、不要 Markdown 代码块。"
)


# The opener the convention above asks for. Models drop it often enough — and shots get
# reordered, inserted and deleted afterwards — that the number is re-derived from
# `order_num` on write rather than trusted from the model. Full-width digits included
# because a model writing Chinese sometimes emits them.
SHOT_LABEL_PATTERN = re.compile(r"^\s*分镜\s*[0-9０-９]+\s*[：:]\s*")


def shot_label(order: int) -> str:
    return f"分镜 {order}："


def with_shot_label(text: str, order: int) -> str:
    """`text` opening with the correct `分镜X：`, replacing a wrong or missing one.

    Empty text stays empty: a shot with no prompt should not acquire one made of nothing
    but its own number.
    """
    body = SHOT_LABEL_PATTERN.sub("", str(text or "").strip())
    return f"{shot_label(order)}{body}" if body else ""


# The 【】 block a shot opens with, right after its label.
CARRY_OVER_PATTERN = re.compile(r"^\s*【[^】]*】\s*")


def shot_action_text(text: str) -> str:
    """A stored shot prompt with its `分镜X：` label and 【承接块】 removed.

    What is left is what the shot itself does. The carry-over block describes the shot
    *before* it, so quoting a whole prompt as "the previous shot" hands the model the
    state from two shots back alongside a shot number that is not the one being rendered.
    """
    body = SHOT_LABEL_PATTERN.sub("", str(text or "").strip())
    return CARRY_OVER_PATTERN.sub("", body).strip()


# Chinese drama dialogue runs at roughly four to five characters a second, English at
# under three words; the half second is the breath before the line.
CJK_PATTERN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’-]*")
MAX_SHOT_SECONDS = 60


def dialogue_seconds(dialogue: str) -> int:
    """The shortest clip a line can be spoken in; 0 when there is no line."""
    text = str(dialogue or "").strip()
    cjk = len(CJK_PATTERN.findall(text))
    words = len(WORD_PATTERN.findall(text))
    if not cjk and not words:
        return 0
    return max(2, math.ceil(cjk / 4.5 + words / 2.8 + 0.5))


def shot_duration_seconds(estimate: int, dialogue: str = "") -> int:
    """The model's duration estimate, raised until the shot's line fits in it.

    The breakdown is told the rule and still under-counts long lines — and a clip shorter
    than its dialogue either cuts the line off or rushes the performance, which no later
    step can repair. A shot with no line keeps the estimate untouched, 0 included: that
    means undecided, and the render falls back to the batch default.
    """
    estimate = max(int(estimate or 0), 0)
    needed = dialogue_seconds(dialogue)
    return min(max(estimate, needed), MAX_SHOT_SECONDS) if needed else min(estimate, MAX_SHOT_SECONDS)


# Transitions that mean "no effect at the seam". Naming one to a video model is worse than
# silence: told about a 硬切, it tends to perform a cut inside the clip.
HARD_CUTS = {"", "硬切", "直切", "切", "切镜", "切换", "无", "cut", "hard cut", "straight cut", "none"}

# How much of the previous shot is quoted back. Enough for its action and end state; the
# full prompt would crowd out the shot actually being rendered.
PREVIOUS_SHOT_CHARS = 260


def video_direction(shot_type: str = "", camera_move: str = "", transition: str = "", prompt: str = "") -> str:
    """Shot size, camera move and opening transition, as one line under the motion prompt.

    These are the fields the breakdown works out that the motion prompt has no guaranteed
    place for — a user-edited prompt often drops them. Shot size is skipped when the
    prompt already states it. A transition is scoped to the opening instant so the rest of
    the clip stays one continuous take.
    """
    shot_type, camera_move, transition = (str(value or "").strip() for value in (shot_type, camera_move, transition))
    parts = [
        f"景别：{shot_type}" if shot_type and shot_type not in str(prompt or "") else "",
        f"运镜：{camera_move}" if camera_move else "",
        f"开场转场：以{transition}进入本镜，只作用于开场瞬间，之后保持连续镜头"
        if transition.lower() not in HARD_CUTS
        else "",
    ]
    return "；".join(part for part in parts if part)


def dialogue_performance(speaker_name: str = "") -> str:
    """How a spoken line is to be performed; goes with the line `compile_prompt` appends."""
    who = f"角色“{speaker_name.strip()}”" if speaker_name.strip() else "说话的角色"
    return (
        f"表演：{who}说出下面这句台词，口型与台词同步，语气、表情与眼神贴合此刻的情绪；"
        "其他人物只做在场反应，不开口、不抢话；台词以外不要增加别的对白，不要生成字幕。"
    )


def video_continuity(previous_prompt: str) -> str:
    """The seam with the previous shot: open where it ended, on the same people and place."""
    previous = shot_action_text(previous_prompt)[:PREVIOUS_SHOT_CHARS]
    if not previous:
        return ""
    return (
        "连续性约束：本镜开场必须直接承接上一镜结束时的人物姿态、位置、朝向、服装、手持物和环境状态，"
        "人物长相与场景布局、光线方向保持一致，不得无过渡改变。"
        f"上一镜内容（仅供承接，不要重演）：{previous}"
    )


def breakdown_reference_block(
    characters: list[dict[str, str]],
    props: list[dict[str, str]],
    *,
    use_cast_sheet: bool = False,
    use_prop_sheet: bool = False,
) -> str:
    """The bible entries the breakdown may lean on, phrased so the model knows what to defer to.

    Three distinct cases, and the wording has to keep them apart:

    - a character with a drawn sheet — say so, so the prompt points at it rather than
      re-describing a face the renderer will get from the reference anyway;
    - a character with only written setting — the model reasons from the text;
    - anyone the bible has never heard of (walk-ons, 甲乙丙丁) — invented from the script.

    Selecting nothing at all is meaningful: it means decide everything from the script.
    Voices are not part of this block: the breakdown writes no audio, and the speaker
    column is filled from the cast regardless.
    """
    def clean(value: Any) -> str:
        return str(value or "").strip()

    if not any((characters, props, use_cast_sheet, use_prop_sheet)):
        return (
            "本次没有提供任何角色或道具参考资料。"
            "请完全依据剧本内容自行推断所有人物与道具的设定。"
        )

    lines: list[str] = ["以下是本剧已有的设定资料，请在分镜提示词中优先沿用它们："]

    if use_cast_sheet:
        lines.append("【角色】已提供整体角色总图。涉及已知角色时，请写明「参照整体角色图」。")
    if characters:
        lines.append("【角色】")
        for character in characters:
            if not isinstance(character, dict):
                continue
            name = clean(character.get("name"))
            detail = "；".join(
                part for part in (clean(character.get("description")), clean(character.get("appearance"))) if part
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
            if not isinstance(prop, dict):
                continue
            name = clean(prop.get("name"))
            owner = clean(prop.get("owner"))
            owned = f"（{owner}的道具）" if owner else ""
            if prop.get("hasImage"):
                lines.append(f"- {name}{owned}：已有道具设定图，请写明「参照《{name}》道具图」。{clean(prop.get('description'))}")
            else:
                lines.append(f"- {name}{owned}：没有设定图，请依据文字设定推理。{clean(prop.get('description'))}")

    lines.append(
        "剧本中出现但不在上述清单里的角色（配角、路人、甲乙丙丁等）以及未列出的道具，"
        "请依据剧本描述自行推断生成，不要遗漏。台词分镜请标注说话角色，便于后续配音对应。"
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

    Each cell carries its number and a few-word caption of what it shows (「1 黄昏街道 |
    青年走路」), so the sheet can be read as a shot list at a glance. The tone prefixes and
    `shot_prompt` are what keep those captions out of the rendered frames.
    """
    numbered = "\n".join(f"{index}. {shot.strip()}" for index, shot in enumerate(shots, start=1) if shot.strip())
    parts = [
        f"为短剧《{episode_title.strip()}》绘制一张分镜基调总览图。",
        "把下列分镜按顺序排成网格缩略图，每格画出该分镜的构图与氛围。"
        "每格左上角用清晰易读的小字标注分镜序号和一句不超过十个字的画面概述，"
        "格式如「1 黄昏街道 | 青年走路」，概述从该分镜内容提炼，写地点或状态加人物动作。",
        "要求：所有格子共用同一套光线、色调、材质与渲染风格；"
        "同一人物在每一格里都是同一张脸、同一发型与同一套服装；"
        "发生在同一地点的格子保持相同的空间布局、陈设与主光方向，相邻格子的景别要有变化；"
        "除每格左上角的序号与画面概述外，不要出现字幕、水印或其他说明文字。",
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
    reference_count: int = 0,
) -> str:
    """One full-resolution frame, told what the references it actually carries are for.

    The reference images do the heavy lifting; this names their job, because a model
    handed several unlabelled references will happily average them. It describes them by
    count and by the `图N` numbers the shot text was compiled to — not as a fixed
    "tone, cast, prop, previous frame" sequence. A shot ships only the references its own
    prefixes and mentions select, so that sequence was usually untrue, and a model told
    the first image is the tone sheet when it is a character sheet draws the wrong thing.
    With none, saying so stops the model from inventing a reference to stay faithful to.

    The instruction against text is load-bearing rather than cosmetic: the cast and prop
    sheets print names and setting notes next to the drawings, and without this the model
    copies those captions straight into the rendered shot.
    """
    if reference_count > 0:
        reference_lines = [
            f"本次随附 {reference_count} 张参考图，分镜内容里的「图1」「图2」…按顺序对应它们并写明了各自的用途："
            "基调图决定光线、色调与渲染风格，角色与道具设定图决定人物长相、服饰与道具外观，"
            "其他分镜的成图决定场景与镜头的连续性。请严格沿用，不要重新设计人物或场景。",
            "重要：参考图上的角色名、道具名、简介、序号与设定文字只是给你看的说明，"
            "成片画面里绝对不能出现任何文字、标注、信息栏、字幕或水印。",
        ]
    else:
        reference_lines = [
            "本次没有参考图：人物的长相、服饰与场景完全依据下面的文字描述绘制，描述里的每一处外观细节都要画准。",
            "成片画面里绝对不能出现任何文字、标注、信息栏、字幕或水印。",
        ]
    parts = [
        f"为短剧《{episode_title.strip()}》绘制第 {order}/{total} 个分镜的成片画面。",
        *reference_lines,
        "只画这一个分镜，单幅完整画面，不要拼图、不要网格。",
        IMAGE_QUALITY_DIRECTIVE,
        f"分镜内容：{shot_text.strip()}",
        f"整体风格：{style_prompt.strip()}。" if style_prompt.strip() else "",
        f"避免出现：{negative_prompt.strip()}。" if negative_prompt.strip() else "",
    ]
    return "\n".join(part for part in parts if part)
