# Progress Log

## Session: 2026-08-07 — 当日修改日志归档

### Phase 1: 盘点当日修改

- **Status:** complete
- Actions taken:
  - 读取 `planning-with-files` 技能及模板。
  - 确认项目根目录已有三份规划文件，选择追加而非覆盖历史。
  - 检查 2026-08-07 的 6 个 Git 提交、当前未提交差异、Git 可达历史、忽略规则与远端分支状态。
  - 确认 `backend/sceneflow.db`、`backend/generated/`、`backend/private_generated/` 已不再被跟踪，当前可达 Git 历史也不包含这些对象。
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 2: 当日修改明细

- **Status:** complete
- Committed changes:
  - `9546f17` — 隐私与安全整改、模型发现及智能问答思考过程：
    - 忽略数据库与生成目录；生成图片、视频、音频和 Agent 产物迁移到私有目录并以签名 URL 访问。
    - 数据库/生成文件收紧权限；移除公开 `/generated` 静态挂载。
    - WebSocket JWT 改走子协议头并校验项目归属；Base URL 拒绝私网/localhost/内嵌凭据。
    - 新增模型列表发现接口和 `ModelSeriesCombobox`；模型系列表单位置调整到 Base URL/API Key 之后。
    - 分离 reasoning/thinking 与最终回答，使思考模型可展示思考过程。
    - 增加安全、模型列表、WebSocket、思考内容相关回归测试与后端说明。
  - `18f197b` — `.gitignore` 增加前端构建缓存忽略规则。
  - `593cffb` — API Key 返显与协议：
    - 新增按当前用户/超级管理员权限读取并解密模型 API Key 的接口。
    - 编辑表单回填 API Key，默认密文，支持眼睛按钮切换明文/密文。
    - 新增中英双语非商用源码可用 `LICENSE` 与 `DISCLAIMER.md`；根和前端包声明许可证位置。
  - `924ad5c` — Toast 统一：
    - 新增基于 Base UI/shadcn 风格的全局 Toast Provider/Viewport。
    - 用户、邀请码、兑换码、模型配置增删改及个人中心保存/兑换/改密统一成功失败 Toast。
    - 移除各页面重复的行内状态消息。
  - `689e950` — 用量与余额修复：
    - 超级管理员官方模型调用继续记录 Token/费用，但 SQL 扣款排除 `superAdmin`。
    - OpenAI 兼容流式模型开启 usage 回传，补齐输入/输出 Token 和费用统计。
  - `227b677` — 使用日志与界面修复：
    - 后端使用日志关联模型配置名称，个人/管理员列表新增模型名称列。
    - 个人使用日志按每页 10 条分页，筛选/重置回到第 1 页。
    - 修复获取模型列表后下拉内容被输入过滤为空的问题。
    - Popover 提升至 `z-50`，Toast 提升至 `z-[100]`，避免被表单遮罩遮挡。
    - 品牌副标题统一为“AI工作台”/“AI Workspace”。
- Current uncommitted changes:
  - `backend/app/services/chat_service.py`、`backend/tests/test_chat_balance.py`：第一条成功保存的用户问题自动成为会话标题；后续问题和余额拒绝不会覆盖标题。
  - `backend/app/api/v1/admin.py`、`backend/app/api/v1/settings.py`、`backend/app/services/config_service.py`、`backend/tests/test_config_service.py`：新增/编辑模型保存不再远程校验模型可用性，只保留 API Key 本地完整性检查；获取列表/显式校验不变。
  - `frontend/src/components/model-series-combobox.tsx`：增加稳定外层节点，继续处理输入/Popover 抖动问题。
  - `package.json`：版本调整为 `0.0.5`；当前文件末尾缺少换行，未在日志任务中擅自修改。
  - `task_plan.md`、`findings.md`、`progress.md`：本次当日日志归档。

### Test Results

| Test | Command / Scope | Result | Status |
|---|---|---|---|
| 后端全量自测 | `cd backend && .venv/bin/python tests/run_all.py` | 无错误，退出码 0 | Pass |
| 前端 ESLint | `cd frontend && npm run lint` | 无 lint 错误 | Pass |
| 前端 TypeScript | `cd frontend && npx tsc --noEmit` | 无类型错误 | Pass |
| Markdown/Git 空白检查 | `git diff --check` | 无空白错误 | Pass |
| 敏感文件跟踪状态 | `git ls-files`、`git log --all`、`git rev-list --objects --all` | 数据库与生成目录未跟踪，当前可达历史无相关对象 | Pass |
| 分支同步状态 | `git branch -vv` | `main` 与 `origin/main` 同步于 `227b677` | Pass |

### Error Log

| Error | Attempt | Resolution |
|---|---:|---|
| `ModuleNotFoundError: No module named 'app'`：从仓库根目录直接运行聊天测试 | 1 | 切换到 `backend` 并改用模块执行。 |
| 同一导入错误：在 `backend` 目录直接执行测试文件时脚本目录仍成为导入根 | 2 | 使用 `.venv/bin/python -m tests.test_chat_balance`；验证通过，并改跑 `tests/run_all.py`。 |

### Documentation Result

- `task_plan.md`：记录归档目标、阶段、验证与错误，状态已完成。
- `findings.md`：记录 6 个当日提交、当前未提交功能、安全清理结论及技术决策。
- `progress.md`：记录完整功能清单、涉及文件、测试结果和错误处理。

### Phase 3: 额度与计费精度整改

- **Status:** complete
- Root cause:
  - 余额/费用的整数微单位方案可保证 6 位小数精度。
  - 模型价格此前经过前端 `Number`、后端 `float` 和 SQLite `REAL`，18 位小数会被截断；大额整数返回前端后也可能超过 JavaScript 的安全整数范围。
- Actions taken:
  - 安装 `decimal.js@10.6.0` 并更新 `frontend/pnpm-lock.yaml`。
  - 前端金额字段和模型价格类型改为十进制字符串；`formatMoney`/`formatMicros` 使用 `decimal.js`。
  - 模型价格表单不再调用 `Number()`，价格输入允许任意小数位。
  - 兑换额度输入范围调整为最小 `0.000001`、步进 `0.000001`，余额及费用显示 6 位小数。
  - 后端 `normalize_pricing` 改用 `Decimal`，模型价格和金额序列化为字符串。
  - `model_configs` 和 `usage_logs` 增加 `pricing_json`；新建、编辑、计费记录均写入精确快照。
  - 保留旧 `REAL` 列并增加启动迁移，确保现有 SQLite 数据库无需手工处理。
  - 新增前端金额专项测试，并扩展配置、兑换码和使用费用后端测试。
