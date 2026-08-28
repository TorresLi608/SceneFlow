from __future__ import annotations

from app.services.prompt_compiler import compile_prompt


def test_labels_become_positional_references() -> None:
    result = compile_prompt(
        "@小满走进@房间",
        provider="qwen",
        model="wan3.0-video",
        references=[{"kind": "character", "id": "c1", "label": "小满"}, {"kind": "prop", "id": "p1", "label": "房间"}],
    )
    assert result["prompt"] == "图1走进图2"
    assert [item["type"] for item in result["media"]] == ["reference_image", "reference_image"]


def test_each_media_kind_counts_separately() -> None:
    result = compile_prompt(
        "@小满 在 @片段 里，配上 @旁白",
        provider="qwen",
        model="wan3.0-video",
        references=[
            {"kind": "character", "id": "c1", "label": "小满"},
            {"kind": "scenevideo", "id": "v1", "label": "片段"},
            {"kind": "voice", "id": "a1", "label": "旁白"},
        ],
    )
    assert result["prompt"] == "图1 在 视频1 里，配上 音频1"
    assert [item["index"] for item in result["media"]] == [1, 1, 1]


def test_image_offset_accounts_for_the_prepended_storyboard_frame() -> None:
    """The render puts the shot's own frame in slot 1 whenever the model takes images.

    Numbering the user's first selection `图1` would point the model at the frame it
    already has instead of the reference the user picked.
    """
    references = [{"kind": "character", "id": "c1", "label": "小满"}]
    assert compile_prompt("@小满 回头", provider="qwen", model="wan3.0-video", references=references)["prompt"] == "图1 回头"
    shifted = compile_prompt("@小满 回头", provider="qwen", model="wan3.0-video", references=references, image_offset=1)
    assert shifted["prompt"] == "图2 回头"
    assert shifted["media"][0]["index"] == 2


def test_longer_labels_win_over_their_own_prefixes() -> None:
    """`@小满` is a prefix of `@小满的房间`; replacing it first corrupts the longer one."""
    result = compile_prompt(
        "@小满 走进 @小满的房间",
        provider="qwen",
        model="wan3.0-video",
        references=[
            {"kind": "character", "id": "c1", "label": "小满"},
            {"kind": "prop", "id": "p1", "label": "小满的房间"},
        ],
    )
    assert result["prompt"] == "图1 走进 图2"


def test_deleted_label_still_ships_its_reference() -> None:
    """A saved shot whose text lost the mention must stay renderable, not lose the image."""
    result = compile_prompt(
        "一个空镜头",
        provider="qwen",
        model="wan3.0-video",
        references=[{"kind": "character", "id": "c1", "label": "小满"}],
    )
    assert result["prompt"] == "一个空镜头"
    assert len(result["media"]) == 1


def test_dialogue_is_appended_once() -> None:
    result = compile_prompt("她转身", provider="doubao", model="doubao-seedance-2.5", dialogue="  你还记得吗  ")
    assert result["prompt"] == "她转身\n台词：“你还记得吗”"
    assert compile_prompt("她转身", provider="doubao", model="doubao-seedance-2.5", dialogue="   ")["prompt"] == "她转身"


def test_doubao_uses_angle_bracket_media_placeholders_with_label() -> None:
    result = compile_prompt(
        "@韩立青年回头",
        provider="doubao",
        model="doubao-seedance-2-5-260628",
        references=[{"kind": "character", "id": "c1", "label": "韩立青年"}],
        dialogue="别走",
        speaker_name="韩立青年",
    )
    assert result["prompt"] == "<图片1> 韩立青年回头\n角色“韩立青年”台词：“别走”"


def test_existing_provider_markers_are_normalized() -> None:
    result = compile_prompt(
        "图3回头",
        provider="doubao",
        model="doubao-seedance-2-5-260628",
        references=[
            {"kind": "character", "id": "c1", "label": "小满"},
            {"kind": "prop", "id": "p1", "label": "房间"},
            {"kind": "character", "id": "c2", "label": "韩立青年"},
        ],
    )
    assert result["prompt"] == "<图片3> 韩立青年回头"


def test_character_state_reference_resolves_parent_label() -> None:
    """characterState preview must include its parent character name, not 500."""
    # The database resolver is covered by the API suite; this assertion documents the
    # label contract consumed by the compiler.
    result = compile_prompt(
        "@韩立 · 青年",
        provider="doubao",
        model="doubao-seedance-2.5",
        references=[{"kind": "characterState", "id": "cstate", "label": "韩立 · 青年"}],
    )
    assert result["prompt"] == "<图片1> 韩立青年"
    assert compile_prompt(
        "@韩立青年",
        provider="doubao",
        model="doubao-seedance-2.5",
        references=[{"kind": "characterState", "id": "cstate", "label": "韩立 · 青年"}],
    )["prompt"] == "<图片1> 韩立青年"


if __name__ == "__main__":
    test_labels_become_positional_references()
    test_each_media_kind_counts_separately()
    test_image_offset_accounts_for_the_prepended_storyboard_frame()
    test_longer_labels_win_over_their_own_prefixes()
    test_deleted_label_still_ships_its_reference()
    test_dialogue_is_appended_once()
    test_doubao_uses_angle_bracket_media_placeholders_with_label()
    test_existing_provider_markers_are_normalized()
    test_character_state_reference_resolves_parent_label()
