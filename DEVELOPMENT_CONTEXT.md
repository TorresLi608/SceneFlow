# SceneFlow Development Context

## Read This First

This file records the current implementation state and the next iteration context for AI-assisted development.

## Current Architecture

### Backend

- Framework: FastAPI.
- Entry point: `backend/app.py`.
- Runtime command:
  ```bash
  cd backend
  .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8080
  ```
- The backend has been split into modules:
  - `backend/routers/`: route groups.
  - `backend/database.py`: SQLite connection and schema creation.
  - `backend/security.py`: JWT and AES key encryption.
  - `backend/config_service.py`: provider/model config validation and loading.
  - `backend/chat_service.py`: chat session/message persistence and chat turn preparation.
  - `backend/model.py`: OpenAI-compatible model routing, chat streaming, script parse/optimize, image generation.

### Frontend

- Framework: Next.js App Router.
- Runtime command:
  ```bash
  cd frontend
  npm run dev
  ```
- Current local URL used in this session: `http://localhost:3001`.
- BFF pattern is used:
  - UI calls `/api/bff/...`.
  - BFF routes forward to FastAPI backend.
  - Axios client injects Bearer token for normal requests.
  - Streaming chat uses `fetch` and manually forwards the token.

## Chat Feature Implemented

### User Flow

- Sidebar has `工作台` and `智能问答`.
- `智能问答` opens a ChatGPT-like basic chat panel.
- User selects from verified `script` / `剧本/提示词` model configs.
- Chat sessions and messages are stored per user.
- Assistant responses stream to the UI.
- If provider returns `reasoning_content`, UI shows it in a collapsible `模型思考` block.

### Backend APIs

- `GET /api/chat/sessions`
- `POST /api/chat/sessions`
- `GET /api/chat/sessions/{session_id}/messages`
- `POST /api/chat/sessions/{session_id}/messages`
- `POST /api/chat/sessions/{session_id}/messages/stream`

The streaming endpoint returns NDJSON lines:

```json
{"type":"userMessage","message":{}}
{"type":"reasoning_delta","content":"..."}
{"type":"content_delta","content":"..."}
{"type":"assistantMessage","message":{}}
{"type":"error","error":"..."}
```

### Frontend Files

- `frontend/src/components/chat/chat-panel.tsx`: composition only.
- `frontend/src/components/chat/use-chat-controller.ts`: chat data flow and streaming state.
- `frontend/src/components/chat/chat-sidebar.tsx`: model selector and session list.
- `frontend/src/components/chat/chat-message-list.tsx`: message rendering.
- `frontend/src/components/chat/chat-format.ts`: display helpers.
- `frontend/src/actions/chat-actions.ts`: chat actions and stream reader.
- `frontend/src/bff/chat-bff.ts`: backend forwarding helpers.
- `frontend/src/types/chat.ts`: chat types.
- `frontend/src/app/api/bff/chat/...`: Next BFF routes.

## Storage Decision

- Chat history should live in the regular database.
- Current DB is SQLite for local speed.
- Later migration target should be Postgres.
- Vector DB should not be the source of truth for chat history.
- Future RAG flow should store original messages/documents in Postgres and write derived chunks/embeddings to `pgvector` or another vector index.

Current SQLite tables added:

```sql
chat_sessions(id, created_at, updated_at, deleted_at, user_id, title, config_id, provider, model_name)
chat_messages(id, created_at, session_id, role, content, reasoning, provider, model_name)
```

## Model Provider Decision

Current provider base URLs are hardcoded in `backend/model.py`.

Not implemented yet:

- User-configurable OpenAI-compatible `base_url`.
- Relay/proxy support such as One API, New API, LiteLLM Proxy, or custom GPT relay endpoints.

Recommended next minimal change:

- Add nullable `base_url` to `user_configs`.
- Show optional `Base URL` in settings.
- For chat models, use user `base_url` when present, otherwise fallback to `CHAT_BASE_URLS[provider]`.
- Only support OpenAI-compatible protocol first.

## Image / Video Chat Mode Decision

Do not auto-call expensive tools by default.

Recommended product flow:

- `聊天模式`: text chat only.
- `图片模式`: explicit image generation.
- `视频模式`: explicit video generation.

Later optional `智能模式`:

- Classify intent as `chat | image | video`.
- Ask for confirmation before costly image/video generation.
- Add queue/progress UI before automatic tool calls.

## Recent Refactor Notes

- `ChatPanel` was split because it was handling fetching, streaming state, side navigation, and message rendering in one file.
- Backend chat route duplicate logic was moved into `chat_service.prepare_chat_turn`.
- Old unused `langchain_chat` path was removed from `backend/model.py`.
- Chat context now uses the latest 40 messages, then restores ascending order before sending to the model.

## Validation Commands Used

```bash
cd frontend
npm run lint
npm run build
```

```bash
python3 -B -c 'import sys; sys.path.insert(0, "backend"); import app; print(len(app.app.routes))'
```

A temporary SQLite streaming test was also run to verify:

- session creation
- stream output
- persisted user message
- persisted assistant message
- persisted reasoning text

## Git / Generated Files

Do not commit:

- `frontend/node_modules/`
- `frontend/.next/`
- `backend/.venv/`
- `backend/__pycache__/`
- `backend/routers/__pycache__/`
- runtime DB files like `backend/sceneflow.db`

Note: `backend/sceneflow.db` may already be tracked by git. If it appears modified after running the app, do not include it in feature commits.

## Current Local Services

- Frontend was started on `http://localhost:3001`.
- Backend was started on `http://127.0.0.1:8080`.

If the port is occupied, use the next available port and update frontend env if needed.

## Next Suggested Iterations

1. Add custom OpenAI-compatible `base_url` support to user model configs.
2. Add chat mode selector: `聊天 / 图片 / 视频`.
3. Add markdown/code rendering for assistant answers using `react-markdown`, `remark-gfm`, and a highlighter.
4. Add Postgres migration plan before data grows.
5. Add `pgvector` only when document/chat semantic retrieval is actually needed.

