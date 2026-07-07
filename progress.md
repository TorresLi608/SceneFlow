# Progress Log

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
| Test file scan | `rg --files -g '*test*' -g '*spec*'` | Identify tests if present | No test/spec files found | Pass |
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

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Complete. |
| Where am I going? | Future AI should read `AI_HANDOFF.md`, `RUNNING.md`, then `findings.md`. |
| What's the goal? | Summarize SceneFlow for future AI development. |
| What have I learned? | Stack, commands, entry points, data model, chat attachment flow, AI SDK stream bridge, current scroll behavior, limits, and checks are captured in `findings.md`. |
| What have I done? | Created persistent planning files, updated `AI_HANDOFF.md`, captured the project map, improved chat attachments/composer UI, integrated AI SDK for frontend stream state, fixed chat scroll UX, and synced scroll docs. |
