# BUG-20261116-production-prompt-coherence：生剧提示词与衔接逻辑导致画面不连贯

- 首次记录：2026-11-16
- 最近更新：2026-11-16
- 状态：已修改，离线自检通过；真实模型出图 / 出片效果未验证
- 检索词：AI 生剧、漫剧、分镜拆解、BREAKDOWN_SYSTEM、shot_prompt、参考图依次是、连续性约束、上一镜提示词、承接块、转场、硬切、台词、时长、durationSeconds、cinematic anime、optimize_script、parse_script、画面质量

## 现象与复现

用户反馈生剧生成的视频逻辑连贯性和成片质量不足（分镜、场景、台词、图片质量）。未调用付费模型复现成片效果；以下问题均由阅读提示词拼装代码并对照实际请求内容确认。

1. **成图模板描述了并不存在的参考图。** `shot_prompt` 固定写"参考图依次是：整集基调图、角色设定三面图、道具设定图、上一个分镜的成图"，但 `run_storyboard` 只发送该分镜自己的前缀与 @引用（见 [data-flow §5](../architecture/data-flow.md#5-shots--tone-sheet--storyboard-frames)），可能顺序不同，也可能一张都没有。
2. **视频的连续性约束引用了错误的内容。** 上一镜提示词被整段附上，其中的 `分镜X：` 序号和 `【承接块】` 描述的是再上一镜的状态。
3. **硬切被当作指令发给视频模型。** `转场：硬切` 原样进入提示词，模型容易在单个片段内部做切换。
4. **片段可能短于台词。** 时长完全采用模型估计，长台词常被低估，后续没有任何环节能补救。
5. **剧本解析 / 润色写死了 anime。** `parse_script`、`optimize_script` 及两处兜底画面提示词含 "cinematic anime" / "anime storyboard frame"，与写实、3D 等项目风格冲突（[项目画面风格](../design/feature-visual-style.md) 只清理了 `build_image_prompt`）。
6. **拆解提示词把每个分镜当作独立画面来写。** 没有场次 / 空间 / 光线的统一设计，没有轴线、景别递进、动作承接等剪辑规则，没有台词节奏与提示词结构要求，也没有声明顶层 JSON 结构。
7. 成图与成片提示词缺少明确的完成度要求与常见缺陷清单；视频分镜补充（`target: video`）看不到各分镜的台词与景别。

## 根因与定位

- 1：模板沿用了早期"自动注入基调图与上一镜成图"的描述，注入逻辑移除后文案未同步（[prompt_service.py](../../backend/app/services/prompt_service.py) `shot_prompt`、[storyboard_service.py](../../backend/app/services/storyboard_service.py) `_generate_shot`）。
- 2、3：[generation_service.py](../../backend/app/services/generation_service.py) `_generate_scene_video` 直接拼接原始字段。
- 4：[episodes.py](../../backend/app/api/v1/episodes.py) `_shot_values` 无下限保护。
- 5：[router.py](../../backend/app/llms/router.py) 内联的英文提示词。
- 6、7：提示词设计不足，属于质量问题而非单点错误；是否足以达到期望的成片效果需真实模型验证。

## 修复与影响

提示词文案与节奏规则统一放在 [prompt_service.py](../../backend/app/services/prompt_service.py)，对应测试为 [test_prompt_service.py](../../backend/tests/test_prompt_service.py)：

- `shot_prompt` 接收实际参考图数量，有参考图时说明"图N 按顺序对应"，没有时明确依文字绘制。未恢复任何隐式参考图注入。
- `video_continuity` 只引用上一镜自身的动作（去掉序号与承接块，截到 260 字）；`video_direction` 不再提及硬切，其他转场限定在开场瞬间，并在提示词缺少景别时补上；`dialogue_performance` 紧贴台词行给出口型与表演要求；末尾追加 `VIDEO_QUALITY_DIRECTIVE`。
- `shot_duration_seconds` 把模型估计抬高到说得完台词为止（约每秒 4.5 个汉字，最少 2 秒，最多 60 秒）；无台词的分镜保持原估计，0 仍表示未定。原位的视频补充使用已存的台词。
- 重写 `BREAKDOWN_SYSTEM`：先做场次、造型、节奏、镜头语言的整体设计再写分镜；台词逐字沿用剧本；画面 / 动态提示词有固定书写顺序并限制在 60–130 字（回复上限 8192 token，最多 40 个分镜）。JSON 字段、`分镜X：` 与 `【】` 约定不变，解析器未改。
- `SCRIPT_POLISH_SYSTEM`、`SCRIPT_PARSE_*`、`fallback_frame_prompt` 不再指定画面风格；润色提示词按短剧要求打磨结构与台词。
- 成图模板、基调图、角色 / 道具设定图、封面、旧版 `build_image_prompt` 与提示词优化器（image / video）补充完成度与一致性要求。
- 影响范围：之后的拆解、成图、成片与提示词优化；已生成的媒体和已保存的分镜提示词不会改变，旧分镜需重新拆解才会按新规则书写。接口、数据库与前端均未改动。发给视频模型的提示词变长，是否触及个别提供商的长度上限未实测。
- 长期规则见 [data-flow §3 / §5 / §6](../architecture/data-flow.md#3-script--shots)。

## 验证

2026-11-16 实际执行（`backend` 目录，临时数据库与媒体目录，供应商全部为桩）：

```bash
check_dir=$(mktemp -d /tmp/sceneflow-full-check.XXXXXX)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh $(rg --files tests -g 'test_*.py' | sed 's#^tests/##; s#\.py$##' | sort)
```

- 50 个文件中 49 个通过，含新增的 `test_prompt_service` 及 `test_breakdown_api`、`test_storyboard_api`、`test_video_service`、`test_project_visual_style`、`test_prompt_prefixes`、`test_prompt_optimization`。成图模板改为按参考图数量描述后，又单独重跑了相关 7 个文件，全部通过。
- `test_episode_migration` 失败，现象与 [BUG-20260920-episode-migration-test-scenes](2026-09-20-episode-migration-test-scenes.md) 一致，与本次改动无关；未在干净工作区复跑对照。
- **未验证**：没有调用任何真实文本、图片或视频模型，因此"连贯性与成片质量是否提升"没有成片证据，只验证了发给模型的提示词内容符合设计。前端检查未执行（无前端改动）。

## 历史与关联

- 2026-11-16：首次记录并修改。尚未提交，无 commit / PR。
- 相关：[项目画面风格](../design/feature-visual-style.md)、[视频首帧默认填充](2026-09-09-video-first-frame-default.md)（显式移除隐式锚点的先例）、[分镜拆解 JSON 兼容](2026-09-01-breakdown-invalid-json.md)（截断风险）。