- Files modified:
  - Backend: `app/api/v1/admin.py`, `settings.py`, `users.py`; `app/core/database.py`; `app/schemas/serializers.py`; `app/services/usage_service.py`。
  - Backend tests: `test_config_service.py`, `test_redemption_codes.py`, `test_usage_service.py`。
  - Frontend: model pricing form, redemption-code manager, profile, usage page, money utilities and auth/admin/usage types。
  - Dependency/test: `frontend/package.json`, `frontend/pnpm-lock.yaml`, `frontend/src/lib/money.test.mts`。

### Precision Test Results

| Test | Command / Scope | Result | Status |
|---|---|---|---|
| 18 位价格往返 | `test_config_service.py` | `0.123456789012345678` 等价格保存/读取不丢位 | Pass |
| 微单位额度兑换 | `test_redemption_codes.py` | `12.500001` 精确转换为 `12500001` micros | Pass |
| 超安全整数金额格式化 | `money.test.mts` | `9007199254740993` micros 正确显示为 `$9007199254.740993` | Pass |
| 后端全量自测 | `cd backend && .venv/bin/python tests/run_all.py` | 退出码 0 | Pass |
| 前端 ESLint / TypeScript | `pnpm lint && pnpm exec tsc --noEmit` | 无错误 | Pass |
| 前端金额专项测试 | `node --no-warnings --experimental-strip-types --test src/lib/money.test.mts` | 1 test passed | Pass |
| 差异检查 | `git diff --check` | 无空白错误 | Pass |

### Precision Error Log

| Error | Attempt | Resolution |
|---|---:|---|
| `npm install decimal.js` 未修改该 pnpm 项目的依赖文件 | 1 | 检查锁文件和包管理器后改用 pnpm。 |
| `pnpm add decimal.js` 在沙箱内出现 registry DNS 失败与 store 路径不一致 | 2 | 使用项目现有 `/Users/torresli/Library/pnpm/store/v10` 并在授权网络环境安装成功。 |

## Session: 2026-07-21 — Admin User Role Selection

- **Status:** complete
- Added role selection to the create-user form; default is ordinary user.
- Backend role whitelist accepts only ordinary user and super administrator.
- Backend tests, Python compile, frontend lint, TypeScript, and diff check passed.
- Files: `backend/routers/admin.py`, `backend/tests/test_admin_users.py`, `frontend/src/types/admin.ts`, and the admin user manager.

## Session: 2026-07-21 — Admin All Usage Records

- **Status:** complete
- Added management menu and `/admin/usage-logs` page.
- Added `GET /api/admin/usage-logs` with super-admin authorization, username fuzzy search, and pagination.
- Added `backend/tests/test_admin_usage_logs.py`.
- Verification passed: backend test runner, Python compile, frontend lint, TypeScript, and `git diff --check`.
- Documentation patch initially assumed a stale progress heading; re-read the file and applied against its actual structure.
- Files: `backend/routers/admin.py`, `backend/tests/test_admin_usage_logs.py`, admin actions/types/query keys, workspace navigation/title, i18n, and `/admin/usage-logs`.

## Session: 2026-07-20

### Phase 13: 用户与邀请码管理
- **Status:** complete
- Actions taken:
  - 为管理员新增创建普通用户与重置密码能力，前后端均通过现有 BFF/React Query 模式接入。
  - 新增邀请码数据表、生成与列表 API；邀请码有效期限定为 1、7、30 天。
  - 注册流程改为必须提交有效邀请码，并在成功注册后标记邀请码及使用用户。
  - 新增管理中心邀请码页面、导航和注册页邀请码输入。
  - 补齐用户管理与邀请码功能的中英文文案；修复用户管理新增操作显示翻译键的问题。
- Files created/modified:
  - `backend/database.py`
  - `backend/routers/admin.py`
  - `backend/routers/auth.py`
  - `frontend/src/app/(workspace)/admin/invitation-codes/**`
  - `frontend/src/app/api/bff/admin/invitation-codes/route.ts`
  - `frontend/src/app/register/page.tsx`
  - `frontend/src/lib/i18n.ts`
  - 用户管理、BFF、actions、types 与测试相关文件；完整清单见 `UNCOMMITTED_CHANGES.md`。

### Phase 14: 未提交变更文档化
- **Status:** complete
- Actions taken:
  - 新增 `UNCOMMITTED_CHANGES.md`，完整记录今天的未提交源码、测试、本地化和数据库变更。
  - 记录已通过的后端测试、前端 lint、TypeScript 和本地化键检查。
  - 记录 Next 生产构建受现有 `.next/lock` 占用，未采取破坏性清理操作。
  - 发现 `findings.md` 已处于删除状态，未恢复或覆盖该已有工作区操作。

## Session: 2026-07-10

### Phase 9: Workspace route/layout refactor
- **Status:** complete
- Actions taken:
  - Replaced the large client-side `HomePage` shell/router with a native Next.js `(workspace)` route group and shared layout.
  - Added `WorkspaceShell` for auth/current-user/header/logout responsibilities.
  - Added a concrete `AppSidebar` using `Link` and `usePathname()`.
  - Changed `/` to redirect to `/chat`.
  - Moved project fetching into `/ai-script` and model-config fetching into `/chat` and `/images` only.
  - Removed `activeMenu`, `activeView`, and duplicated route/local navigation state.
- Files created/modified:
  - `frontend/src/app/page.tsx`
  - `frontend/src/app/(workspace)/layout.tsx`
  - `frontend/src/app/(workspace)/_components/app-sidebar.tsx`
  - `frontend/src/app/(workspace)/_components/workspace-shell.tsx`
  - `frontend/src/app/(workspace)/chat/page.tsx`
  - `frontend/src/app/(workspace)/images/page.tsx`
  - `frontend/src/app/(workspace)/ai-script/page.tsx`

