"""Wording and pacing rules that decide whether consecutive shots cut together.

Offline: pure helpers, plus one shot rendered with every provider and store stubbed so
the prompt the video model would receive can be read back.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import breakdown_service
from app.services.generation_service import _generate_scene_video, build_image_prompt
from app.services.prompt_service import (
    BREAKDOWN_SYSTEM,
    IMAGE_QUALITY_DIRECTIVE,
    SCRIPT_PARSE_INSTRUCTION,
    SCRIPT_POLISH_SYSTEM,
    VIDEO_QUALITY_DIRECTIVE,
    dialogue_seconds,
    fallback_frame_prompt,
    shot_action_text,
    shot_duration_seconds,
    shot_prompt,
    tone_sheet_prompt,
    video_continuity,
    video_direction,
)
from app.services.video_service import VideoResult


def test_breakdown_system_keeps_the_contract_the_parser_and_editor_rely_on() -> None:
    # Every field `models.breakdown_script` reads, and the top-level key it looks for.
    for field in (
        '{"shots":[', "narration", "dialogue", "speaker", "visualPrompt", "shotType",
        "cameraMove", "transition", "durationSeconds", "videoPrompt",
    ):
        assert field in BREAKDOWN_SYSTEM
    # The label and carry-over conventions `with_shot_label` / `shot_action_text` parse.
    assert "「分镜X：」" in BREAKDOWN_SYSTEM and "【】承接块" in BREAKDOWN_SYSTEM
    # The script is the author's: the breakdown paces dialogue, it does not rewrite it.
    assert "逐字沿用剧本原文" in BREAKDOWN_SYSTEM and "不要编造剧本里没有的情节" in BREAKDOWN_SYSTEM
    # Both prompts are length-capped; the reply shares an 8192-token budget with 40 shots.
    assert "60 到 130 字" in BREAKDOWN_SYSTEM


def test_script_prompts_name_no_visual_style() -> None:
    """A hardcoded look used to contradict a realistic or 3D project's configured style."""
    for text in (SCRIPT_POLISH_SYSTEM, SCRIPT_PARSE_INSTRUCTION, fallback_frame_prompt("山门在雾里")):
        assert "anime" not in text.lower() and "动漫" not in text
    assert "optimizedScript" in SCRIPT_POLISH_SYSTEM and "tips" in SCRIPT_POLISH_SYSTEM


def test_carry_over_block_is_stripped_from_a_quoted_shot() -> None:
    assert shot_action_text("分镜 3：【承接上一镜，同一客厅】陆沉转身离开，近景") == "陆沉转身离开，近景"
    assert shot_action_text("分镜３：陆沉转身离开") == "陆沉转身离开"
    # A 【】 later in the text is content, not the opening carry-over block.
    assert shot_action_text("陆沉看向【遗嘱】，近景") == "陆沉看向【遗嘱】，近景"
    assert shot_action_text("") == ""


def test_a_shot_runs_long_enough_to_say_its_line() -> None:
    assert dialogue_seconds("") == 0 and dialogue_seconds("……") == 0
    assert dialogue_seconds("走！") == 2
    assert dialogue_seconds("I never said that.") == 2
    long_line = "你以为我不知道这三年你都背着我做了些什么吗？我只是一直在等你自己开口。"
    assert dialogue_seconds(long_line) == 8
    # A short estimate is raised; a generous one is kept; silence keeps "undecided".
    assert shot_duration_seconds(3, long_line) == 8
    assert shot_duration_seconds(6, "师父，我们到了。") == 6
    assert shot_duration_seconds(0, "") == 0
    assert shot_duration_seconds(0, "走！") == 2
    assert shot_duration_seconds(500, long_line) == 60


def test_video_direction_scopes_transitions_and_skips_hard_cuts() -> None:
    # A hard cut is the absence of an effect; naming it invites a cut inside the clip.
    assert video_direction("近景", "缓慢推镜", "硬切", "陆沉转身，近景") == "运镜：缓慢推镜"
    assert video_direction("", "", "cut", "陆沉转身") == ""
    line = video_direction("近景", "缓慢推镜", "叠化", "陆沉转身")
    assert line.startswith("景别：近景；运镜：缓慢推镜；开场转场：以叠化进入本镜")
    assert "只作用于开场瞬间" in line


def test_continuity_quotes_only_the_previous_shots_own_action() -> None:
    assert video_continuity("") == "" and video_continuity("分镜 2：【承接上一镜】") == ""
    text = video_continuity("分镜 2：【承接上一镜，男主从静止开始】陆沉向前迈一步，近景")
    assert text.endswith("上一镜内容（仅供承接，不要重演）：陆沉向前迈一步，近景")
    assert "分镜 2" not in text and "男主从静止开始" not in text
    assert len(video_continuity("动" * 2000)) < 400


