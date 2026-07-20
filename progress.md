# Progress Log

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
