# Progress Log

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

- **Status:** in_progress
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
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
