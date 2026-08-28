"""Compile editor @mentions into provider-native positional media references."""

from __future__ import annotations

import re
from typing import Any


# The editor writes human labels; providers only count. `图1` is the first image the
# request actually carries, which is not always the first one the user picked — see
# `image_offset`.
IMAGE_PLACEHOLDER = "图{index}"
VIDEO_PLACEHOLDER = "视频{index}"
AUDIO_PLACEHOLDER = "音频{index}"
DIALOGUE_TEMPLATE = "台词：“{dialogue}”"

VIDEO_KINDS = {"video", "scenevideo", "reference_video"}
AUDIO_KINDS = {"audio", "voice", "reference_audio"}


def _placeholder_aliases(kind: str, index: int) -> tuple[str, ...]:
    if kind in VIDEO_KINDS:
        return (f"视频{index}", f"<视频{index}>", f"Video {index}", f"<Video {index}>")
    if kind in AUDIO_KINDS:
        return (f"音频{index}", f"<音频{index}>", f"Audio {index}", f"<Audio {index}>")
    return (
        f"图{index}", f"图片{index}", f"<图{index}>", f"<图片{index}>",
        f"Image {index}", f"<Image {index}>",
    )


def compile_prompt(
    prompt: str,
    *,
    provider: str,
    model: str,
    references: list[dict[str, Any]] | None = None,
    dialogue: str = "",
    image_offset: int = 0,
    speaker_name: str = "",
) -> dict[str, Any]:
    """Return the prompt with `@label` rewritten to the provider's positional reference.

    `image_offset` is how many images the render prepends before the user's own — the
    automatic first frame is one — because the number in the prompt has to match the
    slot in the request, not the row in the editor.

    A label the user deleted from the text simply goes unreferenced: the media still
    ships, so the model keeps the reference, and a saved shot stays renderable.
    """
    refs = references or []
    image_index = image_offset
    video_index = audio_index = 0
    replacements: dict[str, str] = {}
    media: list[dict[str, Any]] = []
    for ref in refs:
        kind = str(ref.get("kind") or ref.get("media") or "image").lower()
        label = str(ref.get("label") or ref.get("name") or "").strip()
        # The editor keeps character states readable as `角色 · 状态`; provider
        # prompts use the compact asset name the model guide examples expect.
        provider_label = label.replace(" · ", "") if kind == "characterstate" else label
        if kind in VIDEO_KINDS:
            video_index += 1
            index = video_index
            placeholder = f"<视频{index}>" if provider == "doubao" else VIDEO_PLACEHOLDER.format(index=index)
            media_type = "reference_video"
        elif kind in AUDIO_KINDS:
            audio_index += 1
            index = audio_index
            placeholder = f"<音频{index}>" if provider == "doubao" else AUDIO_PLACEHOLDER.format(index=index)
            media_type = "reference_audio"
        else:
            image_index += 1
            index = image_index
            if provider == "doubao":
                placeholder = f"<图片{index}>"
            else:
                placeholder = IMAGE_PLACEHOLDER.format(index=index)
            media_type = "reference_image"
        if label:
            replacements[f"@{label}"] = f"{placeholder} {provider_label}" if provider == "doubao" else placeholder
            replacements.setdefault(f"@{label.replace(' · ', ' ')}", replacements[f"@{label}"])
            if provider_label != label:
                replacements.setdefault(f"@{provider_label}", replacements[f"@{label}"])
        for alias in _placeholder_aliases(kind, index):
            replacements.setdefault(alias, f"{placeholder} {provider_label}".strip() if provider == "doubao" and label else placeholder)
        media.append({"type": media_type, "index": index, "kind": kind, "id": ref.get("id"), "label": label})

    compiled = str(prompt or "")
    # Longest first: `@小满` is a prefix of `@小满的房间`, and numeric tokens need a
    # digit boundary so `图1` never corrupts `图10`.
    sources = sorted(replacements, key=len, reverse=True)
    if sources:
        pattern = re.compile("|".join(re.escape(source) for source in sources) + r"(?!\d)")
        compiled = pattern.sub(lambda match: replacements[match.group(0)], compiled)
    if dialogue.strip():
        prefix = f"角色“{speaker_name.strip()}”" if speaker_name.strip() else ""
        compiled = f"{compiled}\n{prefix}{DIALOGUE_TEMPLATE.format(dialogue=dialogue.strip())}"
    return {
        "prompt": compiled.strip(),
        "media": media,
        "provider": provider,
        "model": model,
        "replacements": replacements,
    }
