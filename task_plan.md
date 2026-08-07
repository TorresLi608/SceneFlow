# Task Plan: Project Continuity + Chat Attachments

## Goal
Summarize the current SceneFlow project so future AI sessions can resume development quickly and safely, then improve intelligent chat attachments and composer UI.

## Current Phase
Complete

## Session 2026-08-07: 当日修改日志归档

### Goal

- 将 2026-08-07 已完成及当前未提交的修改、验证结果和已知问题完整记录到持久化日志。

### Phases

#### Phase 1: 盘点当日修改

- [x] 检查当日 Git 提交、当前工作区差异和已有日志。
- [x] 在 `findings.md` 记录功能范围与关键决策。
- **Status:** complete

#### Phase 2: 写入并核验日志

- [x] 在 `progress.md` 记录当日修改、涉及文件、测试与错误。
- [x] 核对日志覆盖所有当日修改并执行 Markdown 差异检查。
- **Status:** complete

### Verification

- `cd backend && .venv/bin/python tests/run_all.py`：通过。
- `cd frontend && npm run lint`：通过。
- `cd frontend && npx tsc --noEmit`：通过。
- `git diff --check`：通过。
- Git 隐私检查：数据库与生成目录未被跟踪，当前可达历史无相关对象，`main` 与 `origin/main` 同步。

### Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| 从仓库根目录直接运行 `backend/tests/test_chat_balance.py` 时找不到 `app` 包 | 1 | 改用后端目录和模块方式运行单测。 |
| 在后端目录直接运行测试文件仍因脚本路径缺少包根目录而失败 | 2 | 使用 `.venv/bin/python -m tests.test_chat_balance`；随后全量 `tests/run_all.py` 通过。 |

## Session 2026-07-20: 用户与邀请码管理记录

### Goal

- 将今天未提交的用户管理、邀请码注册/管理和本地化修改持久化记录，便于后续提交或交接。

### Phases

#### Phase 1: 盘点工作区变更

- [x] 读取 Git 状态、已修改文件、未跟踪文件和相关代码差异。
- [x] 确认修改覆盖用户管理、邀请码注册/管理、本地化、测试和本地 SQLite 数据库。
- [x] 创建 `UNCOMMITTED_CHANGES.md`，按功能列出涉及文件、验证记录与提交注意事项。
- **Status:** complete

#### Phase 2: 同步规划记录

- [x] 将今天的实现、验证结果和构建锁问题写入本计划与进度日志。
- [x] 保留 `findings.md` 的现有删除状态，避免覆盖工作区中已存在的删除操作。
- **Status:** complete

### Today's Changes

- 用户管理：创建普通用户、重置密码、对应后端 API、BFF 和管理页操作。
- 邀请码：`invitation_codes` 数据表、1/7/30 天生成、列表状态与使用用户、注册时强制校验并消耗邀请码。
- 前端：邀请码管理页面/导航、注册表单邀请码字段、类型与 React Query/BFF 路由。
- 本地化：补齐邀请码和用户管理新增操作的中英文文案。
- 测试：新增管理员创建/重置密码及邀请码注册/消费自测。

### Verification

- 后端所有 `test_*.py`：通过。
- 前端 `npm run lint`、`npx tsc --noEmit`：通过。
- 用户管理本地化键检查：通过。
- `npm run build` 未完成：工作区已有 `.next/lock`，未清理或中断可能由用户运行的进程。

### Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Next 构建被 `.next/lock` 占用 | 1 | 未删除锁或中断进程；保留为待运行环境释放后验证。 |
| `findings.md` 已处于删除状态 | 1 | 未恢复或覆盖；今天的发现记录在 `UNCOMMITTED_CHANGES.md`、本计划与 `progress.md`。 |

## Session 2026-07-10: Workspace Layout + Admin Lists

### Goal
- Replace the oversized client-side `HomePage` router/shell with native Next.js route composition.
- Colocate route-private components under their owning `(workspace)` pages.
- Consolidate admin routes into the workspace and align user/model management list UI.

### Phases

#### Phase 1: Split the workspace shell from page content
- [x] Add `app/(workspace)/layout.tsx`.
- [x] Extract `WorkspaceShell` and `AppSidebar`.
- [x] Use `Link` + `usePathname()` for navigation state.
- [x] Make `/` redirect to `/chat`.
- [x] Move project/config queries to only the pages that use them.
- **Status:** complete