### Phase 10: Route-private component colocation and admin consolidation
- **Status:** complete
- Actions taken:
  - Moved all chat-only components under `(workspace)/chat/_components`.
  - Moved the image generation panel under `(workspace)/images/_components`.
  - Removed the duplicate standalone `app/admin` page and shell.
  - Added workspace `/admin` redirect to `/admin/models`.
  - Moved model/user managers into their corresponding admin page `_components` directories.
  - Removed old standalone-admin-only translation keys.
- Files created/modified:
  - `frontend/src/app/(workspace)/chat/_components/*`
  - `frontend/src/app/(workspace)/images/_components/image-generation-panel.tsx`
  - `frontend/src/app/(workspace)/admin/page.tsx`
  - `frontend/src/app/(workspace)/admin/models/page.tsx`
  - `frontend/src/app/(workspace)/admin/models/_components/model-config-manager.tsx`
  - `frontend/src/app/(workspace)/admin/users/page.tsx`
  - `frontend/src/app/(workspace)/admin/users/_components/admin-users-manager.tsx`
  - `frontend/src/lib/i18n.ts`
  - Removed the corresponding old files under `frontend/src/app/chat`, `images`, `ai-script`, and `admin`.

### Phase 11: User management table and admin alignment
- **Status:** complete
- Actions taken:
  - Replaced user cards with a model-management-style table.
  - Added username/ID search, role filter, status filter, and 10-row pagination.
  - Added role/status badges and created/updated timestamps.
  - Kept superAdmin disable/delete controls protected.
  - Added a generic-preserving `filterUsers` helper and Node test.
  - Added Chinese/English user-list translations.
  - Centered actions headers and controls in both user and model management tables.
- Files created/modified:
  - `frontend/src/app/(workspace)/admin/users/_components/admin-users-manager.tsx`
  - `frontend/src/app/(workspace)/admin/users/_components/user-list.ts`
  - `frontend/src/app/(workspace)/admin/users/_components/user-list.test.mts`
  - `frontend/src/app/(workspace)/admin/models/_components/model-config-manager.tsx`
  - `frontend/src/lib/i18n.ts`

### Phase 12: Persistent documentation sync
- **Status:** complete
- Actions taken:
  - Read the `planning-with-files` skill and all three existing project planning files.
  - Updated stale frontend paths and route descriptions in `findings.md`.
  - Recorded workspace/admin decisions, validation results, and all encountered errors.
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

## Session: 2026-07-09

### Phase 7: Dependency cleanup and open-source-first rules
- **Status:** complete
- Actions taken:
  - Audited current frontend/backend dependencies and code paths for hand-rolled or unused pieces.
  - Kept provider/model orchestration on the existing LangChain/LangGraph path.
  - Documented that `google-genai` remains the direct SDK for Gemini native image generation.
  - Confirmed `langchain-google-genai` should only be added if Gemini chat needs a native LangChain provider.
  - Confirmed frontend UI direction: `@base-ui/react` + shadcn-style components is acceptable and should remain the default.
- Files created/modified:
  - `AI_HANDOFF.md`
  - `findings.md`
  - `progress.md`
  - `task_plan.md`

### Phase 8: React i18next migration documentation
- **Status:** complete
- Actions taken:
  - Added `i18next` and `react-i18next` to the frontend.
  - Replaced the custom interpolation code in `frontend/src/lib/i18n.ts` with `i18next` + `initReactI18next` + `useTranslation`.
  - Preserved the existing `useI18n()` facade to avoid touching every page/component.
  - Documented the new localization rule: use open-source i18n plumbing instead of custom string interpolation.
- Files created/modified:
  - `frontend/package.json`
  - `frontend/package-lock.json`
  - `frontend/src/lib/i18n.ts`
  - `AI_HANDOFF.md`
  - `findings.md`
  - `progress.md`
  - `task_plan.md`

## Session: 2026-07-06

### Phase 4: Chat attachments and composer UI
- **Status:** complete
- Actions taken:
  - Read `planning-with-files`, assistant-ui overview, primitives, and runtime skill instructions.
  - Reviewed user screenshots and captured composer UI issues in `findings.md`.
  - Extended `task_plan.md` for the current attachment/UI work.
  - Added `backend/attachment_parser.py` for text/code, PDF, Office OpenXML, ODT, and graceful unparseable notices.
  - Updated chat attachment normalization so `file` parts are parsed into text before being stored and sent to the model.
  - Added `pypdf>=6.1` and installed `pypdf` in the local backend venv.
  - Replaced the limited assistant-ui attachment adapter with a wildcard adapter that accepts all files.
  - Tightened the composer UI into compact wrapping chips plus a ChatGPT-like bottom input row.
- Files created/modified:
  - `backend/attachment_parser.py`
  - `backend/chat_service.py`
  - `backend/requirements.txt`
  - `frontend/src/components/chat/assistant-composer.tsx`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 5: Chat streaming architecture and scroll UX
- **Status:** complete
- Actions taken:
  - Explained Streamdown package responsibilities:
    - `streamdown` renders AI streaming Markdown.
    - `@streamdown/code` adds Shiki-based code highlighting/copy controls.
    - `@streamdown/cjk` improves CJK Markdown/text handling.
  - Added scoped chat message-list scrollbar styling so the message area shows a scrollbar while scrolling.
  - Investigated Vercel AI SDK fit against the existing backend protocol.
  - Confirmed backend was returning custom NDJSON, not AI SDK UI stream.
  - Added `@ai-sdk/react` and `ai`.
  - Converted `frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` from transparent NDJSON passthrough into an AI SDK UI stream translator.
  - Updated `frontend/src/components/chat/use-chat-controller.ts` to use `useChat` and `DefaultChatTransport`.
  - Preserved existing execution-flow display by streaming `agent_step` as transient `data-agent_step`.
  - Deleted old frontend `streamChatMessageAction` hand-written NDJSON reader.
  - Deleted old `ChatStreamEvent` type.
  - Added `isStreaming` to the chat controller return value.
  - Passed `isStreaming` through `chat-panel.tsx` into `chat-message-list.tsx`.
  - Added auto-scroll behavior while the user is near the bottom.
  - Added a floating down-arrow button that appears when the user scrolls away from the bottom.
  - Fixed scroll jitter by canceling pending auto-scroll when the user scrolls upward and only auto-following while near bottom.
  - Later initial-history fix reintroduced `ResizeObserver` only for content growth while follow mode is active, plus `autoScrollKey` and short forced retries for code blocks/lists that finish layout after first paint.
