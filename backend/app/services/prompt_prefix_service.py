"""Prefix prompts — the reusable preamble that sits above a shot's own prompt.

A shot's `visual_prompt` says what this frame shows. It says nothing about how the frame
relates to the episode around it, and that context is identical for every shot in the
episode — so writing it into each shot's own prompt meant retyping the same paragraph
twenty times and losing it the moment the breakdown was re-run.

A prefix is that paragraph, stored beside the prompt rather than inside it: an ordered
list of `{id, name, prompt, references}` items concatenated ahead of the shot's own text
at compile time. Two lists per shot, one for the still and one for the motion prompt,
because the two prompts describe different things and a preamble useful to one is usually
noise to the other.

The `@素材` mentions inside a prefix are *not* free: they resolve through the same
`resolve_generation_references` as the shot's own mentions and occupy the same provider
reference slots, so `combined_references` folds both lists into one deduplicated,
prefix-first order — which is also the order `compile_prompt` numbers `图1`, `图2`… in.
"""

from __future__ import annotations

import json
from typing import Any

from app.services.reference_service import REFERENCE_KINDS


# Marks the prefix this module writes for the episode's tone sheet. Regenerating the
# anchor replaces the item carrying this source rather than appending a second copy, and
# the editor's quick-preset button reproduces it after a user deletes one.
TONE_SOURCE = "tone"
TONE_PREFIX_NAME = "基调图"

# A prefix list is a preamble, not a script: the cap keeps one shot's payload bounded
# without ever being reachable by hand.
MAX_PREFIXES = 8


def stored_prompt_prefixes(value: str | None) -> list[dict[str, Any]]:
    """Parse a stored prefix column, dropping anything malformed.

    Lenient in the same way as `stored_generation_references`: a prefix that cannot be
    read costs the shot its preamble, while raising would cost the shot its render.
    """
    try:
        items = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(items, list):
        return []
    prefixes: list[dict[str, Any]] = []
    for item in items[:MAX_PREFIXES]:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("id") or "").strip()
        prompt = str(item.get("prompt") or "")
        if not identifier:
            continue
        references = [
            {"kind": str(reference.get("kind")), "id": str(reference.get("id"))}
            for reference in (item.get("references") or [])
            if isinstance(reference, dict)
            and reference.get("kind") in REFERENCE_KINDS
            and str(reference.get("id") or "").strip()
        ]
        prefixes.append(
            {
                "id": identifier,
                "name": str(item.get("name") or "").strip(),
                "prompt": prompt,
                "references": references,
                "source": str(item.get("source") or "").strip(),
            }
        )
    return prefixes


def dump_prompt_prefixes(items: list[dict[str, Any]]) -> str:
    return json.dumps(items[:MAX_PREFIXES], ensure_ascii=False, separators=(",", ":"))