#### Phase 2: Colocate private route components
- [x] Move chat components to `(workspace)/chat/_components`.
- [x] Move image generation UI to `(workspace)/images/_components`.
- [x] Remove the duplicate standalone `/admin` UI.
- [x] Move model/user managers into their corresponding admin page `_components` folders.
- [x] Keep `/admin` as a workspace redirect to `/admin/models`.
- **Status:** complete

#### Phase 3: Improve admin list UI
- [x] Replace user cards with a table matching model management.
- [x] Add username/ID search, role/status filters, and 10-row pagination.
- [x] Keep superAdmin accounts protected from disable/delete actions.
- [x] Center the actions header and controls in both user and model tables.
- [x] Add Chinese/English list labels.
- **Status:** complete

#### Phase 4: Verify and persist the update
- [x] Run frontend ESLint.
- [x] Run TypeScript checking.
- [x] Run the user-filter Node test.
- [x] Run successful webpack production builds after the route/admin consolidation.
- [x] Record the final build approval-service failure separately from code validation.
- [x] Update `task_plan.md`, `findings.md`, and `progress.md`.
- **Status:** complete

### Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use a `(workspace)` route group with a shared layout | Native Next.js composition removes fake route wrappers without changing URLs. |
| Keep `AppSidebar` concrete instead of building a generic navigation framework | There is only one application sidebar; a configurable abstraction is not needed. |
| Derive active navigation from `usePathname()` | Removes duplicated URL/local `activeView` state. |
| Fetch projects only on `/ai-script` and model configs only on `/chat` or `/images` | Avoids loading unrelated data and client modules on every route. |
| Colocate private components under the owning page | Makes route ownership explicit and keeps feature-only code out of shared folders. |
| Redirect `/admin` to `/admin/models` | Preserves the old address while removing the duplicate admin shell. |
| Keep user filtering/pagination client-side with page size 10 | Current API returns a small complete user list; server pagination can wait until data size requires it. |

### Verification
- `cd frontend && npm run lint`
- `cd frontend && npx tsc --noEmit`
- `cd frontend && node --no-warnings --experimental-strip-types --test 'src/app/(workspace)/admin/users/_components/user-list.test.mts'`
- `cd frontend && npm run build -- --webpack` passed after workspace route/component/admin consolidation.
- Final build retry after the user-list change could not start because the automatic approval reviewer returned `404` for its own review model; lint, type-check, and logic test still passed.

### Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `apply_patch` rejected move-only hunks as empty | 1 | Re-ran moves with small legitimate import/formatting edits in the same patch. |
| Next/Turbopack build stayed at `Creating an optimized production build ...` | 1 | Interrupted the hung process and used Next's webpack build path. |
| Webpack build failed to fetch Google Fonts in the sandbox | 1 | Re-ran with approved network permission; build passed. |
| `.next/types` referenced the deleted standalone `app/admin/page.tsx` | 1 | Rebuilt Next output, which regenerated route types; TypeScript then passed. |
| `filterUsers` narrowed returned rows and hid `createdAt`/`updatedAt` | 1 | Made the helper generic so it preserves the full `AuthUser` shape. |
| TypeScript rejected the direct `.ts` extension in the Node test import | 1 | Added a scoped `@ts-expect-error` explaining Node's type-stripping execution. |
| Node rejected `--experimental-default-type=module` | 1 | Removed the unsupported flag and used `--no-warnings --experimental-strip-types`. |
| Final production-build escalation could not be reviewed because the approval service returned `404` | 1 | Did not bypass approval; retained successful lint, type-check, logic test, and earlier production builds as verification. |

## Session 2026-07-09: Recent Updates + Development Rules Docs

### Goal
- Record the recent dependency cleanup and i18n migration.
- Make the open-source-first rule explicit for future human/AI development.
- Document that `@base-ui/react` + shadcn-style components are the preferred frontend component foundation.

### Phases

#### Phase 1: Inspect current planning docs
- [x] Read `planning-with-files` instructions.
- [x] Read `task_plan.md`, `findings.md`, `progress.md`, `AI_HANDOFF.md`, and `RUNNING.md`.
- **Status:** complete

#### Phase 2: Capture recent decisions
- [x] Document open-source-first, avoid-hand-rolled-generic-code guidance.
- [x] Document `react-i18next`/`i18next` replacing custom i18n interpolation.
- [x] Document `google-genai` vs `langchain-google-genai` decision.
- [x] Document `@base-ui/react` + shadcn-style UI direction.
- **Status:** complete

#### Phase 3: Verify docs
- [x] Run lightweight doc/status checks.
- [x] Update `progress.md` with completed actions.
- **Status:** complete

### Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use open-source libraries before hand-written generic infrastructure | Keeps code maintainable and easier for humans/AI to extend. |
| Keep `useI18n()` as a local facade over `react-i18next` | Low churn at call sites while replacing the hand-rolled interpolation engine. |
| Keep `google-genai` for Gemini native image generation | Direct SDK is simpler for current image workflow; LangChain wrapper only matters for native Gemini chat. |
| Keep `@base-ui/react` + shadcn-style components | Matches current frontend stack and avoids custom primitive behavior. |

## Phases

### Phase 1: Create persistent notes
- [x] Create `task_plan.md`
- [x] Create `findings.md`
- [x] Create `progress.md`
- **Status:** complete

### Phase 2: Inspect project structure
- [x] Identify stack, package manager, and workspace layout
- [x] Identify backend entry points and major modules
- [x] Identify frontend entry points and major modules
- [x] Identify useful scripts and test commands
- **Status:** complete

### Phase 3: Write handoff summary
- [x] Update `findings.md` with project map and development notes
- [x] Update `progress.md` with completed actions
- [x] Add current-session pointer to `AI_HANDOFF.md`
- [x] Mark this plan complete
- **Status:** complete

## Key Questions
1. What technology stack and package manager does this repo use?
   - Backend: Python/FastAPI/SQLite/LangChain/LangGraph. Frontend: Next.js 16/React 19/TypeScript/Tailwind/assistant-ui. Package docs mention npm; root also has a tiny pnpm lock.
2. Where are the main app entry points and core modules?
   - Answered in `findings.md` under Project Map.
3. What commands should future AI sessions run before changing code?
   - Backend compile check and frontend lint/build/type-check are documented in `AI_HANDOFF.md`; exact commands captured in `findings.md`.

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use the three planning files in the project root | Matches `planning-with-files`; keeps context beside code for future sessions. |
| Keep the summary concise | Future AI needs a map, not a second codebase. |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `zsh: no matches found: frontend/src/app/projects/[projectId]/page.tsx` | 1 | Quote bracketed Next.js route paths before reading them. |
| `zsh: no matches found: frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` | 2 | Same bracket-path issue; quote all Next dynamic route paths. |

## Notes
- Re-read this file before making project-level decisions.
- Update `findings.md` after project discoveries.
- Update `progress.md` after each phase or error.

## Session 2026-07-06: Chat Attachments + Composer UI

### Goal
- Make intelligent chat upload accept all files, including code files like `.py`.
- Parse images and text/code files when possible.
- For unsupported or unreadable binary formats, send an explicit "cannot parse this file" notice instead of blocking upload.
- Clean up the frontend composer to feel closer to ChatGPT: compact attachments, clear input row, less visual clutter.

### Phases

#### Phase 1: Inspect current assistant-ui integration
- [x] Read assistant-ui overview, primitives, and runtime skill docs.
- [x] Read current composer/runtime code and backend attachment flow.
- **Status:** complete

#### Phase 2: Implement all-file attachment adapter
- [x] Replace limited image/text adapter with wildcard adapter.
- [x] Keep images as image parts.
- [x] Read text/code files into text parts.
- [x] Send PDF/Office/other files to backend parser with explicit unparseable notices.
- **Status:** complete

#### Phase 3: Tighten composer UI
- [x] Make attachment chips compact and wrapping.
- [x] Keep input controls in a ChatGPT-like bottom row.
- [x] Remove oversized attachment bar behavior seen in screenshots.
- **Status:** complete

#### Phase 4: Verify and document
- [x] Run backend compile/service checks if backend touched.
- [x] Run frontend type-check and lint.
- [x] Update `AI_HANDOFF.md`, `findings.md`, and `progress.md`.
- **Status:** complete

### Verification
- `backend/.venv/bin/python -m compileall -q backend`
- `backend/.venv/bin/python backend/chat_service.py`
- `cd frontend && npx tsc --noEmit`
- `cd frontend && npm run lint`
- `cd backend && .venv/bin/python -c "...attachment smoke test..."`

## Session 2026-07-06: Chat Streaming, AI SDK, and Scroll UX

### Goal
- Make the intelligent chat message list behave correctly during streaming output.
- Show a visible scrollbar and a ChatGPT-like "scroll to bottom" arrow when the user scrolls away from the latest response.
- Let Vercel AI SDK handle frontend chat sending, stream parsing, and in-progress message state where it fits.
- Keep Assistant UI responsible for rendering and composer primitives.

### Phases