- Files created/modified:
  - `frontend/package.json`
  - `frontend/package-lock.json`
  - `frontend/src/actions/chat-actions.ts`
  - `frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts`
  - `frontend/src/app/globals.css`
  - `frontend/src/components/chat/chat-message-list.tsx`
  - `frontend/src/components/chat/chat-panel.tsx`
  - `frontend/src/components/chat/use-chat-controller.ts`
  - `frontend/src/types/chat.ts`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 6: Chat scroll documentation sync
- **Status:** complete
- Actions taken:
  - Read `planning-with-files` instructions and existing root planning files.
  - Searched project markdown for chat scroll, bottom, `autoScrollKey`, and `ResizeObserver` references.
  - Updated stale docs that said the final scroll implementation avoided `ResizeObserver`.
  - Documented the current behavior: `autoScrollKey`, delayed forced scroll retries, and gated `ResizeObserver` follow-up scrolling.
- Files created/modified:
  - `AI_HANDOFF.md`
  - `findings.md`
  - `progress.md`
  - `task_plan.md`

### Phase 1: Create persistent notes
- **Status:** complete
- **Started:** 2026-07-06
- Actions taken:
  - Read `planning-with-files` instructions and templates.
  - Created root planning files for future AI continuity.
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 2: Inspect project structure
- **Status:** complete
- Actions taken:
  - Listed root directory and repository files.
  - Checked git status.
  - Captured first project map in `findings.md`.
  - Read `AI_HANDOFF.md`, `RUNNING.md`, root `package.json`, backend README/requirements, and frontend package/README.
  - Captured stack, commands, and key product constraints in `findings.md`.
  - Read frontend AI instructions and backend core files: `app.py`, `database.py`, `model.py`, `context_graph.py`, `routers/chat.py`, `routers/projects.py`.
  - Captured backend entry points and backend flow in `findings.md`.
  - Read frontend root layout, home page, chat controller/panel, workbench editor, and chat/project action modules.
  - Captured frontend action/BFF pattern in `findings.md`.
  - Read project/user stores and frontend HTTP clients.
  - Captured frontend store and realtime patterns in `findings.md`.
  - Read backend service layer files and streaming BFF route.
  - Captured backend service boundaries, data model, and known limits in `findings.md`.
  - Checked test/spec file presence, env file presence, backend config defaults, gitignore, Next config, tsconfig, and ESLint config.
  - Captured environment and verification notes in `findings.md`.
- Files created/modified:
  - `findings.md`
  - `task_plan.md`
  - `progress.md`
  - `AI_HANDOFF.md`

