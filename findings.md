# Findings & Decisions

## Requirements
- User asked to summarize the current project for sustainable future AI development.
- Use the `planning-with-files` pattern with persistent files in the project root.
- Keep the result useful for resuming work: stack, layout, commands, conventions, and known risks.

## Research Findings
- `planning-with-files` requires `task_plan.md`, `findings.md`, and `progress.md` in the project directory.
- Root has existing continuity docs: `AI_HANDOFF.md` and `RUNNING.md`.
- Project is split into `backend/` and `frontend/`.
- Git worktree already has a modified `backend/sceneflow.db`; leave it untouched unless explicitly asked.
- Backend stack: Python 3.11, FastAPI, uvicorn, SQLite, bcrypt, PyJWT, cryptography, `google-genai`, OpenAI SDK, LangChain, LangGraph.
- Frontend stack: Next.js 16.2.3, React 19.2.4, TypeScript, Tailwind CSS 4, `@base-ui/react`, shadcn-style components, `@assistant-ui/react`, Vercel AI SDK, React Query, Zustand, axios, `i18next`/`react-i18next`.
- Core user constraints from existing handoff:
  - Use `@assistant-ui/react` for mature chat UI capabilities.
  - Backend core should use LangChain and LangGraph instead of custom orchestration where possible.
  - Chat needs follow-up context, memory, 1M token budget, summary compression.
  - Project and scene CRUD must persist in backend SQLite, not frontend-only state.
  - Agent runtime events should stream to the frontend and be visible as execution steps.

## Project Map
- Root:
  - `AI_HANDOFF.md`: existing handoff summary; should be read by future AI sessions.
  - `RUNNING.md`: existing local run instructions; should be read before starting servers.
  - `package.json`, `pnpm-lock.yaml`: root-level package metadata.
  - `backend/`: Python backend.
  - `frontend/`: Next.js-style frontend.
- Backend notable files:
  - `backend/app.py`: FastAPI entry. Adds CORS, mounts `/generated`, includes routers, runs `init_db()` on startup, exposes `/healthz`.
  - `backend/database.py`: SQLite schema and migrations-in-code. Seeds `superAdmin` / `superAdmin@123` every startup.
  - `backend/model.py`: LangChain provider router plus script parse, script optimize, chat streaming, context summarization.
  - `backend/context_graph.py`: LangGraph context loading/compression, `agent_step` runtime events, 1M token budget, keeps last 20 messages after compression.
  - `backend/routers/`: API route modules for auth, users, projects, chat, settings, admin, websocket.
  - `backend/routers/chat.py`: chat session CRUD and NDJSON streaming endpoint. Streams `userMessage`, `agent_step`, `reasoning_delta`, `content_delta`, `assistantMessage`, and error events.
  - `backend/routers/projects.py`: project CRUD, scene reorder/update, parse, optimize, image generation, video generation, soft delete, WebSocket broadcasts.
  - `backend/config_service.py`: normalizes provider/model/baseUrl, validates purpose/provider compatibility, validates API keys through model calls except video.
  - `backend/chat_service.py`: owns chat config selection, session ownership checks, message persistence, and non-stream context assembly.
  - `backend/project_service.py`: validates project ownership and active script model config for parse.
  - `backend/generation_service.py`: async generation task runner. Image generation currently only supports OpenAI; audio and video generation use simulated progress/URLs.
  - `backend/realtime.py`: in-memory WebSocket client registry keyed by project id.
  - `backend/security.py`: JWT auth, superAdmin guard, AES-GCM API key encryption/decryption.
  - `backend/sceneflow.db`: local SQLite database, currently modified.