#### Phase 1: Message list scrollbar
- [x] Add a dedicated `chat-message-list-scrollbar` class to the message list scroller.
- [x] Add scoped scrollbar CSS in `frontend/src/app/globals.css`.
- **Status:** complete

#### Phase 2: Streamdown package clarification
- [x] Identify `streamdown` as the AI-streaming Markdown renderer.
- [x] Identify `@streamdown/code` as Shiki syntax highlighting for code blocks.
- [x] Identify `@streamdown/cjk` as CJK-friendly Markdown/text handling.
- **Status:** complete

#### Phase 3: AI SDK frontend integration
- [x] Add `@ai-sdk/react` and `ai` dependencies.
- [x] Convert BFF chat stream response from backend NDJSON into AI SDK UI stream chunks.
- [x] Replace the frontend hand-written NDJSON reader with `useChat` and `DefaultChatTransport`.
- [x] Preserve existing `agent_step` execution flow UI through transient `data-agent_step` chunks.
- [x] Keep backend Python/LangChain/LangGraph model calls unchanged.
- **Status:** complete

#### Phase 4: Auto-scroll and bottom arrow
- [x] Pass `isStreaming` from `use-chat-controller.ts` through `chat-panel.tsx` to `chat-message-list.tsx`.
- [x] Auto-scroll only while the user remains near the bottom.
- [x] Show a floating down-arrow button when the user scrolls away from the bottom.
- [x] Clicking the arrow scrolls to the bottom and resumes auto-follow.
- [x] Gate `ResizeObserver` follow-up scrolling so async content growth can settle without fighting manual upward scroll.
- [x] Cancel pending auto-scroll immediately when the user scrolls upward.
- **Status:** complete

### Verification
- `cd frontend && npm run lint`
- `cd frontend && npx tsc --noEmit`

### Notes
- `cd frontend && npm run build` was attempted after AI SDK integration but stayed in Next/Turbopack "Creating an optimized production build ..." for more than two minutes with no new output, then was interrupted to avoid leaving a hanging process.
- `npm install @ai-sdk/react ai` reported 12 npm audit findings; they were not fixed in this task to avoid widening scope.
- The AI SDK migration is intentionally frontend/BFF-scoped. Full backend migration to a Node/Vercel AI SDK runtime was skipped because the backend already owns Python LangChain/LangGraph orchestration and persistence.

### Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `zsh: no matches found: frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` | 1 | Quote bracketed Next.js dynamic route paths. |
| ESLint parsing error in BFF stream route after adding `createUIMessageStreamResponse` | 1 | Fixed a missing closing parenthesis around `createUIMessageStream(...)`. |
| React lint error: `setState` synchronously inside an effect | 1 | Moved initial scroll-state update into `requestAnimationFrame`. |
| Streaming output caused scroll jitter, worse when user scrolled upward | 1 | Gated `ResizeObserver`, canceled pending auto-scroll on upward wheel, and only auto-follow when still near bottom. |

## Session 2026-07-06: Chat Scroll Documentation Sync

### Goal
- Check whether the latest chat initial-scroll fix is reflected in project docs, and update only stale documentation.

### Phases

#### Phase 1: Inspect docs
- [x] Read existing planning files.
- [x] Search project docs for chat scroll behavior.
- **Status:** complete

#### Phase 2: Sync stale docs
- [x] Update any stale docs found.
- [x] Keep documentation scoped to current behavior.
- **Status:** complete

#### Phase 3: Verify
- [x] Run lightweight documentation/diff checks.
- [x] Update `findings.md` and `progress.md`.
- **Status:** complete

### Verification
- `rg` scan for stale chat-scroll/ResizeObserver phrases in markdown
- `git diff --check`

## Session 2026-07-21: AI 短剧编排与代码审查文档

### Goal

生成可独立评审的编排架构文档，明确 LangGraph、持久化任务、worker、中断恢复和资产回滚边界。

### Phases

- [x] 复核当前前后端、TTS、generation jobs 和 LangChain/LangGraph 依赖。
- [x] 汇总代码审查修复项与仍未完成范围。
- [x] 生成 `AI_SHORT_DRAMA_ORCHESTRATION.md`。
- [x] 修正主技术方案中的模拟音频过时描述。
- [x] 更新 planning 文件并完成 Markdown 检查。
- **Status:** complete

### Decisions Made

