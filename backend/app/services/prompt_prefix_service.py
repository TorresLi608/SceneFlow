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


def tone_prefix_prompt(tone_label: str, order: int, total: int) -> str:
    """What a shot is told about the episode's tone sheet.

    The sheet is a numbered grid of every shot in one sampling, so a shot can be pointed at
    *its own* cell and at the cells on either side — which is the whole reason the anchor is
    generated as one image. The closing sentence is load-bearing for the same reason
    `shot_prompt`'s is: the grid carries cell numbers, and without being told otherwise the
    model draws them into the frame.
    """
    neighbours = "、".join(
        part
        for part in (
            f"第 {order - 1} 格" if order > 1 else "",
            f"第 {order + 1} 格" if order < total else "",
        )
        if part
    )
    context = f"并结合{neighbours}的画面，保持与前后镜头的剧情与视觉连贯；" if neighbours else ""
    return (
        f"这是整集的基调图 @{tone_label}。本镜是分镜 {order}（全集共 {total} 镜）。"
        f"请以基调图中第 {order} 格的构图与氛围为准，{context}"
        "并沿用基调图整体的光线、色调、材质与渲染风格，不要重新设计人物或场景。"
        "基调图只是参考，成片里不要出现网格、格子边框、分镜序号或任何文字。"
    )


def tone_prefix_item(episode_id: str, tone_label: str, order: int, total: int) -> dict[str, Any]:
    """The prefix the tone sheet writes into every shot once it lands.

    `id` is derived rather than random so re-running the anchor rewrites the same item in
    place — a stable id is what keeps a regenerate from stacking a second copy on a shot
    the user has already edited around.
    """
    return {
        "id": f"prefix-tone-{order}",
        "name": TONE_PREFIX_NAME,
        "prompt": tone_prefix_prompt(tone_label, order, total),
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
) -> str:
    """`stored` with the tone prefix inserted, replacing any earlier one.

    Prepended rather than appended: the tone sheet decides the look every other instruction
    is then qualified against, so it reads first for the same reason it is generated first.
    """
    item = tone_prefix_item(episode_id, tone_label, order, total)
    existing = [prefix for prefix in stored_prompt_prefixes(stored) if prefix.get("source") != TONE_SOURCE]
    return dump_prompt_prefixes([item, *existing])