- Frontend notable files:
  - `frontend/src/app/layout.tsx`: root layout, Chinese locale, app preferences provider, React Query provider.
  - `frontend/src/app/page.tsx`: minimal root route that redirects `/` to `/chat`.
  - `frontend/src/app/(workspace)/layout.tsx`: shared authenticated workspace layout for chat, images, AI script, and admin routes.
  - `frontend/src/app/(workspace)/_components/workspace-shell.tsx`: owns auth hydration, current-user query, top header, logout, and shared workspace frame.
  - `frontend/src/app/(workspace)/_components/app-sidebar.tsx`: concrete application navigation using `Link` + `usePathname()`; no duplicated local active-view state.
  - `frontend/src/app/(workspace)/chat/page.tsx`: fetches model configs only for chat and renders the chat panel.
  - `frontend/src/app/(workspace)/images/page.tsx`: fetches model configs only for image generation and renders the image panel.
  - `frontend/src/app/(workspace)/ai-script/page.tsx`: owns project list fetching, filtering, creation, and navigation.
  - `frontend/src/app/(workspace)/admin/page.tsx`: redirects `/admin` to `/admin/models` inside the workspace shell.
  - `frontend/src/app/projects/[projectId]/page.tsx`: project page entry; read with shell quoting because brackets are glob syntax.
  - `frontend/src/app/(workspace)/chat/_components/use-chat-controller.ts`: chat state machine using Vercel AI SDK `useChat`, session queries, message conversion, and streamed agent-step state.
  - `frontend/src/app/(workspace)/chat/_components/chat-panel.tsx`: route-private chat layout with sidebar, message list, and assistant composer.
  - `frontend/src/app/(workspace)/images/_components/image-generation-panel.tsx`: route-private image generation form, preview, download, and current local history UI.
  - `frontend/src/app/projects/[projectId]/_components/workbench-editor.tsx`: main project editor. Handles project CRUD actions, scene editing/reordering, parse/optimize/generate/video mutations, auth redirects, and WebSocket state updates.
  - `frontend/src/app/(workspace)/admin/models/_components/model-config-manager.tsx`: model config table, filters, edit/view dialogs, default/enabled switches, and actions.
  - `frontend/src/app/(workspace)/admin/users/_components/admin-users-manager.tsx`: user table with search, role/status filters, pagination, status switch, and delete action.
  - `frontend/src/components/`: shared UI primitives and cross-route components only; route-private feature components should stay under their owning app route `_components` folder.
  - `frontend/src/actions/`, `frontend/src/bff/`, `frontend/src/lib/`: client actions, BFF helpers, HTTP/API utilities.
- Frontend action pattern:
  - Components call `src/actions/*`.
  - Actions call `/api/bff/**` through `httpClient` or `fetch` for streaming.
  - Next BFF routes forward to FastAPI backend.
  - `frontend/src/lib/http/client.ts` injects Bearer token from `user-store`; 401 logs out locally.
  - `frontend/src/lib/http/backend-client.ts` points server-side BFF calls at `BACKEND_API_BASE_URL` or `http://127.0.0.1:8080`.
  - Streaming BFF route `frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` translates backend NDJSON into AI SDK UI stream chunks.
- Frontend state pattern:
  - `frontend/src/store/user-store.ts` persists only auth token/user in localStorage.
  - `frontend/src/store/project-store.ts` is an in-memory normalized project/scene cache fed by backend data and WebSocket events.
  - Script and scene edits are optimistic locally, then debounced 500ms to backend.
  - Scene reorder is local first, then persisted through `/scenes/reorder`.
- Realtime pattern:
  - `WorkbenchEditor` opens `ws://127.0.0.1:8080/ws/projects/:id?token=<JWT>` by default.
  - Handles `PROJECT_UPDATE`, `VIDEO_UPDATE`, `PROJECT_DELETED`, and `SCENE_UPDATE`.

## Data Model
- SQLite tables are created/migrated in `backend/database.py`, not by Alembic.
- Important tables:
  - `users`
  - `user_configs`
  - `official_model_configs`
  - `user_official_config_defaults`
  - `projects`
  - `scenes`
  - `chat_sessions`
  - `chat_messages`
- Soft delete convention: `deleted_at IS NULL` filters active rows.
- Chat memory columns: `chat_sessions.context_summary`, `chat_sessions.context_summary_until`.
- API keys are encrypted before storage and decrypted only server-side.

## Environment / Config
- Backend env defaults are in `backend/config.py`:
  - `PORT=8080`
  - `SCENEFLOW_DB_PATH=./sceneflow.db`
  - `SCENEFLOW_JWT_SECRET=dev-jwt-secret-change-me`
  - `SCENEFLOW_AES_KEY=dev-aes-key-change-me`
  - `SCENEFLOW_PUBLIC_BASE_URL=http://127.0.0.1:8080`
  - `SCENEFLOW_GENERATED_DIR=./generated`
- Frontend env files present:
  - `frontend/.env.example`
  - `frontend/.env.local` exists locally and is ignored; do not read or commit local secrets.
- `.gitignore` excludes `.env*`, `node_modules`, Next outputs, Python venv/cache, `backend/*.db`, and TS build info.
- `frontend/next.config.ts` enables React Compiler and `code-inspector-plugin` for Turbopack.
- `frontend/tsconfig.json` has `strict: true`, `noEmit: true`, `moduleResolution: bundler`, and `@/* -> ./src/*`.