| Decision | Rationale |
|---|---|
| LangGraph 只负责 LLM 决策与人工确认 | checkpoint/interrupt 适合小型结构化状态，不适合媒体长任务。 |
| 媒体任务继续使用 generation jobs + worker | 数据库租约、幂等和重试可避免重启丢任务与重复扣费。 |
| 回滚使用版本指针与 stale 标记 | 已生成素材有成本，不应通过删除模拟事务回滚。 |
| 音频时长复用 FFprobe | 避免手写媒体解析，也不引入许可证需额外评估的依赖。 |

### Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| 受限网络首次无法安装音频解析依赖 | 1 | 联网审批后核对许可证，最终不纳入项目并改用已有 FFprobe。 |

## Session 2026-07-21: AI 漫剧 / 短剧开发首个纵向切片

### Goal

完成项目生产参数的前后端持久化闭环，并建立可恢复、可重试的 generation job 后端基础。

### Phases

#### Phase 1: 项目生产设置
- [x] 扩展项目数据表、兼容迁移、校验与序列化。
- [x] 提供创建参数和独立更新 API。
- [x] 在项目工作台提供模式、画幅、帧率、时长、语言及提示词设置。
- [x] 同步前端类型、actions、store 与 WebSocket 增量字段。
- **Status:** complete

#### Phase 2: 持久化任务基础
- [x] 新增 generation jobs 表、索引和序列化。
- [x] 实现入队、列表、取消、重试、租约领取和完成服务。
- [x] 提供项目任务列表及任务取消/重试 API。
- [x] 增加所有权、幂等、重试和项目设置回归测试。
- **Status:** complete

#### Phase 3: Verification
- [x] 后端全量测试与 compileall。
- [x] 前端 ESLint 与 TypeScript 检查。
- [x] `git diff --check`。
- **Status:** complete

### Deferred

- worker processor、任务入队 UI、角色级声音/字幕、角色/地点资产、候选分镜版本及 FFmpeg 合成将在后续纵向切片接入。基础真实 TTS 已完成。

## Session 2026-07-21: AI 短剧 / 漫剧产品与技术调研

### Goal

结合 SceneFlow 已有能力和技术栈，调研代表性的开源与商业 AI 短剧/漫剧产品，产出可评审的产品文档、技术文档与缺口清单，本轮不实施功能。

### Phases

#### Phase 1: 仓库与现状盘点
- [x] 核对现有文生图、图生图、文生视频、图生视频、对话与 AI 剧本链路。
- [x] 记录可复用模块、数据模型和当前技术约束。
- **Status:** complete

#### Phase 2: 市场与项目调研
- [x] 调研有代表性的开源项目、开源组件和商业产品。
- [x] 提取业务流程、生成流程、关键能力、差异与可验证来源。
- **Status:** complete（外部页面受策略限制，易变信息保留开发前核验标记）

#### Phase 3: 方案设计
- [x] 给出 SceneFlow 的产品定位、用户流程、功能结构、MVP 边界与迭代顺序。
- [x] 给出贴合当前栈的架构、数据模型、任务编排、模型适配、资产一致性与质量控制方案。
- [x] 列出当前缺失子功能及复用/新增判断。
- **Status:** complete

#### Phase 4: 文档交付与校验
- [x] 生成产品文档和技术文档。
- [x] 核验来源、文档链接、范围和结论一致性。
- [x] 更新调研记录并交付用户确认。
- **Status:** complete

### Decisions Made

| Decision | Rationale |
|---|---|
| 本轮只产出文档，不修改业务代码 | 用户要求先确认方案再进入开发。 |
| 优先复用现有生成、对话、项目与用量能力 | 避免另建一套重复的 AI 基础设施。 |

### Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| GitHub 泛关键词搜索噪声过高 | 1 | 改为目标仓库与官方资料定向核验。 |
| GitHub API 联网审批服务返回 404 | 1 | 切换到浏览器只读调研。 |
| 浏览器策略禁止访问 GitHub | 1 | 停止访问 GitHub，使用官网、模型页和论文等替代来源。 |
| 用户提供的 GitHub/Gitee/官网仍被浏览策略拒绝 | 1 | 使用用户提供的描述归纳流程，所有易变或法律相关信息标为开发前待核验。 |

## Session 2026-07-21: AI 短剧 / 漫剧可执行开发技术方案

### Goal

将现有技术方案细化为与 SceneFlow 当前代码一一对应的前后端开发计划、需求追踪矩阵、阶段任务和验收标准，本轮仍不实施业务代码。

### Phases

#### Phase 1: 当前实现复核
- [x] 复核当前未提交代码是否已改变模型用途、数据库和用量设计。
- [x] 复核项目工作台、BFF/actions、WebSocket 和生成服务的真实边界。
- **Status:** complete

