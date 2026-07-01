# SceneFlow Implementation Phases

## Execution Rule
- Only one phase is implemented at a time.
- Move to the next phase only after manual acceptance.

## Phase 1 - Backend Foundation and Auth (Completed)
- FastAPI service entrypoint and route grouping.
- SQLite setup and compatible table creation.
- PyJWT issue/verify and auth dependency.
- AES-256-GCM utility for provider API key encryption/decryption.
- User CRUD APIs (`/api/users/me`).
- UserConfig CRUD APIs (`/api/settings/keys`).
- LangChain model routing in `backend/model.py`.

### Acceptance checks
- `python3 -m py_compile backend/app.py backend/model.py` passes.

## Phase 2 - Frontend Foundation and Auth Loop (Completed)
- Initialize Next.js + Tailwind + shadcn/ui.
- Zustand `userStore` with persistence.
- Login/Register pages.
- Settings modal for API key and model selector.
- Axios interceptor with JWT Bearer injection.

## Phase 3 - Static Workbench UI + Drag and Drop (Completed)
- Two-pane layout (script input + scene card flow).
- `SceneCard` component and mock data rendering.
- `dnd-kit` sort and reorder.
- Zustand `projectStore` for scene state.
- Frontend architecture uplift: unified axios + BFF routes + action layer + React Query cache/state.

## Phase 4 - Parse API + WebSocket Foundation (Completed)
- `POST /api/projects/:id/parse` implementation.
- Decrypt user API key and call selected LLM through LangChain.
- Validate strict JSON and persist scenes.
- FastAPI WebSocket project broadcast.

## Phase 5 - Concurrent Generation + End-to-End Sync (Completed)
- `POST /api/projects/:id/generate` with async task concurrency.
- Simulated image/TTS worker execution.
- Progress streaming via WebSocket.
- Frontend WS subscription updates scene progress/status.
- Skeleton and progress animation for generating scenes.