### Phase 3: Write handoff summary
- **Status:** complete
- Actions taken:
  - Finalized `findings.md` as the main project map for future AI sessions.
  - Updated `task_plan.md` to complete.
  - Added a 2026-07-06 continuation pointer to `AI_HANDOFF.md`.
  - Reviewed planning files and git status.
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
  - `AI_HANDOFF.md`

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| N/A | Documentation task | No runtime test needed | Final docs reviewed | Pass |
| Test file scan | `rg --files -g '*test*' -g '*spec*'` | Identify tests if present | Initial scan found none; `user-list.test.mts` was added on 2026-07-10 | Pass |
| Env file scan | `rg --files -g '.env*'` | Identify env examples without reading secrets | Found `frontend/.env.example` and ignored `frontend/.env.local` | Pass |
| Final doc review | Read `task_plan.md`, `findings.md`, `progress.md`, `AI_HANDOFF.md` top | Planning docs should be coherent | Needed final status cleanup, then updated | Pass |
| Backend compile | `backend/.venv/bin/python -m compileall -q backend` | Python files compile | Passed | Pass |
| Chat service self-check | `backend/.venv/bin/python backend/chat_service.py` | Attachment normalization checks pass | Passed | Pass |
| Frontend type-check | `cd frontend && npx tsc --noEmit` | No TypeScript errors | Passed after moving className wrapper off `ComposerPrimitive.Attachments` | Pass |
| Frontend lint | `cd frontend && npm run lint` | No lint errors | Passed | Pass |
| Attachment parser smoke | `cd backend && .venv/bin/python -c "...attachment smoke test..."` | Text parses and binary reports unparseable | Printed `True` / `True` | Pass |
| Chat scrollbar/AI SDK lint | `cd frontend && npm run lint` | No lint errors | Passed after fixing stream-route syntax and scroll effect lint | Pass |
| Chat scrollbar/AI SDK type-check | `cd frontend && npx tsc --noEmit` | No TypeScript errors | Passed | Pass |
| Next production build | `cd frontend && npm run build` | Finish production build | Stayed at `Creating an optimized production build ...` for over 2 minutes; interrupted | Incomplete |
| Chat scroll doc stale scan | `rg` scan for stale chat-scroll/ResizeObserver phrases in markdown | No stale docs remain | No matches | Pass |
| Markdown diff whitespace check | `git diff --check` | No whitespace errors | Passed | Pass |
| i18n lint | `cd frontend && npm run lint` | No lint errors | Passed | Pass |
| i18n type-check | `cd frontend && npx tsc --noEmit` | No TypeScript errors | Passed | Pass |
| i18n dependency tree | `cd frontend && npm ls react-i18next i18next` | Installed and deduped | `react-i18next@17.0.8`, `i18next@26.3.5` | Pass |
| Workspace/admin lint | `cd frontend && npm run lint` | No lint errors after route moves and table changes | Passed repeatedly, including final action-column alignment | Pass |
| Workspace/admin type-check | `cd frontend && npx tsc --noEmit` | No TypeScript errors | Passed after regenerating stale Next route types and preserving full filtered-user types | Pass |
| User filter logic | `cd frontend && node --no-warnings --experimental-strip-types --test 'src/app/(workspace)/admin/users/_components/user-list.test.mts'` | Combined search/role/status filters select correct users | 1 test passed | Pass |
| Workspace webpack production build | `cd frontend && npm run build -- --webpack` | Routes compile and page data generates | Passed after route split, component colocation, and admin consolidation | Pass |
| Final user-list production build retry | Same webpack command with required network approval | Revalidate after final list change | Could not start because the automatic approval reviewer returned a service-side `404` | Blocked by tooling |
| 2026-07-10 Markdown diff check | `git diff --check` | No whitespace errors | Passed | Pass |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-07-06 | `zsh: no matches found: frontend/src/app/projects/[projectId]/page.tsx` | 1 | Use quotes around bracketed Next.js route paths. |
| 2026-07-06 | `zsh: no matches found: frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` | 2 | Quote all Next dynamic route paths. |
| 2026-07-06 | `pip install pypdf` failed with DNS/network error in sandbox | 1 | Re-ran with approved escalated network permission; installed `pypdf-6.14.2`. |
| 2026-07-06 | Attachment parser smoke test from repo root raised `ModuleNotFoundError: No module named 'attachment_parser'` | 1 | Re-ran from `backend/`, matching backend module import layout. |
| 2026-07-06 | TypeScript rejected `className` on `ComposerPrimitive.Attachments` | 1 | Wrapped attachments in a styled `<div>` guarded by `AuiIf`. |
| 2026-07-06 | `zsh: no matches found: frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` | 1 | Quoted the Next.js dynamic route path. |
| 2026-07-06 | ESLint parsing error: `Argument expression expected` in the BFF stream route | 1 | Closed the `createUIMessageStream(...)` call correctly before passing it to `createUIMessageStreamResponse`. |
| 2026-07-06 | `npm run build` hung in Next/Turbopack production build startup | 1 | Interrupted after more than two minutes with no new output; lint and type-check still passed. |
| 2026-07-06 | React lint error: `Calling setState synchronously within an effect` in `chat-message-list.tsx` | 1 | Moved initial scroll state update into `requestAnimationFrame`. |
| 2026-07-06 | Streaming output caused visible scroll jitter, worse after manual upward scrolling | 1 | Canceled queued auto-scroll on upward wheel and only auto-follow while near bottom; later `ResizeObserver` use is gated by follow state. |
| 2026-07-06 | `zsh: command not found: ResizeObserver` while scanning markdown | 1 | Re-ran `rg` with the pattern in single quotes so backticks were literal text. |
| 2026-07-10 | `apply_patch verification failed: Update file hunk ... is empty` while moving route-private files | 1 | Re-ran moves with small real import/formatting changes so each move had a valid hunk. |
| 2026-07-10 | Next/Turbopack build hung at `Creating an optimized production build ...` | 1 | Interrupted the hung process and switched verification to `next build --webpack`. |
| 2026-07-10 | Webpack build failed with `getaddrinfo ENOTFOUND fonts.googleapis.com` in sandbox | 1 | Re-ran with approved network permission; production build passed. |
| 2026-07-10 | `ps`/`pgrep` process inspection was blocked by sandbox permissions | 1 | Stopped inspecting processes and polled the existing command session directly. |
| 2026-07-10 | `rmdir` reported `src/app/ai-script: No such file or directory` after other empty directories were removed | 1 | Confirmed the directory was already gone; no further action needed. |
| 2026-07-10 | `.next/types` still imported deleted `src/app/admin/page.js` | 1 | Ran a fresh successful Next build to regenerate route types; `tsc` then passed. |
| 2026-07-10 | TypeScript reported `createdAt`/`updatedAt` missing after `filterUsers` | 1 | Made `filterUsers<T extends UserListItem>` generic so the returned rows retain the full `AuthUser` shape. |
| 2026-07-10 | TypeScript rejected `.ts` extension in the Node test import | 1 | Added a scoped `@ts-expect-error` documenting Node type-stripping behavior. |
| 2026-07-10 | Node rejected `--experimental-default-type=module` | 1 | Removed that flag and ran with `--no-warnings --experimental-strip-types`. |
| 2026-07-10 | Automatic approval reviewer returned `404` for its review model when starting the final build | 1 | Did not bypass approval; reported the tooling block and retained lint/type/test plus earlier successful builds. |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Complete. |
| Where am I going? | Future AI should read `AI_HANDOFF.md`, `RUNNING.md`, then `findings.md`. |
| What's the goal? | Keep SceneFlow easy to resume while maintaining a simple route-owned frontend architecture. |
| What have I learned? | Stack, commands, entry points, workspace route layout, route-private component ownership, admin list behavior, chat flow, limits, and checks are captured in `findings.md`. |
| What have I done? | Created persistent planning files, captured the project map, improved chat attachments/streaming/scroll UX, replaced `HomePage` with a workspace layout, colocated private components, consolidated admin routes, and upgraded user management to a filtered table. |

## Session: 2026-07-21 — Balance Enforcement and Usage Audit

### Phase 1: Discovery and business-flow audit

- **Status:** complete
- Actions taken:
  - Read the `planning-with-files` skill and templates.
  - Preserved existing planning history and created the missing `findings.md`.
  - Captured the requested balance, model-source accounting, refresh, default-level, filter-reset, testing, and logging requirements.
  - Traced all `record_usage` callers and both official-model resolution paths.
  - Confirmed the current defect: official calls are billed only after completion, with no zero-balance preflight.
  - Confirmed personal configurations are already usage-counted without balance deduction; no pricing exists for honest monetary estimation.
  - Confirmed redemption already refreshes both global Zustand state and React Query `me`; a new state machine is unnecessary.
  - Found shared FastAPI error-detail handling missing in `resolveRequestError`.
  - Audited usage source filtering, user-create default level, and list filter reset behavior.
  - Chose a shared backend balance-policy function called at provider boundaries, with chat validation before message persistence.
  - Identified the existing usage tests as the smallest place to cover official zero-balance rejection, super-admin bypass, personal-config allowance, and source filtering.
  - Added the requested backend architecture audit.
  - Chose a focused `tests/` + `services/` reorganization and skipped an empty speculative `plugins/` layer.
  - Moved eight business service modules to `backend/services/`, shared parser/time-ID helpers to `backend/lib/`, and all ten self-checks to `backend/tests/`.
  - Added `backend/tests/run_all.py` and documented the new layout in `backend/README.md`.
  - Updated imports across routers, services, tests, model code, database, and helpers.
  - Ran the new backend test runner, Python compile check, frontend lint, and TypeScript check successfully.
  - Rechecked the custom backend error envelope and corrected the audit note: it uses `error`; the frontend now supports both `error` and standard `detail`.
  - Visually reviewed the modified filter and create-user form composition in source.
  - Audited all remaining status-filter list pages and found model management plus AI project list still lacked reset controls.
  - Identified and scheduled removal of the AI project page's nonfunctional advanced-filter button.
  - Added reset controls to model management and the AI project list; replaced the dead advanced-filter action.
  - Added chat, image, usage-source, balance-message, personal-config, super-admin, redemption, and default-level regression coverage.
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Test Results

| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Pending audit baseline | Backend/frontend targeted checks | Establish current behavior before edits | Pending | Pending |
| Backend reorganized self-checks | `.venv/bin/python tests/run_all.py` | All ten tests pass from `tests/` | Passed | Pass |
| Backend compile | `.venv/bin/python -m compileall -q .` | No import/syntax errors after moves | Passed | Pass |
| Frontend lint/type-check | `pnpm lint && pnpm exec tsc --noEmit` | New filters/forms compile cleanly | Passed | Pass |
| Official chat zero balance | `tests/test_chat_balance.py` | Reject before saving user message | HTTP 402; message count remains 0 | Pass |
| Personal chat zero balance | `tests/test_chat_balance.py` | Allow and save message | Message saved | Pass |
| Official image zero balance | `tests/test_images.py` | Provider is not called | HTTP 402; await count 0 | Pass |
| Official image after credit | `tests/test_images.py` | Provider call proceeds | Image response returned | Pass |
| Usage source filters | `tests/test_usage_service.py` | Official/user summaries isolate records | One call in each filtered result | Pass |
| New user default level | `tests/test_admin_users.py` | Level defaults to 1 | Level is 1 | Pass |
| Final backend suite | `.venv/bin/python tests/run_all.py` | All executable self-checks pass | Passed | Pass |
| Backend app import | `.venv/bin/python -c 'from app import app; ...'` | Reorganized imports load app | Passed | Pass |
| Final Python compile | `.venv/bin/python -m compileall -q .` | No syntax/import compilation failures | Passed | Pass |
| Final frontend lint | `pnpm lint` | No lint errors | Passed | Pass |
| Final frontend type-check | `pnpm exec tsc --noEmit` | No type errors | Passed | Pass |
| Final diff/import scan | `git diff --check` + stale flat import `rg` | Clean diff and no old service paths | Passed | Pass |

### Final Files and Behavior

- Backend:
  - `services/`: business services and balance/usage policy.
  - `lib/`: attachment parser and small shared utilities.
  - `tests/`: eleven executable regression files plus `run_all.py`.
  - Official model calls now require positive balance for ordinary users; personal configs and super admins bypass the balance gate.
  - Usage logs support `all`, `official`, and `user` source filtering.
- Frontend:
  - Usage log source filter and reset control.
  - Reset controls for user, invitation, redemption, model, and AI-project lists.
  - User creation visibly defaults level to 1 and submits it.
  - Redemption continues updating global Zustand + React Query account state immediately.
  - Nonfunctional advanced-filter UI was removed.
- Documentation:
  - `backend/README.md`, `task_plan.md`, `findings.md`, and `progress.md` updated.

### Error Log

| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-07-21 | `findings.md` was missing | 1 | Recreated the required planning file and preserved the existing plan/progress files. |
| 2026-07-21 | `apply_patch` could not find the expected findings section | 1 | Re-read `findings.md` and patched against the actual section order. |
| 2026-07-21 | Architecture findings patch used the wrong section position | 1 | Patched the current file structure directly and stopped assuming section order. |
| 2026-07-21 | TypeScript rejected string arrays passed to Base UI Select `items` | 1 | Replaced them with `{ value, label }` arrays. |

## Session: 2026-07-21 — AI 短剧 / 漫剧产品与技术调研

### Phase 1: 仓库与现状盘点

- **Status:** complete
- Actions taken:
  - 读取 `planning-with-files` 说明与模板。
  - 检查并保留现有 `task_plan.md`、`findings.md`、`progress.md` 历史。
  - 建立本次调研的范围、阶段和初始技术假设。
  - 读取仓库状态、前后端依赖、运行说明与前端 Next.js 约束。
  - 确认 `backend/sceneflow.db` 是本轮开始前的既有修改，后续保持不动。
  - 扫描生成、项目、分镜、对话、模型、用量和实时进度相关代码。
  - 初步确认独立图片/视频生成已接真实模型，而项目音频和项目成片仍为模拟实现。
  - 读取项目 API、生成服务、数据库 schema、前端项目类型与工作台交互。
  - 确认当前持久化模型和异步机制不足以支撑可恢复的多阶段短剧生产任务。
  - 尝试 GitHub 泛关键词检索；因噪声过高，改用定向候选核验。
  - GitHub API 后续受 DNS/审批服务异常影响，浏览器又明确禁止 GitHub；已记录限制并停止尝试该域名。
  - 搜索引擎和部分产品官网也受浏览策略限制；确定不写无法实时核验的热度/价格数字。
  - 确定用两份根目录 Markdown 交付产品与技术方案。
  - 收录用户补充的全链路开源、核心模型与商业平台候选清单。
  - 再次尝试用户明确提供的 GitHub/Gitee 地址，仍被浏览策略拒绝；停止外部访问并保留核验标记。
  - 生成 `AI_SHORT_DRAMA_PRODUCT.md`，包含对标、业务流程、双模式、功能阶段、页面、指标与 MVP 验收。
  - 生成 `AI_SHORT_DRAMA_TECHNICAL.md`，包含现状、架构、数据模型、持久化任务、模型适配、一致性、TTS/字幕/FFmpeg、API、测试与实施顺序。
  - 将用户提供的开源/商业候选及其推定业务流程并入两份文档，所有未能打开原站的易变信息均标为待核验。
  - 运行 `git diff --check` 通过，并检查两份文档标题结构。
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
  - `AI_SHORT_DRAMA_PRODUCT.md`
  - `AI_SHORT_DRAMA_TECHNICAL.md`