def prefix_reference_pairs(prefixes: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [
        (str(reference["kind"]), str(reference["id"]))
        for prefix in prefixes
        for reference in prefix.get("references") or []
    ]


def combined_references(
    prefixes: list[dict[str, Any]],
    own: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Every asset the compiled prompt can talk about, prefix-first and deduplicated.

    Order is the contract: `compile_prompt` numbers references by position, so the prefixes
    have to come first here exactly as their text comes first in `combined_prompt`. An
    asset mentioned in both a prefix and the shot's own prompt is one reference with one
    number, not two slots spent on the same image.
    """
    seen: set[tuple[str, str]] = set()
    combined: list[tuple[str, str]] = []
    for pair in [*prefix_reference_pairs(prefixes), *own]:
        if pair in seen:
            continue
        seen.add(pair)
        combined.append(pair)
    return combined


def combined_prompt(prefixes: list[dict[str, Any]], prompt: str) -> str:
    """The prefix bodies, in order, above the shot's own text."""
    parts = [str(prefix.get("prompt") or "").strip() for prefix in prefixes]
    parts.append(str(prompt or "").strip())
    return "\n".join(part for part in parts if part)


# The two prefix lists get different tone wording. `image` is the still render, `video`
# the motion render; anything else is rejected rather than silently given the still text.
TONE_PREFIX_MEDIA = ("image", "video")


def tone_prefix_prompt(tone_label: str, order: int, total: int, *, media: str = "image") -> str:
    """What a shot is told about the episode's tone sheet, worded for the render it precedes.

    The sheet is a numbered grid of every shot in one sampling, so a still can be pointed at
    *its own* cell and at the cells on either side — which is the whole reason the anchor is
    generated as one image. The closing sentence is load-bearing for the same reason
    `shot_prompt`'s is: the grid carries cell numbers, and without being told otherwise the
    model draws them into the frame.

    The motion render must not get the still wording. Told "this is shot N of M, use cell N
    and the cells beside it", a video model reads the grid as a shot list to play through:
    it opens on the first cell, or cuts the clip into one segment per cell. So the video
    text demotes the sheet to a look reference only, names the cell for its mood alone, and
    spells out the single continuous take the grid keeps tempting it away from. It also
    says the sheet is not the first frame — the sheet is the first image the request
    carries, and an image-to-video model treats the first image as the opening frame unless
    told otherwise.
    """
    if media not in TONE_PREFIX_MEDIA:
        raise ValueError(f"unknown tone prefix media: {media!r}")
    if media == "video":
        return (
            f"整集的基调图 @{tone_label} 只用来统一光线、色调、材质与渲染风格，本镜的氛围以其中第 {order} 格为准。"
            "基调图不是分镜脚本，也不是首帧：不要从基调图的第一格起逐格播放，不要按格子顺序切换或拼接多个片段，"
            "不要复现其他格子的内容。"
            "整段视频只拍本镜这一个连续镜头：同一场景、同一组人物，一镜到底，不分屏、不分段、不在镜头内切换画面；"
            "画面中不要出现网格、格子边框、分镜序号或任何文字。"
        )
    neighbours = "、".join(
        part
        for part in (
            f"第 {order - 1} 格" if order > 1 else "",
            f"第 {order + 1} 格" if order < total else "",
        )
        if part
    )
    context = f"并参考{neighbours}，保持与前后镜头的剧情与视觉连贯；" if neighbours else ""
    return (
        f"这是整集的基调图 @{tone_label}，其中第 {order} 格对应本镜（全集共 {total} 镜）。"
        f"请以第 {order} 格的构图与氛围为准，{context}"
        "沿用基调图整体的光线、色调、材质与渲染风格，不要重新设计人物或场景。"
        "只画本镜这一幅完整画面，不要把多个格子拼在一起；"
        "基调图只是参考，成片里不要出现网格、格子边框、分镜序号或任何文字。"
    )


def tone_prefix_item(
    episode_id: str, tone_label: str, order: int, total: int, *, media: str = "image"
) -> dict[str, Any]:
    """The prefix the tone sheet writes into every shot once it lands.

    `id` is derived rather than random so re-running the anchor rewrites the same item in
    place — a stable id is what keeps a regenerate from stacking a second copy on a shot
    the user has already edited around. The id is the same in both lists: they are stored
    apart, and the editor already re-keys a preset it adds beside an existing item.
    """
    return {
        "id": f"prefix-tone-{order}",
        "name": TONE_PREFIX_NAME,
        "prompt": tone_prefix_prompt(tone_label, order, total, media=media),
        # The `@` label above is only text until it resolves; the reference is what actually
        # ships the image, and it is what spends the slot.
        "references": [{"kind": "tone", "id": episode_id}],
        "source": TONE_SOURCE,
    }


def with_tone_prefix(
    stored: str | None,
    *,
    episode_id: str,
    tone_label: str,
    order: int,
    total: int,
    media: str = "image",
) -> str:
    """`stored` with the tone prefix inserted, replacing any earlier one.

    Prepended rather than appended: the tone sheet decides the look every other instruction
    is then qualified against, so it reads first for the same reason it is generated first.
    """
    item = tone_prefix_item(episode_id, tone_label, order, total, media=media)
    existing = [prefix for prefix in stored_prompt_prefixes(stored) if prefix.get("source") != TONE_SOURCE]
    return dump_prompt_prefixes([item, *existing])


# ---- The other quick-fill presets ----------------------------------------------------------
#
# Inserted by hand from the editor's bar and never rewritten afterwards, unlike the tone
# item; their `source` only records where the text came from, so a later refresh could
# find them. They carry the episode's own words to the model: the script, this shot's line,
# or every shot in order.
SCRIPT_SOURCE = "script"
SHOT_SOURCE = "shot"
SHOT_LIST_SOURCE = "shots"
SCRIPT_PREFIX_NAME = "整篇原文"
SHOT_PREFIX_NAME = "本镜原文"
SHOT_LIST_PREFIX_NAME = "整集分镜"

# Mirrors the `prompt` cap on `PromptPrefixRequest`, because a preset the editor cannot
# save back is worse than one cut short. The test suite checks the two stay equal.
MAX_PREFIX_PROMPT_CHARS = 4000
TRUNCATION_NOTE = "……（内容过长，已截断）"

_CN_DIGITS = "零一二三四五六七八九"


def cn_number(value: int) -> str:
    """1 → 一, 10 → 十, 12 → 十二, 21 → 二十一. Digits past 99, which no episode reaches."""
    if not 1 <= value <= 99:
        return str(value)
    tens, ones = divmod(value, 10)
    if tens == 0:
        return _CN_DIGITS[ones]
    head = "十" if tens == 1 else f"{_CN_DIGITS[tens]}十"
    return head if ones == 0 else f"{head}{_CN_DIGITS[ones]}"


def _fit(text: str, limit: int) -> str:
    """`text` within `limit` characters, ending in the truncation note when it was cut."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(TRUNCATION_NOTE))].rstrip() + TRUNCATION_NOTE


def script_prefix_item(source_text: str) -> dict[str, Any] | None:
    """The episode's script above a shot, so the model knows the story the shot sits in.

    Framed as reading material rather than as the thing to draw: handed a pasted script
    with no framing, a model prints it as subtitles or narrates it over the clip.
    """
    body = str(source_text or "").strip()
    if not body:
        return None
    header = (
        "以下是本集的小说原文，只用于理解整集的剧情、人物关系与情绪走向；"
        "画面与动作以本镜的提示词为准，不要把原文当作字幕、旁白或文字画进画面。\n原文：\n"
    )
    return {
        "id": "prefix-script",
        "name": SCRIPT_PREFIX_NAME,
        "prompt": header + _fit(body, MAX_PREFIX_PROMPT_CHARS - len(header)),
        "references": [],
        "source": SCRIPT_SOURCE,
    }


def shot_prefix_item(narration: str, order: int) -> dict[str, Any] | None:
    """This shot's own line from the breakdown — what happens in it, in the script's words."""
    body = str(narration or "").strip()
    if not body:
        return None
    header = (
        f"以下是本镜（分镜 {order}）对应的原文，只用于理解这一镜的剧情与情绪；"
        "画面与动作以本镜的提示词为准，不要把原文当作字幕或文字画进画面。\n本镜原文：\n"
    )
    return {
        "id": f"prefix-shot-{order}",
        "name": SHOT_PREFIX_NAME,
        "prompt": header + _fit(body, MAX_PREFIX_PROMPT_CHARS - len(header)),
        "references": [],
        "source": SHOT_SOURCE,
    }


def shot_list_prefix_item(
    shots: list[dict[str, Any]],
    order: int,
    *,
    media: str,
    episode_id: str = "",
    tone_label: str = "",
) -> dict[str, Any] | None:
    """Every shot of the episode in order, above one of them.

    `shots` are `{order, text}` with the text already chosen for `media` — the frame prompt
    under the still list, the motion prompt under the video list — so the model can place
    this shot in the sequence. Which is exactly what a video model tries to *play*, so the
    closing line pins the render to this one shot. The tone sheet is bound above the list
    when the episode has one, the way the storyboard is normally read against it.
    """
    if media not in TONE_PREFIX_MEDIA:
        raise ValueError(f"unknown prefix media: {media!r}")
    entries = [
        (int(shot.get("order") or index), str(shot.get("text") or "").strip())
        for index, shot in enumerate(shots, start=1)
    ]
    entries = [(shot_order, text) for shot_order, text in entries if text]
    if not entries:
        return None
    references: list[dict[str, str]] = []
    head: list[str] = []
    if tone_label and episode_id:
        head.append(f"素材绑定：故事板分镜基调图 @{tone_label}")
        references.append({"kind": "tone", "id": episode_id})
    kind_label = "视频" if media == "video" else "画面"
    head.append(f"以下是整集分镜的{kind_label}提示词，按顺序列出，只用于理解前后剧情与镜头衔接：")
    if media == "video":
        foot = f"本镜是分镜{cn_number(order)}；只拍本镜这一个连续镜头，不要把其他分镜的内容拼进来，也不要按顺序播放多个分镜。"
    else:
        foot = f"本镜是分镜{cn_number(order)}；只画本镜这一幅画面，不要把其他分镜拼进同一张图。"
    # The list is trimmed from the end rather than the whole text cut mid-line: a shot that
    # does not fit is dropped, and the closing instruction always survives.
    budget = MAX_PREFIX_PROMPT_CHARS - sum(len(line) + 1 for line in head) - len(foot) - len(TRUNCATION_NOTE) - 1
    blocks: list[str] = []
    for shot_order, text in entries:
        block = f"分镜{cn_number(shot_order)}：\n{text}"
        if len(block) + 1 > budget:
            blocks.append(TRUNCATION_NOTE)
            break
        blocks.append(block)
        budget -= len(block) + 1
    return {
        "id": f"prefix-shots-{media}",
        "name": SHOT_LIST_PREFIX_NAME,
        "prompt": "\n".join([*head, *blocks, foot]),
        "references": references,
        "source": SHOT_LIST_SOURCE,
    }
