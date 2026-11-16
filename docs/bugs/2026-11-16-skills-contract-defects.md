# BUG-20261116-skills-contract-defects：生产技能骨架的协议缺陷

- 首次记录：2026-11-16
- 最近更新：2026-11-16
- 状态：已修复，离线自检通过；尚无真实 runner / 供应商调用可验证
- 检索词：app/skills、SkillResult、extra_forbidden、INVALID_INPUT、to_tool、adapter、ModelSettings、baseUrl、lastFrame、existingShots、SkillExecutionError、pickle、output_schema、SkillUnavailableError

## 现象与复现

对 `backend/app/skills/`（第一阶段骨架，尚无业务调用方）做代码评审并用临时脚本逐项实测，发现以下问题。原有 `test_skills` 全部通过，因为测试恰好绕开了这些路径。

1. `SkillResult(status="success", data=ImageGenerationOutput(...))` 抛 `extra_forbidden`（传 dict 同样）。只有写成 `SkillResult[Output](...)` 才成立，而基类自己构造错误结果时用的就是裸写法，实现者照写会让 `run()` 抛 `ValidationError`。
2. 协议比现有业务严：`VideoGenerationInput` 要求有尾帧必须有首帧，而 `video_service` 各提供商分支独立发送尾帧；`existingShots` 复用 `ShotSpec`，强制画面提示词非空、时长大于 0，而数据库分镜这两项默认是空和 0，`breakdown_service` 也明确容忍空画面提示词。
3. 各 `adapter.py` 直接 `model_validate`，非法参数抛出原始 `ValidationError`，其 `errors()` 带原始输入（提示词、URL）；`run()` 则只返回一句 "Input does not match the skill schema"，不含任何字段位置。
4. 工具 schema 把 `model`（provider / model / baseUrl / timeoutSeconds）作为必填参数暴露给 LLM，转成 OpenAI 工具后 `required` 为 `['model', 'prompt']`。授权只靠"runner 必须覆盖"的文档约定。
5. `ModelSettings.base_url` 接受 `https://user:secret@host/v1`，而 `MediaArtifact.url` 拒绝同类 URL。
6. `metadata().output_schema` 按校验形态生成，`usage.quantity` 发布为 number 或 string，实际输出恒为 string。
7. 次要：输入侧不校验重复 key / 悬空引用、`target: video` 可不带已有分镜；`VoiceDesignOutput.clips` 可重复 `lineKey`；design 模式带参考音频或 provider voice 被静默接受；带时长的 GIF 不能展示超过自身时长；音频 cue 不校验素材时长；`SkillUsage` 可只给 quantity 或只给 unit；`SkillExecutionError` 不能 pickle / copy，空 message 抛 `ValidationError`；registry 对未知名称抛 `KeyError`、未实现抛 `ValueError`，名称不校验格式，缺 schema 的类报 `AttributeError`；五个 adapter 完全重复；`__init__` 未导出 `SkillError`、`SkillUsage`；导入隔离测试未拦 `app.graph`、`app.utils`、`app.main`。

## 根因与定位

- 1：`SkillResult.data` 的类型变量上界是空的 `SkillModel`，未参数化时按上界校验，叠加 `extra="forbid"` 与 `revalidate_instances="always"`（[base.py](../../backend/app/skills/base.py)）。
- 2：schema 按"成品输出"的严格度写了输入，没有对照现有业务的实际数据（[video_generation/schema.py](../../backend/app/skills/video_generation/schema.py)、[script_breakdown/schema.py](../../backend/app/skills/script_breakdown/schema.py)）。
- 3、4：adapter 把技能的提供商级 Input 原样当作 Agent 工具 schema，也没有复用 `run()` 的脱敏路径。
- 5、6、7：单点遗漏，见各文件。

## 修复与影响

- [base.py](../../backend/app/skills/base.py)：新增 `BaseSkill.success()` / `failure()`；裸 `SkillResult` 带 data 时给出明确报错；`SkillError.details` 与 `validation_details()` 只返回字段路径和错误类型（至多 12 条）；`ModelSettings` 拒绝内嵌凭据；输出 schema 改为序列化形态；`SkillUsage` 要求 quantity 与 unit 成对；`SkillExecutionError` 支持 pickle / copy 并对空文案回退；`SkillMetadata.name` 限定 `^[a-z][a-z0-9_]{0,63}$`。
- [tool_adapter.py](../../backend/app/skills/tool_adapter.py)（新增）：五个 adapter 共用。带 `model` 的技能必须在 `to_tool(run, model=…)` 传入宿主解析的配置，该字段及 `host_inputs` 绑定的字段从 Agent schema 中移除并禁止覆盖；非法参数以脱敏文本作为工具结果返回。
- [registry.py](../../backend/app/skills/registry.py)：未知与未实现统一抛 `SkillUnavailableError`；缺声明报 `TypeError`。
- schema：尾帧不再要求首帧；新增宽松的 `ExistingShotSpec`；输入校验重复 key、悬空引用，`target: video` 要求已有分镜；镜头内引用不得重复；音色模式拒绝不属于该模式的字段，clips 的 `lineKey` 唯一；源时长上限只约束视频，音频 cue 不得超过已知素材时长。
- 调用方：`app/skills` 目前只有 `tests/test_skills.py` 引用，业务代码未受影响。`to_tool` 的签名变化（新增必填的 `model`）与 `registry.get` 的异常类型变化属于不兼容调整，但没有既有调用方。
- 有意保持不变：composer 的 FPS 仍为整数（与应用内视频能力一致）；同一镜头的字幕允许重叠；未被 `host_inputs` 绑定的媒体字段仍出现在 Agent schema 中，待第二阶段接 runner 时由宿主绑定。
- 长期规则已写入 [production-skills.md](../architecture/production-skills.md)。

## 验证

2026-11-16 实际执行（`backend` 目录，临时数据库与媒体目录）：

```bash
check_dir=$(mktemp -d /tmp/sceneflow-full-check.XXXXXX)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh $(rg --files tests -g 'test_*.py' | sed 's#^tests/##; s#\.py$##' | sort)
```

- 50 个文件中 49 个通过，含更新后的 `test_skills`（覆盖上述每一项）。
- `test_episode_migration` 失败，报 `NoSuchTableError: scenes`，与 [BUG-20260920-episode-migration-test-scenes](2026-09-20-episode-migration-test-scenes.md) 现象一致；本次未改迁移，未在干净工作区复跑对照。
- 修复前的现象由临时探针脚本实测得到（脚本已删除，未入库）。
- 未执行：前端检查（本次无前端改动）；真实供应商、MCP、独立 SDK 安装；未生成 Alembic revision 或 OpenAPI（无 HTTP / 数据库 schema 变化）。

## 历史与关联

- 2026-11-16：评审发现并一次修复。尚未提交，无 commit / PR。
- 骨架引入于 commit `c1177e7`（2026-11-10）。