### Test Results

| Test | Expected | Actual | Status |
|---|---|---|---|
| `git diff --check` | Markdown 无空白错误 | 无输出 | Pass |
| 文档结构扫描 | 产品/技术章节完整 | 400/526 行，章节结构完整 | Pass |

## Session: 2026-07-21 — AI 短剧 / 漫剧可执行开发技术方案

### Phase 1: 当前实现复核

- **Status:** complete
- Actions taken:
  - 重新读取 `planning-with-files` 说明。
  - 完整读取现有技术方案与当前工作区状态。
  - 确认本轮直接增强现有技术文档，不新增重复方案文件。
  - 发现模型配置、数据库、用量和管理 UI 存在未提交修改，安排在方案定稿前复核。
  - 读取当前模型配置统一迁移 diff、项目 API/服务、视频服务、项目类型/actions/store。
  - 确认开发方案必须兼容正在进行的统一 `model_configs` 改造，并缩小 Zustand 的未来职责。
  - 核对配置 purpose、统一模型表、数据库迁移、项目列表、工作台和场景卡实现。
  - 确认 `audio` purpose 尚缺完整链路，并决定 MVP 先将现有 `scenes` 直接演进为镜头，避免立即引入两级场/镜头模型。
  - 定位项目 WebSocket 和事件处理集中在 `workbench-editor.tsx`，确定先抽项目控制器 hook。
  - 核对现有后端自检体系与前端测试现状，确定只新增项目/job/合成及状态 reducer 的最小检查。
  - 首次大型文档补丁因一处上下文不匹配失败；已记录并改用分段补丁。
  - 文档扫描发现一处尾随空格和两处旧 shot 术语，已统一修正。
  - 将 `AI_SHORT_DRAMA_TECHNICAL.md` 升级为 V0.2 可执行开发方案。
  - 新增 DR-01 至 DR-12 需求清单和前端/后端/数据/验收追踪矩阵。
  - 新增前端组件、类型、actions/query、状态职责和检查方案。
  - 新增后端迁移、模型/TTS、服务、worker、API、FFmpeg 和测试方案。
  - 新增 Stage 0–6 纵向开发顺序、联调流程和最终 Definition of Done。
  - 运行 `git diff --check` 通过，并确认文档不存在旧 `/shots`、`shot_id`、`SHOT_UPDATE` 残留。
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
  - `AI_SHORT_DRAMA_TECHNICAL.md`

### Verification

| Check | Result |
|---|---|
| `git diff --check` | Pass |
| 技术文档结构 | 822 行，需求/前端/后端/阶段/DoD 章节齐全 |
| 旧 shot 术语扫描 | 无 `/shots`、`shot_id`、`SHOT_UPDATE` 残留 |

## Session: 2026-07-21 — AI 漫剧 / 短剧开发启动

### Phase 0: 基线与冲突审计

- **Status:** complete
- Actions taken:
  - 读取 `planning-with-files` 与 pnpm 技能说明。
  - 确定首个纵向切片为项目生产设置与持久化 generation jobs。
  - 明确具体供应商暂不硬编码，保留后续模型配置入口。
  - 检查工作树与 pnpm/Next.js 约束；确认当前业务代码无未提交冲突，只有 planning 文档变更。
  - 基线后端全测、前端 lint/type-check 通过。
  - 读取数据库迁移、项目 API/服务、serializer、应用入口和测试 runner，确定增量实现边界。
  - 首次项目 API 补丁因错误的占位 import 上下文失败；改为精确分段补丁。
  - 后端项目生产设置、generation job schema/service/API 和对应自检已实现，后端全量测试通过。
  - 读取前端项目 types/actions/store/workbench，确定用一个路由私有设置组件完成 DR-01 UI。
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 1: 生产设置与任务基础

- **Status:** complete
- Actions taken:
  - 为项目增加漫剧/真人短剧模式、画幅、分辨率、帧率、目标时长、语言、统一风格提示词、负面提示词和当前阶段。
  - 增加兼容旧 SQLite 数据库的增量迁移与服务层输入校验。
  - 增加生产设置更新 API，并让项目创建、读取和前端 store 全链路支持新字段。
  - 在项目工作台增加生产设置表单，中英文文案齐全，保存成功后即时更新本地项目状态。
  - 新增持久化 generation jobs 表及入队、幂等、取消、重试、租约领取、完成等服务能力。
  - 新增项目任务列表、任务取消与重试 API，并广播任务更新事件。
  - 后端全量测试、compileall、前端 lint/type-check 和 diff 检查全部通过。
- Files created:
  - `backend/app/api/v1/jobs.py`
  - `backend/app/services/job_service.py`
  - `backend/tests/test_job_service.py`
  - `backend/tests/test_project_production.py`
  - `frontend/src/app/projects/[projectId]/_components/production-settings.tsx`

### Phase 2: 可配置 TTS 与本地免费语音

- **Status:** complete
- Actions taken:
  - 将 `audio` 加入统一模型用途和模型管理界面。
  - 支持 OpenAI 兼容 `/audio/speech` TTS 配置。
  - 内置 macOS `say` / Linux `espeak-ng` 免费系统语音回退，无需 API Key。
  - 将原有场景假音频 URL 替换为真实 WAV 文件生成与持久化。
  - 工作台显示当前 TTS 配置；未配置时明确显示内置免费系统语音。
  - 增加 TTS 配置及系统命令选择测试，并完成真实本机语音冒烟测试。
  - 新增 Edge-TTS 免费供应商及默认中文音色 `zh-CN-XiaoxiaoNeural`，服务不可达时自动回退本地系统语音。

### Phase 3: 产品与技术文档同步

- **Status:** complete
- Actions taken:
  - 按 `planning-with-files` 重新读取计划、发现、进度、产品文档和技术文档。
  - 将技术方案升级为 V0.3，新增当前已完成/未完成清单。
  - 更新 DR-01、DR-06、DR-07 追踪矩阵、数据库/TTS 服务边界、阶段计划和当前到目标差异。
  - 更新产品文档中的 TTS 能力、待确认问题和当前已完成功能。
  - 修正 planning 文档中仍处于 pending、仍把 TTS 列为 deferred 的过时状态。
