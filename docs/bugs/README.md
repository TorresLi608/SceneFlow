# Bug 历史索引

这是 Bug 排查和修复记录的统一入口。**AI 接到 Bug 修复任务时先读本索引，按现象、错误码或模块查找，再打开匹配的详情；每次修复交付前，必须同时更新详情和本索引。** 不在仓库根目录新建 `BUGFIX_*.md`、修复报告或总结文档。

当前迁入了原 `known-errors.md` 的条目和 Git 中可追溯的根目录 Bug 报告。历史记录不是当前版本已经通过验证的证明；详情会区分源码核对、实际测试和待验证事项。

## 问题列表

按最近更新日期倒序维护；同一天按首次记录日期倒序。每个详情文档只保留一行索引。

| 问题 ID | 检索词 / 模块 | 摘要 | 状态 | 最近更新 | 详情 |
|---|---|---|---|---|---|
| BUG-20260910-chat-composer-draft-focus | 智能问答、输入框、焦点、草稿、isSendDisabled、isSending | 发送时整体禁用输入且等待回复结束才恢复焦点；现改为立即聚焦、持续编辑并单独限制发送 | 本地检查和模拟流浏览器验证通过 | 2026-09-10 | [聊天输入框焦点与草稿](2026-09-10-chat-composer-draft-focus.md) |
| BUG-20260910-chat-error-thinking-state | 智能问答、报错、思考框、执行流程、agentSteps、reasoning、onError | 错误回调未清理临时步骤及本轮思考；现统一清理并保留历史、正文和草稿 | 前端回归和模拟流浏览器验证通过 | 2026-09-10 | [聊天报错后思考区域残留](2026-09-10-chat-error-thinking-state.md) |
| BUG-20260910-mobile-responsive-layout | 移动端、响应式、320px、侧栏、分镜详情、素材弹窗、英文按钮、dvh、iOS | 补齐手机导航、纵向滚动、弹窗约束和按钮换行，调整平板表单列宽；折叠导航保留可访问名称 | 浏览器视口回归及前端检查通过，真机待验证 | 2026-09-10 | [移动端布局适配](2026-09-10-mobile-responsive-layout.md) |
| BUG-20260909-video-first-frame-default | 首帧、分镜图、视频提示词、videoFirstFrame、shot-row | 生成分镜图后视频编辑器自动填充首帧；已移除自动推导，手动选择仍保留 | 类型检查和现有回归通过，浏览器未验证 | 2026-09-09 | [视频首帧默认填充](2026-09-09-video-first-frame-default.md) |
| BUG-20260908-qwen-voice-design-target-model | Qwen、DashScope、qwen-voice-design、target_model、音色设计、qwen_voice_service | 任务模型被误作合成目标；共享适配器增加目标模型回退，账号音色 targetModel 元数据仍待对齐 | 本地回归通过，实网待验证 | 2026-09-08 | [Qwen 音色目标模型](2026-09-08-qwen-voice-design-target-model.md) |
| BUG-20260908-export-video-audio-missing | 视频导出、合并导出、音频丢失、concat_videos、export_service、无声音、FFmpeg、a=0 | concat 的 a=0 丢弃音轨；已增加探测、补齐与映射，但探测失败仍按无音频处理 | 正常路径已验证，探测失败待完善 | 2026-09-08 | [合并导出视频丢失音频](2026-09-08-export-video-audio-missing.md) |
| BUG-20260908-docker-pnpm-ignored-builds | ERR_PNPM_IGNORED_BUILDS、docker:build、Dockerfile、pnpm-workspace.yaml、allowBuilds、onlyBuiltDependencies、Corepack、pnpm 10 | Docker 构建前端镜像时因缺少 pnpm-workspace.yaml 拷贝及 packageManager 锁定导致 ERR_PNPM_IGNORED_BUILDS；已补充拷贝与版本锁定 | 已验证 | 2026-09-08 | [Docker 前端构建 pnpm 报错](2026-09-08-docker-pnpm-ignored-builds.md) |
| BUG-20260907-admin-tables-double-border | 管理后台、Table、border、border-radius、admin/users、admin/usage-logs、admin/error-logs、admin/invitation-codes、admin/redemption-codes、双边框 | 管理后台 5 个页面外层冗余包装 div 导致与 Table 组件内置容器叠加产生双重边框与圆角不一致；已移除冗余包装 | 已验证 | 2026-09-07 | [后台表格双边框](2026-09-07-admin-tables-double-border.md) |
| BUG-20260907-sqlite-persistence | SQLite、Docker、DATABASE_URL、SCENEFLOW_DB_PATH、本地迁移、数据丢失、WAL、挂载权限 | 移除旧变量，统一 DATABASE_URL；本地旧库已迁至 data/app.db，逐表/哈希校验和三项后端回归通过 | 本地已验证，容器待验证 | 2026-09-07 | [SQLite 部署持久化](2026-09-07-sqlite-persistence.md) |
| BUG-20260907-video-unsupported-fps | Seedance 2.0、fps=24、videos/generate | 模型不支持 FPS 时表单仍发送 24；已移除硬编码回退 | 已修复，验证范围见详情 | 2026-09-07 | [不支持的 FPS 参数](2026-09-07-video-unsupported-fps.md) |
| BUG-20260907-generation-editor-reset | 重置、历史记录、图片、视频、音色 | 历史回填后缺少新建编辑入口；三个面板支持重置并保留历史 | 已修复，验证范围见详情 | 2026-09-07 | [生成编辑器重置](2026-09-07-generation-editor-reset.md) |
| BUG-20260904-video-reference-save | 视频提示词、@素材、videoReferences、validate_video_reference_counts | 保存视频引用时调用参数不匹配；历史修复后仍有配置解析和校验缺口 | 部分修复，待验证 | 2026-09-07 | [视频参考素材保存](2026-09-04-video-reference-save.md) |
| BUG-20260901-breakdown-invalid-json | BREAKDOWN_INVALID_JSON、502、分镜拆解、JSON、转义、截断 | 模型响应格式差异导致拆解失败；兼容解析和回归样例已存在 | 历史修复，未复跑 | 2026-09-07 | [分镜拆解 JSON 兼容](2026-09-01-breakdown-invalid-json.md) |

