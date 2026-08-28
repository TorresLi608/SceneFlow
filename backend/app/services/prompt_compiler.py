"""Compile editor @mentions into provider-native positional media references."""

from __future__ import annotations

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


def compile_prompt(
    prompt: str,
    *,
    provider: str,
    model: str,
    references: list[dict[str, Any]] | None = None,
    dialogue: str = "",
    image_offset: int = 0,
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
        if kind in VIDEO_KINDS:
            video_index += 1
            index, placeholder, media_type = video_index, VIDEO_PLACEHOLDER.format(index=video_index), "reference_video"
        elif kind in AUDIO_KINDS:
            audio_index += 1
            index, placeholder, media_type = audio_index, AUDIO_PLACEHOLDER.format(index=audio_index), "reference_audio"
        else:
            image_index += 1
            index, placeholder, media_type = image_index, IMAGE_PLACEHOLDER.format(index=image_index), "reference_image"
        if label:
            replacements[f"@{label}"] = placeholder
        media.append({"type": media_type, "index": index, "kind": kind, "id": ref.get("id"), "label": label})

    compiled = str(prompt or "")
    # Longest first: `@小满` is a prefix of `@小满的房间`, and replacing the short one
    # first would leave `图1的房间` pointing at the wrong reference.
    for source in sorted(replacements, key=len, reverse=True):
        compiled = compiled.replace(source, replacements[source])
    if dialogue.strip():
        compiled = f"{compiled}\n{DIALOGUE_TEMPLATE.format(dialogue=dialogue.strip())}"
    return {
        "prompt": compiled.strip(),
        "media": media,
        "provider": provider,
        "model": model,
        "replacements": replacements,
    }