- Files modified:
  - `AI_SHORT_DRAMA_PRODUCT.md`
  - `AI_SHORT_DRAMA_TECHNICAL.md`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 4: 前后端结构与业务审计

- **Status:** complete
- Actions taken:
  - 审查数据库迁移、项目设置、generation jobs、模型配置、TTS、工作台和模型管理调用链。
  - 修复图片配置错误回退、项目级幂等范围、TTS 兼容字段、Linux 回退音色和 API Key 残留。
  - 使用现有 FFprobe 获取真实音频时长，不引入许可证不合适的解析依赖。
  - 统一前后端目标时长范围，并增加画幅/宽高一致性校验和默认尺寸推导。
  - 明确 LangGraph 与持久化 worker 的混合编排边界，并更新技术方案和后端 README。
  - 后端全测/compileall、前端 lint/type-check 和 diff 检查通过。

## Session: 2026-07-21 — 模型配置、邀请码/兑换码与图片单价修复

### Phase 1: 统一模型配置表与来源切换

- **Status:** complete
- Actions taken:
  - 将个人配置表与官方配置表合并为 `model_configs`。
  - 以 `source` 和 `user_id` 区分官方配置与个人配置。
  - 增加兼容旧数据库的自动迁移、配置 ID 重映射，以及默认模型和会话引用迁移。
  - 调整管理端模型 API，使现有配置可以直接切换来源而无需重新创建。
  - 在临时数据库和真实数据库副本中执行迁移验证，外键检查无错误。
- Main files involved:
  - `backend/app/core/database.py`
  - `backend/app/api/v1/admin.py`
  - `backend/app/api/v1/settings.py`
  - `backend/app/services/config_service.py`
  - `backend/app/services/chat_service.py`
  - `backend/app/services/usage_service.py`
  - `backend/app/schemas/serializers.py`
  - `backend/tests/test_config_service.py`
  - `frontend/src/app/(workspace)/admin/models/_components/model-config-manager.tsx`

### Phase 2: 邀请码与兑换码审计信息

- **Status:** complete
- Actions taken:
  - 为 `invitation_codes`、`redemption_codes` 增加 `created_by_user_id` 兼容迁移。
  - 新生成记录保存当前管理员，列表 API 返回 `createdBy`。
  - 邀请码列表新增使用时间和创建人；兑换码列表新增创建人并保留兑换时间。
  - 旧记录缺少可靠创建人时显示 `—`。
  - 增加邀请码、兑换码创建人回归测试。
- Main files involved:
  - `backend/app/core/database.py`
  - `backend/app/api/v1/admin.py`
  - `backend/tests/test_invitation_codes.py`
  - `backend/tests/test_redemption_codes.py`
  - `frontend/src/types/admin.ts`
  - `frontend/src/lib/i18n.ts`
  - `frontend/src/app/(workspace)/admin/invitation-codes/_components/invitation-code-manager.tsx`
  - `frontend/src/app/(workspace)/admin/redemption-codes/_components/redemption-code-manager.tsx`

### Phase 3: 图片单价输入与保存

- **Status:** complete
- Actions taken:
  - 将模型计费输入状态由 `number` 改为 `string`，允许清空初始 `0` 后输入新价格。
  - 保存时才通过 `Number(...)` 转换单价。
  - 调整 `normalize_config_payload` 及更新接口，仅在连接字段变化或首次设为默认时调用 `validate_provider`。
  - 增加使用完整管理页 payload 更新图片单价的回归测试，断言不调用外部验证且单价成功保存。
  - 在真实数据库副本中以配置 ID `5`、管理员 ID `2` 调用当前更新逻辑，返回 `unitPrice: 5.0`、`unitName: image`。
- Main files involved:
  - `backend/app/api/v1/admin.py`
  - `backend/app/services/config_service.py`
  - `backend/tests/test_config_service.py`
  - `frontend/src/app/(workspace)/admin/models/_components/model-config-manager.tsx`

### Verification Results

| Check | Result |
|---|---|
| 后端全量测试 | Pass |
| 前端 `pnpm exec tsc --noEmit` | Pass |
| 前端 `pnpm lint` | Pass |
| 临时数据库统一表迁移与外键检查 | Pass |
| 真实数据库副本迁移与图片单价更新 | Pass |
| `git diff --check` | Pass |

### Runtime Handoff

- 当前监听 `8080` 的后端 PID `58712` 仍是旧进程，未加载最新代码。
- 对该旧进程发送相同 PATCH 会持续等待，前端最终显示 `Internal Server Error`。
- 终止进程的 sandbox 权限请求被拒绝，升级审批又因 `codex-auto-review` 404 失败；没有绕过权限限制。
- 用户需在后端终端执行：先 `Ctrl+C`，再运行 `npm run dev:backend`。

### Error Log

| Timestamp | Error | Attempt | Resolution |
|---|---|---|---|
| 2026-07-21 | 图片单价初始 `0` 无法删除 | 1 | 输入编辑态改为字符串，提交时转换为数字。 |
| 2026-07-21 | 保存完整图片模型参数返回 500 | 1 | 将无条件供应商验证改为按连接字段变化触发。 |
| 2026-07-21 | 旧后端进程未加载修复代码 | 1 | 记录 PID 和手动重启命令，等待用户在运行终端重启。 |
| 2026-07-21 | sandbox 拒绝终止 PID，审批服务返回 404 | 1 | 保持安全边界，不尝试绕过权限。 |

## Session: 2026-07-21 — AI 短剧编排与代码审查文档

- **Status:** complete
- Actions taken:
  - 使用 `planning-with-files` 复核计划、发现、进度和主技术方案。
  - 核实 LangGraph 1.2.7 已由 LangChain 安装，无需新增依赖。
  - 明确 LangGraph 与 generation jobs/worker 的职责边界。
  - 记录人工中断、服务恢复、幂等、租约和版本化回滚流程。
  - 记录本轮前后端代码审查修复项及后续开发顺序。
  - 新增 `AI_SHORT_DRAMA_ORCHESTRATION.md`，并修正主技术方案的过时缺陷描述。
- Files modified:
  - `AI_SHORT_DRAMA_ORCHESTRATION.md`
  - `AI_SHORT_DRAMA_TECHNICAL.md`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
