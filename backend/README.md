# SceneFlow Backend

## Run

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Structure

- `app/api/v1/`: FastAPI endpoints and request/response orchestration.
- `app/core/`: configuration, database, security, and realtime infrastructure.
- `app/schemas/`: response serialization shared by API modules.
- `app/services/`: model, usage, chat, artifact, project, and generation business logic.
- `app/graph/`: context and agent workflow orchestration.
- `app/llms/`: provider routing and model registry.
- `app/utils/`: small shared helpers such as IDs, timestamps, and attachment parsing.
- `tests/`: dependency-free executable self-checks.

Run all backend checks:

```bash
cd backend
.venv/bin/python tests/run_all.py
```

## Optional env

- `PORT` (default `8080`)
- `SCENEFLOW_DB_PATH` (default `./sceneflow.db`)
- `SCENEFLOW_ENV` (default `development`; set `production` in production)
- `SCENEFLOW_JWT_SECRET` (development default is intentionally non-production)
- `SCENEFLOW_AES_KEY` (default `dev-aes-key-change-me`, internally SHA-256 -> 32 bytes)
- `SCENEFLOW_SUPER_ADMIN_PASSWORD` (default `superAdmin@123` in development)
- `SCENEFLOW_MAX_CONTEXT_TOKENS` (default `100000`)
- `SCENEFLOW_PUBLIC_BASE_URL` (default `http://127.0.0.1:8080`)
- `SCENEFLOW_CORS_ORIGINS` (comma-separated; defaults to the two local frontend origins)
- `SCENEFLOW_PRIVATE_GENERATED_DIR` (default `./private_generated`)
- `SCENEFLOW_CJK_FONT_PATH` (optional PDF Chinese TTF/TTC path; common macOS/Linux paths are auto-detected)
- `SCENEFLOW_CJK_FONT_NAME` (default `Arial Unicode MS`, used by generated Word documents)

Production startup rejects the development JWT, AES, and super-admin secrets.

## Super admin

- Startup creates `superAdmin` with `SCENEFLOW_SUPER_ADMIN_PASSWORD` only if it is missing, then keeps it enabled with role `superAdmin`.
- Disabled users cannot log in or use existing tokens.

## Model routing

- `app/llms/router.py` owns LLM provider switching; `app/services/` owns application workflows.
- Chat models use LangChain adapters. OpenAI-compatible providers share `ChatOpenAI(base_url=...)`; Anthropic uses `ChatAnthropic`.
- Chat context assembly lives in `app/graph/`: SQLite history -> token budget check -> old-context summary compression -> model messages.
- Chat uses LangChain `create_agent` with image, PDF, and Word generation tools. Generated chat artifacts use signed 30-day links and server-controlled paths.
- Supported script/chat providers: `qwen`, `doubao`, `deepseek`, `openai`, `gemini`, `anthropic`, and `custom`.
- Image generation currently supports OpenAI Images.

## APIs

### Auth
- `POST /api/auth/register`
- `POST /api/auth/login`

### User (JWT required)
- `GET /api/users/me`
- `PATCH /api/users/me`
- `DELETE /api/users/me`

### UserConfig (JWT required)
- `POST /api/settings/keys`
- `GET /api/settings/keys`
- `GET /api/settings/keys/:id`
- `PATCH /api/settings/keys/:id`
- `DELETE /api/settings/keys/:id`
- `POST /api/settings/official/:id/activate`
- `DELETE /api/settings/official/:id/activate`

### Admin (superAdmin required)
- `GET /api/admin/users`
- `GET /api/admin/usage-logs?search=&page=&pageSize=`
- `PATCH /api/admin/users/:id`
- `DELETE /api/admin/users/:id`
- `GET /api/admin/default-models`
- `POST /api/admin/default-models`
- `PATCH /api/admin/default-models/:id`
- `DELETE /api/admin/default-models/:id`

Official script configs support OpenAI-compatible relays by setting `provider: "custom"`,
`modelSeries`, and `baseUrl` such as `https://www.juaiapi.com/v1`.

### Project Parse (JWT required)
- `POST /api/projects/:id/parse`
  - request body: `{ "script": "...", "model": "gpt-4o" }`
  - parses script to scenes and persists to DB

### Project Generate (JWT required)
- `POST /api/projects/:id/generate`
  - requires an active image configuration
  - generates real storyboard images and TTS audio concurrently
  - TTS supports Edge/System/OpenAI audio configurations
- `PATCH /api/projects/:id/production-settings`
- `GET /api/projects/:id/jobs`
- `POST /api/jobs/:id/cancel`
- `POST /api/jobs/:id/retry`

`generation_jobs` currently provides persistence, idempotency, leases, cancel, and retry services. The worker processor and project job UI are still pending; existing image/audio generation still starts in the API process.

## Short-drama orchestration

- LangGraph is reserved for checkpointed LLM decisions and human approval, such as script structure and continuity review.
- `generation_jobs` plus a worker owns deterministic image, TTS, video, and FFmpeg tasks.
- Rollback means selecting an earlier asset version and marking downstream results stale, not deleting generated assets.
- LangGraph is already installed through LangChain; no extra dependency is needed.

### WebSocket
- `GET /ws/projects/:id`, with `sceneflow-auth.<JWT>` in `Sec-WebSocket-Protocol`
  - heartbeat enabled
  - project-scoped broadcast stream
  - event types include `WS_CONNECTED`, `PROJECT_UPDATE`, `SCENE_UPDATE`

## Notes

- Passwords are stored by bcrypt hash; model API keys are encrypted with AES-GCM.
- Generated media is stored under `private_generated` and served only through expiring signed URLs.
- Provider API keys are encrypted by AES-256-GCM before persisting.
- Existing SQLite data is kept compatible with the old GORM table names and columns.
- Generate flow streams per-scene progress events over WebSocket (`SCENE_UPDATE`).