## Known Limits / Sharp Edges
- `backend/sceneflow.db` is local mutable data and already dirty in git status; do not overwrite or reset casually.
- `backend/*.db` is ignored, so DB changes usually represent local dev state, not source edits.
- Generated files go under `backend/generated` by default and are served from `/generated`.
- WebSocket registry is process-local memory; multi-process deployment would need a shared pub/sub layer.
- Image generation supports OpenAI and Gemini providers; generated files are persisted under the configured generated directory.
- Audio generation and video generation currently simulate output URLs/progress.
- Next.js dynamic route paths contain brackets; quote them in shell commands.

## Development Commands
- Backend setup:
  - `cd backend`
  - `python3.11 -m venv .venv`
  - `source .venv/bin/activate`
  - `pip install -r requirements.txt`
- Backend dev server:
  - `cd backend && .venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8080`
  - Health check: `http://127.0.0.1:8080/healthz`
- Frontend setup:
  - `cd frontend`
  - `npm install`
  - Copy `.env.example` to `.env.local` if needed.
- Frontend dev server:
  - `cd frontend && npm run dev`
  - Default URL: `http://localhost:3000`
- Useful checks from existing handoff:
  - `cd backend && .venv/bin/python -m compileall -q *.py routers`
  - `cd frontend && npm run lint`
  - `cd frontend && npx tsc --noEmit`
  - `cd frontend && npm run build`
- Root shortcuts:
  - `npm run dev:backend`
  - `npm run dev:frontend`

## Tests / Checks
- Most validation remains compile/lint/type/build based.
- `frontend/src/app/(workspace)/admin/users/_components/user-list.test.mts` is a small Node test for combined user search/role/status filtering.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Persist findings in root markdown files | Future AI sessions can recover state without relying on chat context. |
| Reuse `AI_HANDOFF.md` and `RUNNING.md` as primary sources | They already capture user constraints, completed work, and run commands. |
| Treat frontend docs as partly stale | `frontend/README.md` says project data uses session store, but newer handoff says project/scene CRUD now persists in backend SQLite. |
| Before changing Next.js code, read local Next docs under `node_modules/next/dist/docs/` | `frontend/AGENTS.md` warns this Next version has breaking changes versus older training data. |
| Before changing assistant-ui patterns, use assistant-ui docs/MCP if available | `frontend/CLAUDE.md` explicitly calls out assistant-ui project patterns. |
| Open-source/library first | Before building a general-purpose feature, check project dependencies, platform APIs, and mature open-source packages. Use the right library directly instead of hand-rolling. |
| Keep `@base-ui/react` + shadcn-style UI | Base UI primitives are acceptable for interaction/accessibility foundations; keep shadcn-style composition for readable local UI components. |
| Keep `google-genai` for Gemini native image generation | It is the direct SDK path currently used by the app. Add `langchain-google-genai` only if Gemini chat needs native LangChain provider behavior. |
| Use `react-i18next` for UI localization | Replaces hand-written interpolation in `frontend/src/lib/i18n.ts` while keeping the local `useI18n()` facade for low-churn call sites. |
| Use a `(workspace)` route group and shared layout | Native Next.js layout composition keeps URLs unchanged while sharing auth, sidebar, and header. |
| Derive sidebar active state from `usePathname()` | URL is the source of truth; removes `HomePage`/`activeView` state synchronization. |
| Keep route-private components beside their pages | Chat, image, model-admin, and user-admin components now live under their owning `_components` folders. |
| Keep `/admin` as a redirect rather than a second admin UI | Preserves old links without maintaining duplicate auth/navigation/management code. |
| Keep user list filtering and pagination client-side for now | The current admin API returns the complete small user set; page size 10 bounds rendered rows. |

## Development Principles
- Before coding, ask: is this already in the codebase, stdlib/platform, or an installed/mature open-source library?
- Prefer installing and using a suitable open-source library over writing custom generic infrastructure.
- Do not add abstractions for future possibilities. Keep modules small, named clearly, and aligned with existing frontend actions/BFF/backend service boundaries.
- Code should be easy for a human or AI to continue: explicit file ownership, simple data flow, small diffs, and no hidden side effects.
- Keep validation, auth, persistence, and user-data safety explicit; do not simplify away safety boundaries.

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Shell failed to read `frontend/src/app/projects/[projectId]/page.tsx` because zsh expanded brackets | Quote bracketed paths, e.g. `sed -n '1,160p' 'frontend/src/app/projects/[projectId]/page.tsx'`. |
| Same shell glob issue repeated on a BFF stream route | Quote all Next dynamic route paths before running shell commands. |
| Move-only `apply_patch` hunks were rejected as empty | Include a small real import/formatting edit in the same move patch. |
| Turbopack production build hung without progress | Interrupt the hung session and use `next build --webpack` for deterministic verification. |
| Webpack build could not fetch Google Fonts in the sandbox | Use approved network access for the existing `next/font` download; the build then passed. |
| `.next/types` retained the removed standalone admin route | Rebuild Next output before rerunning standalone `tsc`. |
| Final build approval review returned a service-side `404` | Do not bypass approval; report that the build could not start and rely on successful lint/type/test plus earlier builds. |

