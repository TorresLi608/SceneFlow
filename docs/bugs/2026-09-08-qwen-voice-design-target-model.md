# BUG-20260908-qwen-voice-design-target-model：音色设计任务模型被误作合成目标

- 首次记录：2026-09-08
- 最近更新：2026-09-08
- 状态：请求目标回退的本地回归通过；真实 DashScope 调用待验证，账号音色目标元数据仍待对齐
- 检索词：Qwen、DashScope、`qwen-voice-design`、`target_model`、`qwen_voice_service.create_voice`、音色设计
- [返回 Bug 索引](README.md)

## 现象与复现

当音色配置的模型填为 `qwen-voice-design` 时，修改前的适配器把它同时放入请求的任务 `model` 和合成 `input.target_model`。后者应指向 TTS 合成模型，不能使用音色设计任务名。空模型此前直接抛出 `Qwen voice design target model is required`。

本次从未提交差异确认该请求构造问题，并用 stub HTTP 响应检查发出的 `target_model`；未调用真实收费接口，没有确认现场错误码或供应商响应。

## 根因与定位

[qwen_voice_service.py](../../backend/app/services/qwen_voice_service.py) 的 `create_voice` 原样使用配置中的 `model` 作为合成目标，没有区分任务模型和合成模型。两个生产调用方共用它：

- [user_voices.py](../../backend/app/api/v1/user_voices.py)：独立音色页的请求内设计。
- [job_handlers.py](../../backend/app/services/job_handlers.py)：项目 `voice_design` 队列任务，包括新建和原位重新设计。

[model-providers.ts](../../frontend/src/lib/model-providers.ts) 的 Qwen 音色预设此前未提供默认模型值。

## 修复与影响

共享适配器保持任务模型 `qwen-voice-design`，把空值或同名任务模型回退为 `qwen3-tts-vd-realtime-2025-12-16`；其他显式配置保持原值。前端 Qwen 音色预设和输入提示同步使用该目标。HTTP ≥400 时，适配器现在提取供应商 `message`/`code`，解析失败时截取响应文本；该错误分支尚无本次执行的专项断言。

回退只影响发往供应商的请求。两个调用方仍把原始配置写入 `UserVoice.target_model`，因此回退后的 `targetModel` 展示元数据可能不准确；本次文档核对没有修改这条持久化路径。长期契约见 [后端供应商说明](../../backend/README.md#providers-and-model-configuration)，待办见 [Backlog](../plans/backlog.md)。

## 验证

2026-09-08 实际执行：

```bash
cd backend
audit_voice_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$audit_voice_dir/media" sh scripts/run_tests.sh test_qwen_voice_service test_voice_design_api test_voices_api
```

- 三个测试文件均通过；runner 为每个文件提供临时数据库，媒体目录也已隔离。
- `test_qwen_voice_service` 验证显式目标保留、任务模型回退、预览音频解码；未覆盖空模型及供应商错误响应分支。
- `test_voice_design_api` 验证项目设计/账号保存、导入及携带 `voiceId` 重新设计后仍只有原项目音色 ID；提供商已替换为 stub。新默认台词的全部分支、角色绑定和排队期间删除目标的场景未被这些断言覆盖。
- `cd frontend` 后 `pnpm exec tsc --noEmit` 通过；`pnpm lint` 为 0 错误、1 个既有警告：`src/hooks/use-unsaved-settings-check.ts` 中未使用的 `Project` 导入。
- 临时数据库/媒体目录下导入 `scripts.regen_api_spec`，将其 `HEADER` 与相同参数的 `yaml.safe_dump(app.openapi(), ...)` 输出逐字比较：当前 `docs/reference/api-spec.yaml` 完全一致，未手工改写生成文件。
- 未运行真实 DashScope 生成、浏览器交互回归或完整应用测试套件。

## 历史与关联

- 2026-09-08：核对现有未提交修复及调用方，执行上述检查并补录本记录；不将文档补录描述为另一次代码修复。
- 同批的项目音色原位重新设计、默认台词和共享媒体预览属于功能变更，分别更新 [数据流](../architecture/data-flow.md#project-voice-design-and-editing) 和 [代码地图](../architecture/code-map.md)，不另建 Bug 条目。