#### Phase 2: 需求与代码映射
- [x] 建立需求编号和前端、后端、数据、接口、验收追踪矩阵。
- [x] 明确复用、修改、新增和不做范围。
- **Status:** complete

#### Phase 3: 开发阶段与交付
- [x] 给出按依赖排序的前后端开发阶段和文件清单。
- [x] 给出每阶段联调、测试、迁移和上线门禁。
- [x] 更新技术文档并完成一致性检查。
- **Status:** complete

### Decisions Made

| Decision | Rationale |
|---|---|
| 直接升级 `AI_SHORT_DRAMA_TECHNICAL.md` | 避免新增一份内容重复的开发文档。 |
| 先复核当前未提交代码再定方案 | 工作区已有模型配置、数据库和用量相关修改，旧结论可能过时。 |

### Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| 技术文档大型补丁因一个表格上下文不匹配而失败 | 1 | 不重复整块补丁；拆成版本/模型修订与新增开发章节两部分，并按实际文本定位。 |
| 文档检查发现版本行尾空格和两处旧 `shot` 术语 | 1 | 删除尾随空格，并统一为现有 `scenes` 镜头语义。 |

## Session 2026-07-21: AI 漫剧 / 短剧开发启动

### Goal

按照 V0.2 技术方案开始实现 SceneFlow 的 AI 漫剧/短剧纵向链路，先交付不依赖具体供应商配置的生产基础、项目设置和持久化任务能力，并保持现有功能与数据兼容。

### Phases

#### Phase 0: 基线与冲突审计
- [x] 复核所有未提交修改，避免覆盖用户正在进行的模型配置改造。
- [x] 运行当前后端/前端基线检查。
- [x] 确认 pnpm workspace、Next.js 约束和数据库迁移现状。
- **Status:** complete

#### Phase 1: 后端生产基础
- [x] 增量扩展项目生产设置字段。
- [x] 实现持久化 generation jobs、幂等、租约、重试和取消服务基础。
- [x] 增加项目生产设置、任务查询和控制 API。
- **Status:** complete（worker processor 待后续阶段）

#### Phase 2: 前端生产基础
- [x] 扩展项目类型/actions/store。
- [x] 增加项目生产设置 UI。
- [x] 保持现有项目生成/排序/实时更新正常。
- [ ] 增加任务状态 UI。
- **Status:** partial

#### Phase 3: 验证与交付
- [x] 增加后端 job/项目/TTS 回归自检。
- [x] 运行后端全测、前端 lint/type-check 和数据库兼容检查。
- [x] 更新开发记录并说明下一阶段。
- **Status:** complete

#### Phase 4: 可配置真实 TTS
- [x] 统一模型配置增加 `audio` purpose。
- [x] 接入 Edge-TTS、本地 System TTS 和 OpenAI compatible TTS。
- [x] 将模拟音频替换为真实文件并增加测试与回退。
- **Status:** complete

### Decisions Made

| Decision | Rationale |
|---|---|
| 首个实现切片为 DR-01 + DR-06 基础 | 后续图片、TTS、视频和合成都依赖生产设置和可靠任务。 |
| 具体生成供应商暂不硬编码 | 用户后续配置模型；先提供 purpose/adapter/job 接入边界。 |
| 不覆盖现有统一 `model_configs` 修改 | 这些是工作区中的用户变更，AI 短剧代码只在兼容点增量工作。 |

### Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| 项目 API 补丁包含不存在的占位 import 上下文 | 1 | 拆分为精确 import、创建逻辑和新 endpoint 三个补丁，不重复原补丁。 |
| Edge-TTS 真实冒烟在受限网络环境不可达 | 1 | 验证自动回退系统语音，并用异步 mock 测试覆盖 Edge 保存分支。 |

## Session 2026-07-21: 开发文档同步

### Goal

将生产设置、generation jobs、可配置 TTS 和 Edge-TTS 的真实实现状态同步到产品、技术及 planning 文档。

### Phases

- [x] 复核代码变更与现有文档中的过时描述。
- [x] 更新产品文档的已完成功能和待确认项。
- [x] 将技术方案升级为 V0.3，标明已完成、部分完成和待开发边界。
- [x] 更新 `task_plan.md`、`findings.md` 和 `progress.md`。
- [x] 运行文档一致性和 `git diff --check`。
- **Status:** complete

### Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `zsh: command not found: ResizeObserver` while searching docs | 1 | Re-ran the `rg` search with the pattern in single quotes so backticks were not treated as shell command substitution. |

## Session 2026-07-21: Balance Enforcement and Usage Audit