## Resources
- `/Users/torresli/Documents/other/SceneFlow`
- `/Users/torresli/.cc-switch/skills/planning-with-files/SKILL.md`
- `/Users/torresli/Documents/other/SceneFlow/AI_HANDOFF.md`
- `/Users/torresli/Documents/other/SceneFlow/RUNNING.md`
- `/Users/torresli/Documents/other/SceneFlow/backend/README.md`
- `/Users/torresli/Documents/other/SceneFlow/frontend/README.md`
- `/Users/torresli/Documents/other/SceneFlow/task_plan.md`
- `/Users/torresli/Documents/other/SceneFlow/findings.md`
- `/Users/torresli/Documents/other/SceneFlow/progress.md`

## Visual/Browser Findings
- 2026-07-06 chat composer screenshots: current attachment preview appears as a wide full-row input-like bar, making the bottom composer feel visually heavy and confusing.
- Desired composer direction: closer to ChatGPT, with compact attachment chips inside the composer, a simple paperclip/input/send row, and no visible explanatory helper text.

## Workspace Routing and Admin UI Findings
- 2026-07-10 the previous `HomePage` was both a client router and a page shell: it statically imported chat, images, project list, and admin managers, duplicated URL state in `activeView`, and ran unrelated queries on every route.
- Current workspace routes are grouped under `frontend/src/app/(workspace)`; the group name does not appear in URLs.
- The shared workspace layout covers `/chat`, `/images`, `/ai-script`, `/admin`, `/admin/models`, and `/admin/users`; login/register and the project workbench remain outside this shell.
- The application sidebar is intentionally concrete rather than configurable. Add a generic sidebar abstraction only if a second independent app shell appears.
- Project list data is fetched only by `/ai-script`; user model configs are fetched only by `/chat` and `/images`.
- Standalone `frontend/src/app/admin` was removed because it duplicated model/user managers and had no unique entry or capability.
- User management now matches the model-management table pattern:
  - username/ID search;
  - role and enabled/disabled filters;
  - 10-row client pagination;
  - role/status badges;
  - created/updated timestamps;
  - inline enabled switch and delete action;
  - superAdmin rows are protected from disable/delete.
- User filtering lives in `user-list.ts` and preserves the full row type through a generic helper; `user-list.test.mts` checks combined search/role/status behavior.
- The actions headers and inline controls in both user and model tables are horizontally centered.

## Chat Attachment Findings
- User wants uploads to accept all files, including code files such as `.py`.
- Implemented behavior: assistant-ui custom `AttachmentAdapter` accepts `*`.
- Frontend parses images as image parts and text/code files as text parts.
- Frontend sends PDF/Office/other non-text files as `file` data URL parts for backend parsing.
- Backend `attachment_parser.py` parses text/code, PDF via `pypdf`, and Office OpenXML `.docx/.xlsx/.pptx` via stdlib zip/XML extraction.
- Unsupported formats, old binary Office `.doc/.xls/.ppt`, scanned PDFs, malformed data, or missing parser dependencies degrade to an explicit Chinese "无法解析该文件" attachment note.
- `pypdf` is now listed in `backend/requirements.txt` and was installed in the local backend venv during this session.

## Chat Streaming and Scroll UX Findings
- 2026-07-06 user asked why the frontend did not use Vercel AI SDK for chat processing.
- Existing backend stream protocol before the migration was custom NDJSON from FastAPI:
  - `userMessage`
  - `agent_step`
  - `reasoning_delta`
  - `content_delta`
  - `assistantMessage`
  - `error`
- Vercel AI SDK `useChat` cannot consume that custom NDJSON directly; it expects AI SDK UI stream/SSE chunks.
- Minimal working split chosen:
  - Keep Python backend model calls, LangChain/LangGraph orchestration, session creation, DB persistence, and context compression unchanged.
  - Make the Next BFF stream route translate backend NDJSON into AI SDK UI stream chunks.
  - Use `@ai-sdk/react` `useChat` and `ai` `DefaultChatTransport` in the frontend controller.
  - Keep Assistant UI for composer/rendering primitives.
- Added dependencies:
  - `@ai-sdk/react`
  - `ai`