## 排查和归档规则

1. **先检索，再定位。** 先在上表搜索错误码、现象和模块，再读相关详情中的触发条件、根因、代码入口和验证记录。历史方案必须与当前代码核对，不能直接照抄。需要现场信息时再结合请求 ID、错误日志和当前复现结果。
2. **同一问题更新原文档。** 相同根因复发时追加日期、复现和修复/验证记录，并更新索引状态；不要另建一份重复总结。不同根因独立建档，相关问题互相链接。一项任务修复多个独立问题时分别记录。
3. **新问题固定位置。** 详情文件为 `docs/bugs/YYYY-MM-DD-short-topic.md`，日期为首次记录日期，主题使用简短英文 kebab-case。问题 ID 为 `BUG-YYYYMMDD-short-topic`，在索引中唯一；后续更新保留原文件名和 ID。
4. **每次修复都留证据。** 无论改动大小，都在同一次交付中更新详情和索引，记录实际修改位置、根因、验证命令及结果。未复现、未执行、失败或受阻如实标注；有测试文件不等于测试通过，没有提交时不编造 commit。
5. **索引只放摘要。** 具体分析和复现过程放详情；长期规则更新对应架构/约定文档并在详情中链接。不要把待办清单、普通功能开发或每轮聊天都变成 Bug 报告。
6. **保留可追溯性和隐私。** 迁移旧报告注明原路径、来源提交和验证局限；移动文件同步修正索引/引用。只放脱敏的最小复现和诊断信息，不复制密钥、JWT、签名链接、完整脚本、聊天内容或原始模型输出。

这些是仓库内的工作约定，由 [AGENTS.md](../../AGENTS.md#bug-fix-workflow) 和导入它的 CLAUDE.md 约束后续 AI 工作；不是后台自动生成报告的程序。旧 [known-errors.md](../reference/known-errors.md) 仅保留跳转，不再维护第二份历史列表。

## 详情最小模板

新建记录时使用以下结构，填写真实信息；已有文档补充相应字段即可，不为排版重写历史。

```markdown
# BUG-YYYYMMDD-short-topic：问题标题

- 首次记录：YYYY-MM-DD
- 最近更新：YYYY-MM-DD
- 状态：待定位 / 已修改待验证 / 已验证 / 历史记录待复核
- 检索词：错误码、用户现象、模块、关键函数

## 现象与复现
影响的页面/API、触发条件、预期和实际表现、最小复现步骤。

## 根因与定位
共享问题入口和代码链接；区分已确认原因与待验证假设。

## 修复与影响
改了什么、涉及哪些调用方、仍有什么限制；关联长期规则文档。

## 验证
实际执行的命令/手工步骤、结果、未执行项及原因；不要把建议步骤写成通过。

## 历史与关联
按日期追加复发/修复记录，附已有 commit/PR/旧报告出处及相关问题链接。
```

执行验证遵循 [测试约定](../conventions/testing.md)；HTTP 错误消息查 [错误清单](../reference/error-codes.md)，代码入口查 [代码地图](../architecture/code-map.md)。
