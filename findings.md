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
- Backend stack: Python 3.11, FastAPI, uvicorn, SQLite, bcrypt, PyJWT, cryptography, httpx, LangChain, LangGraph.
- Frontend stack: Next.js 16.2.3, React 19.2.4, TypeScript, Tailwind CSS 4, shadcn/ui-style components, `@assistant-ui/react`, React Query, Zustand, axios.
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
  - `frontend/src/app/page.tsx`: logged-in home shell. Left nav toggles Chat and AI Script project list. Uses user/project stores plus React Query actions.
  - `frontend/src/app/projects/[projectId]/page.tsx`: project page entry; read with shell quoting because brackets are glob syntax.
  - `frontend/src/components/`: UI, chat, workbench, settings components.
  - `frontend/src/components/chat/use-chat-controller.ts`: chat state machine. Picks usable configs, handles sessions, consumes NDJSON streaming events, accumulates reasoning/content deltas, stores agent steps.
  - `frontend/src/components/chat/chat-panel.tsx`: chat layout with sidebar, message list, assistant composer.
  - `frontend/src/components/workbench/workbench-editor.tsx`: main project editor. Handles project CRUD actions, scene editing/reordering, parse/optimize/generate/video mutations, auth redirects, and WebSocket state updates.
  - `frontend/src/actions/`, `frontend/src/bff/`, `frontend/src/lib/`: client actions, BFF helpers, HTTP/API utilities.
- Frontend action pattern:
  - Components call `src/actions/*`.
  - Actions call `/api/bff/**` through `httpClient` or `fetch` for streaming.
  - Next BFF routes forward to FastAPI backend.
  - `frontend/src/lib/http/client.ts` injects Bearer token from `user-store`; 401 logs out locally.
  - `frontend/src/lib/http/backend-client.ts` points server-side BFF calls at `BACKEND_API_BASE_URL` or `http://127.0.0.1:8080`.
  - Streaming BFF route `frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` passes the backend response body through unchanged.
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
- Image generation supports OpenAI provider only.
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
- No test/spec files were found by `rg --files -g '*test*' -g '*spec*'`.
- Existing validation surface is mostly compile/lint/type/build commands listed above.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Persist findings in root markdown files | Future AI sessions can recover state without relying on chat context. |
| Reuse `AI_HANDOFF.md` and `RUNNING.md` as primary sources | They already capture user constraints, completed work, and run commands. |
| Treat frontend docs as partly stale | `frontend/README.md` says project data uses session store, but newer handoff says project/scene CRUD now persists in backend SQLite. |
| Before changing Next.js code, read local Next docs under `node_modules/next/dist/docs/` | `frontend/AGENTS.md` warns this Next version has breaking changes versus older training data. |
| Before changing assistant-ui patterns, use assistant-ui docs/MCP if available | `frontend/CLAUDE.md` explicitly calls out assistant-ui project patterns. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Shell failed to read `frontend/src/app/projects/[projectId]/page.tsx` because zsh expanded brackets | Quote bracketed paths, e.g. `sed -n '1,160p' 'frontend/src/app/projects/[projectId]/page.tsx'`. |
| Same shell glob issue repeated on a BFF stream route | Quote all Next dynamic route paths before running shell commands. |

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
  - File: `frontend/src/components/chat/use-chat-controller.ts`
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
  - File: `frontend/src/components/chat/chat-message-list.tsx`
  - Root scroller uses dedicated `chat-message-list-scrollbar`.
  - CSS lives in `frontend/src/app/globals.css`.
  - Scrollbar styles are scoped to chat messages rather than all scroll containers.
- Auto-scroll behavior:
  - While the user is near the bottom, streaming output auto-scrolls to the newest content.
  - If the user scrolls upward, auto-follow stops immediately and a floating down-arrow button appears.
  - Clicking the down-arrow scrolls to the bottom and resumes auto-follow.
  - The final implementation avoids `ResizeObserver`; the first implementation used it and caused jitter because token streaming repeatedly changed content height while programmatic scroll and user scroll fought over `scrollTop`.
- Current verification for this work:
  - `cd frontend && npm run lint`
  - `cd frontend && npx tsc --noEmit`
- Known caveats:
  - `npm run build` was attempted after AI SDK integration but hung at Next/Turbopack production build startup for over two minutes; it was interrupted.
  - `npm install @ai-sdk/react ai` reported 12 npm audit findings; not addressed in this pass.
  - Full backend migration to Vercel AI SDK was explicitly skipped; current backend remains Python/FastAPI/LangChain/LangGraph.