def test_frame_templates_carry_the_quality_bar_and_consistency_rules() -> None:
    frame = shot_prompt("陆沉站在窗前", 2, 5, "第一集", "电影风格", "文字水印")
    assert IMAGE_QUALITY_DIRECTIVE in frame and "整体风格：电影风格。" in frame and "避免出现：文字水印。" in frame
    # The template describes the references the request really carries, never a fixed list.
    assert "本次没有参考图" in frame and "随附" not in frame and "上一个分镜的成图" not in frame
    with_references = shot_prompt("图1 陆沉站在窗前", 2, 5, "第一集", reference_count=3)
    assert "本次随附 3 张参考图" in with_references and "本次没有参考图" not in with_references
    assert "不能出现任何文字" in frame and "不能出现任何文字" in with_references
    sheet = tone_sheet_prompt("第一集", "剧本", ["陆沉站在窗前", "苏晚推门"])
    assert "同一张脸" in sheet and "主光方向" in sheet
    legacy = build_image_prompt({"narration": "少年抬头", "visual_prompt": "low angle"})
    assert "correct anatomy and hands" in legacy and "Visual direction: low angle." in legacy


def test_motion_pass_is_told_each_shots_line_and_size() -> None:
    episode = MagicMock(title="第一集", synopsis="")
    prompt = breakdown_service.build_user_prompt(
        episode=episode, script="剧本", target="video", characters=[], props=[],
        use_cast_sheet=False, use_prop_sheet=False,
        existing_shots=[
            {"narration": "对峙", "dialogue": "你骗我。", "shot_type": "近景", "visual_prompt": "分镜 1：陆沉皱眉"},
            {"narration": "沉默"},
        ],
    )
    assert "   台词：你骗我。" in prompt and "   景别：近景" in prompt
    assert "2. 剧情：沉默" in prompt and prompt.count("台词：") == 1
    assert "台词逐字沿用剧本原文" in prompt


def _render(scene: dict) -> str:
    config = {
        "provider": "qwen", "apiKey": "secret", "model": "wan2.7-i2v", "baseUrl": "https://relay.example.com/api/v1",
        "videoCapabilities": {
            "referenceImages": True, "maxReferenceImages": 1, "referenceImagesRequired": False,
            "referenceAudio": False, "aspectRatios": ["16:9"],
        },
    }
    options = {"quality": "720p", "aspectRatio": "16:9", "fps": None, "duration": 5, "promptExtend": False}
    generate = AsyncMock(return_value=VideoResult(b"mp4"))
    with (
        patch("app.services.generation_service.generate_video", new=generate),
        patch("app.services.generation_service.db", return_value=MagicMock()),
        patch("app.services.generation_service.require_model_balance"),
        patch("app.services.generation_service.record_usage"),
        patch("app.services.generation_service.store_artifact", return_value="projects/p/scene-2.mp4"),
        patch("app.services.generation_service.signed_url_for_stored", return_value="/api/files/video"),
        patch("app.services.generation_service.update_scene_row"),
        patch("app.services.generation_service.scene_event", new=AsyncMock()),
    ):
        assert asyncio.run(_generate_scene_video("p", scene, config, 1, options))
    return generate.call_args.kwargs["prompt"]


def test_the_video_model_receives_direction_performance_continuity_and_quality() -> None:
    prompt = _render({
        "id": "scene-2", "order_num": 2, "characters": [], "explicitVideoReferences": True,
        "video_prompt": "分镜 2：【承接上一镜结束姿态】陆沉向前迈一步，抓住苏晚左臂",
        "shot_type": "近景", "camera_move": "固定", "transition": "硬切",
        "dialogue": "你到底瞒了我什么？", "speaker": {"name": "陆沉"},
        "previous_video_prompt": "分镜 1：陆沉站定不动，右手缓缓握拳，全景",
        "style_prompt": "电影风格",
    })
    lines = prompt.split("\n")
    assert lines[0] == "分镜 2：【承接上一镜结束姿态】陆沉向前迈一步，抓住苏晚左臂"
    # Shot size and camera, but no instruction about a hard cut.
    assert lines[1] == "景别：近景；运镜：固定" and "转场" not in prompt
    # The performance note sits directly above the line it is about.
    assert lines[2].startswith("表演：角色“陆沉”说出下面这句台词")
    assert lines[3] == "角色“陆沉”台词：“你到底瞒了我什么？”"
    assert lines[4].endswith("上一镜内容（仅供承接，不要重演）：陆沉站定不动，右手缓缓握拳，全景")
    assert lines[5] == VIDEO_QUALITY_DIRECTIVE
    assert lines[6] == "整体画面风格：电影风格"

    # A silent first shot gets neither a performance note nor a continuity clause.
    silent = _render({
        "id": "scene-1", "order_num": 1, "characters": [], "explicitVideoReferences": True,
        "video_prompt": "分镜 1：雾中山门，全景", "shot_type": "全景", "transition": "淡入",
    })
    assert "表演：" not in silent and "连续性约束" not in silent
    assert "开场转场：以淡入进入本镜" in silent and "景别：" not in silent
    assert silent.endswith(VIDEO_QUALITY_DIRECTIVE)


if __name__ == "__main__":
    test_breakdown_system_keeps_the_contract_the_parser_and_editor_rely_on()
    test_script_prompts_name_no_visual_style()
    test_carry_over_block_is_stripped_from_a_quoted_shot()
    test_a_shot_runs_long_enough_to_say_its_line()
    test_video_direction_scopes_transitions_and_skips_hard_cuts()
    test_continuity_quotes_only_the_previous_shots_own_action()
    test_frame_templates_carry_the_quality_bar_and_consistency_rules()
    test_motion_pass_is_told_each_shots_line_and_size()
    test_the_video_model_receives_direction_performance_continuity_and_quality()
    print("prompt service checks passed")