### Goal

Audit today's account/level/invitation/redemption changes, enforce ordinary-user official-model balance rules, preserve personal-model usage accounting, add source/reset filters, organize backend tests/services, verify the full flow, and leave a concise implementation log.

### Current Phase

Complete — implementation, verification, and documentation finished.

### Phases

#### Phase 1: Discovery and business-flow audit
- [x] Trace every official/personal model execution path and usage write.
- [x] Trace balance cache/store refresh after redemption and model use.
- [x] Audit user creation defaults and list filters/reset behavior.
- **Status:** complete

#### Phase 2: Minimal implementation
- [x] Add backend insufficient-balance enforcement at the shared trust boundary.
- [x] Keep personal configuration usable while recording usage cost.
- [x] Add usage source filter and missing filter reset controls.
- [x] Ensure new-user level defaults to 1 in UI and backend.
- [x] Move backend tests to `tests/` and service modules to `services/`, updating imports and run instructions.
- **Status:** complete

#### Phase 3: Verification
- [x] Add focused backend regression checks for official/personal balance behavior.
- [x] Run all backend tests, frontend lint/type-check, and feasible build checks.
- [x] Exercise filter/reset and redemption refresh flows.
- **Status:** complete

#### Phase 4: Documentation and handoff
- [x] Record findings, changed files, decisions, errors, and test results.
- [x] Review diff and requirement coverage.
- **Status:** complete

### Verification Summary

- `cd backend && .venv/bin/python tests/run_all.py`
- `cd backend && .venv/bin/python -c 'from app import app; assert app.title == "SceneFlow Backend"'`
- `cd backend && .venv/bin/python -m compileall -q .`
- `cd frontend && pnpm lint`
- `cd frontend && pnpm exec tsc --noEmit`
- `git diff --check`
- Stale flat backend import scan: no matches.
- Production build was not repeated because this workspace already has a documented external Google Fonts/network blocker; repeating the same failed network action would not add code confidence.

### Key Decisions

| Decision | Rationale |
|----------|-----------|
| Do not add a state machine by default | Existing Zustand + React Query already represent global user/account state. |
| Put the balance gate in shared backend model-resolution/execution flow | One trusted guard is smaller and safer than UI-only checks in every page. |
| Limit backend reorganization to real categories | `tests/` and `services/` improve navigation; empty `plugins/` and a full package rewrite are YAGNI. |

### Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| `findings.md` absent although older logs referenced it | 1 | Recreated it for this audit without touching existing plan/progress history. |
| `apply_patch` findings hunk mismatch | 1 | Re-read the file and used its actual section order. |
| Second `apply_patch` findings hunk mismatch | 1 | Patched the actual sections independently and logged the repeated assumption error. |
| Base UI Select rejected primitive `items` arrays | 1 | Converted usage feature/day options to `{ value, label }` items. |

## Session 2026-07-21: Admin All Usage Records

### Goal

Allow super administrators to browse every user's usage history with fuzzy username search and pagination.

### Phases

#### Phase 1: Backend query
- [x] Add super-admin-only `/api/admin/usage-logs` endpoint.
- [x] Join usage records with usernames.
- [x] Add parameterized fuzzy username search and pagination.
- **Status:** complete

#### Phase 2: Management UI
- [x] Add “全部使用记录” management menu and route title.
- [x] Add username search, clear action, table, and pagination.
- [x] Display user, time, type, source, model, tokens, and cost.
- **Status:** complete

#### Phase 3: Verification and documentation
- [x] Add fuzzy-search and pagination backend self-check.
- [x] Run backend tests/compile and frontend lint/type-check.
- [x] Update README, findings, and progress logs.
- **Status:** complete

### Verification

- `cd backend && .venv/bin/python tests/run_all.py`
- `cd backend && .venv/bin/python -m compileall -q .`
- `cd frontend && pnpm lint`
- `cd frontend && pnpm exec tsc --noEmit`
- `git diff --check`

## Session 2026-07-21: 模型配置、邀请码/兑换码与图片单价修复

### Goal

完成并记录以下管理端修复：模型配置可在官方与个人来源之间直接切换；合并重复的模型配置表；邀请码和兑换码展示使用时间与创建人；修复图片单价无法清空编辑以及保存返回 500 的问题。

### Phases

#### Phase 1: 统一模型配置存储
- [x] 将 `user_configs` 与 `official_model_configs` 合并为 `model_configs`。
- [x] 使用 `source=user|official` 和 `user_id` 区分配置归属。
- [x] 增加旧数据库迁移、配置 ID 重映射、用户默认模型和会话引用迁移。
- [x] 允许管理员编辑现有配置时直接切换官方/个人来源，保留同一个配置 ID 与 API Key。
- **Status:** complete