- Updated BFF stream route:
  - File: `frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts`
  - Reads backend NDJSON.
  - Emits AI SDK chunks: `start`, `reasoning-start`, `reasoning-delta`, `reasoning-end`, `text-start`, `text-delta`, `text-end`, `message-metadata`, `finish`, and `error`.
  - Emits `agent_step` as transient `data-agent_step` so execution-flow UI can update without polluting assistant message content.
- Updated frontend chat controller:
  - Current file: `frontend/src/app/(workspace)/chat/_components/use-chat-controller.ts` (moved from the earlier shared-components path on 2026-07-10).
  - Uses `useChat<SceneFlowUIMessage>()`.
  - Uses `DefaultChatTransport` with `prepareSendMessagesRequest` to send the existing payload shape: `content`, `attachments`, `configId`, `officialConfigId`.
  - Converts persisted `ChatMessage` records to AI SDK `UIMessage` for display and back to local `ChatMessage` shape for existing components.
  - Exposes `isStreaming` separately from `messagesLoading`; `messagesLoading` means history fetch, not SSE output.
- Removed old hand-written frontend stream reader:
  - File: `frontend/src/actions/chat-actions.ts`
  - Deleted `streamChatMessageAction`.
  - Deleted now-unused `ChatStreamEvent` from `frontend/src/types/chat.ts`.
- Streamdown package meanings:
  - `streamdown`: AI-streaming-friendly Markdown renderer, roughly a streaming replacement for `react-markdown`.
  - `@streamdown/code`: Streamdown code-block plugin using Shiki syntax highlighting; current UI enables copy and disables download.
  - `@streamdown/cjk`: CJK-friendly Markdown/text handling for Chinese/Japanese/Korean content.
- Chat message list scrollbar:
  - Current file: `frontend/src/app/(workspace)/chat/_components/chat-message-list.tsx` (moved on 2026-07-10).
  - Root scroller uses dedicated `chat-message-list-scrollbar`.
  - CSS lives in `frontend/src/app/globals.css`.
  - Scrollbar styles are scoped to chat messages rather than all scroll containers.
- Auto-scroll behavior:
  - While the user is near the bottom, streaming output auto-scrolls to the newest content.
  - If the user scrolls upward, auto-follow stops immediately and a floating down-arrow button appears.
  - Clicking the down-arrow scrolls to the bottom and resumes auto-follow.
  - History initialization/session switches use `autoScrollKey` and short forced scroll retries so code blocks, Shiki highlighting, and ordered lists that grow after first paint still end at the true bottom.
  - `ResizeObserver` is used only while `shouldFollowRef` is true; upward wheel input cancels follow and pending forced retries to avoid fighting manual scroll.
- Current verification for this work:
  - `cd frontend && npm run lint`
  - `cd frontend && npx tsc --noEmit`
- Known caveats:
  - `npm run build` was attempted after AI SDK integration but hung at Next/Turbopack production build startup for over two minutes; it was interrupted.
  - `npm install @ai-sdk/react ai` reported 12 npm audit findings; not addressed in this pass.
  - Full backend migration to Vercel AI SDK was explicitly skipped; current backend remains Python/FastAPI/LangChain/LangGraph.

## Chat Initial Scroll Fix Documentation Sync
- 2026-07-06 latest chat scroll code uses an `autoScrollKey` derived from session id, message count, and last message id.
- `ChatMessageList` force-scrolls on initial history load/session message-key changes and retries shortly after layout (`50ms`, `150ms`, `350ms`) so Streamdown code blocks, Shiki highlighting, and ordered lists that grow after first paint do not leave history views mid-scroll.
- `ResizeObserver` is now used only to keep following when content height changes and `shouldFollowRef` is still true; upward wheel input cancels follow and pending retries. Older docs that said the final implementation avoided `ResizeObserver` were updated in this sync.

## Recent Cleanup and i18n Findings
- 2026-07-09 cleanup pass favored existing/open-source tools over custom code.
- Removed the old hand-written i18n interpolation path from `frontend/src/lib/i18n.ts`.
- Added `i18next` and `react-i18next`; current `useI18n()` wraps `useTranslation()` and syncs language from `preferences-store`.
- `frontend/src/lib/i18n.ts` still keeps translations in one file because there are only two locales and the existing call surface is small enough; split locale JSON files when translation volume grows.
- Frontend `shadcn` CLI should not be a runtime dependency. Root-level shadcn CLI is enough for component generation.
- `@base-ui/react` remains the preferred primitive layer for local shadcn-style UI components.
- `google-genai` remains appropriate for Gemini image generation; `langchain-google-genai` is not needed unless Gemini chat moves to native LangChain provider integration.