#### Phase 2: 邀请码与兑换码审计字段
- [x] 为邀请码和兑换码增加 `created_by_user_id`，生成时记录当前管理员。
- [x] API 返回 `createdBy`，管理表格展示“创建人”。
- [x] 邀请码展示使用时间；兑换码沿用已有兑换时间展示。
- [x] 旧记录无法可靠反推创建人时显示 `—`，不做错误回填。
- **Status:** complete

#### Phase 3: 图片单价编辑与保存
- [x] 将计费输入的前端编辑状态改为字符串，允许删除初始 `0` 后重新输入整数或小数。
- [x] 提交时再将价格转换为数字。
- [x] 仅在连接字段改变或首次设为默认配置时重新验证模型。
- [x] 仅修改价格时不再调用外部模型验证接口。
- [x] 增加完整管理页参数更新图片单价的回归测试。
- **Status:** complete

#### Phase 4: Verification and handoff
- [x] 验证旧双表向统一表的迁移及外键完整性。
- [x] 在真实数据库副本中验证配置 ID `5` 可保存 `unitPrice=5`、`unitName=image`。
- [x] 运行后端全量测试、前端 TypeScript、ESLint 和 diff 检查。
- [x] 记录运行中旧后端进程尚未加载修复代码的环境问题。
- **Status:** complete

### Verification

- `cd backend && .venv/bin/python tests/run_all.py`
- `cd frontend && pnpm exec tsc --noEmit`
- `cd frontend && pnpm lint`
- 临时数据库及真实数据库副本迁移验证：通过，外键检查无错误。
- 当前代码直接调用 `update_model_config(5, payload, 2)`：成功返回 `unitPrice: 5.0`、`unitName: image`。
- `git diff --check`

### Key Decisions

| Decision | Rationale |
|---|---|
| 合并为一张 `model_configs` 表 | 两类配置字段和生命周期高度一致；双表使来源切换必须删除重建，并造成默认配置、会话和用量引用分叉。 |
| 保持配置 ID 不变地切换来源 | 避免重建配置、重复录入 API Key，以及修复下游引用。 |
| 不为旧邀请码/兑换码猜测创建人 | 历史数据没有可靠来源，错误回填比显示未知更危险。 |
| 价格编辑期间保留字符串状态 | 数字输入每次按键立即转换会把空字符串强制变回 `0`，导致无法正常编辑。 |
| 价格修改不触发供应商验证 | 计费字段不影响连接有效性，外部验证会引入无关超时和 500。 |

### Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| 图片单价中的 `0` 无法删除 | 1 | 将输入状态改为字符串，保存时再转换为数字。 |
| 保存完整图片模型参数时提示 `Internal Server Error` | 1 | 发现更新流程无条件调用外部模型验证；改为仅在连接字段变化或首次设默认时验证。 |
| 监听 `8080` 的后端 PID `58712` 仍运行旧代码，请求持续等待 | 1 | 代码和数据库副本验证均已通过；需要用户在后端终端手动 `Ctrl+C` 后运行 `npm run dev:backend`。 |
| 尝试终止旧后端进程被 sandbox 拒绝，升级审批服务返回 `codex-auto-review` 404 | 1 | 未绕过权限；将重启步骤作为运行环境交接项记录。 |

## Session 2026-07-21: Admin User Role Selection

### Goal

Let a super administrator choose ordinary user or super administrator when creating an account, defaulting to ordinary user.

### Phases

#### Phase 1: Backend validation
- [x] Accept `user` and `superAdmin` roles only.
- [x] Default omitted role to `user`.
- [x] Persist the selected role during creation.
- **Status:** complete

#### Phase 2: Frontend form
- [x] Add role selector to the create-user dialog.
- [x] Default/reset the selector to ordinary user.
- [x] Submit the selected role through existing admin actions/types.
- **Status:** complete

#### Phase 3: Verification and documentation
- [x] Test default role, super-admin creation, and invalid-role rejection.
- [x] Run backend tests/compile and frontend lint/type-check.
- [x] Update planning logs.
- **Status:** complete

### Verification

- `cd backend && .venv/bin/python tests/run_all.py`
- `cd backend && .venv/bin/python -m compileall -q .`
- `cd frontend && pnpm lint`
- `cd frontend && pnpm exec tsc --noEmit`
- `git diff --check`
