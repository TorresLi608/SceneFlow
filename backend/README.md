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
- `app/core/`: configuration, database, logging, security, and realtime infrastructure.
- `app/models/`: SQLModel table definitions; the single source of truth for the schema.
- `app/schemas/`: `requests.py` holds the Pydantic request bodies, `serializers.py` the response shaping.
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
- `SCENEFLOW_LOG_LEVEL` (default `INFO`)
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
  - request body: `{ "script": "...", "model": "gpt-4o", "replaceAll": false }`
  - parses script to scenes and persists to DB
  - Re-splitting is destructive. When the project already has shots carrying a generated
    image or voice track, the response comes back with `applied: false`,
    `discardsGeneratedScenes: N`, and the parsed shots under `pendingScenes` instead of
    overwriting them. The client confirms, then repeats the call with `replaceAll: true`.

### Project Generate (JWT required)
- `POST /api/projects/:id/generate`
  - requires an active image configuration
  - generates real storyboard images and TTS audio concurrently
  - TTS supports Edge/System/OpenAI audio configurations
  - the terminal status reflects what landed: `done`, `partial`, or `failed`
- `PATCH /api/projects/:id/production-settings`
- `GET /api/projects/:id/jobs`
- `POST /api/jobs/:id/cancel`
- `POST /api/jobs/:id/retry`

`generation_jobs` currently provides persistence, idempotency, leases, cancel, and retry services. The worker processor and project job UI are still pending; existing image/audio generation still starts in the API process.

## Data model

`Project` is a series. Its content hangs off `Episode` rows, and each `Scene` is one shot
inside an episode. `Character` plus `CharacterVariant` form the series bible that keeps a
cast member's look, image model, and voice stable across episodes; `SceneCharacter` records
who appears in a shot. `ExportJob` tracks a merged render of up to
`MAX_EXPORT_EPISODES` (10) episodes.

Generated media is referenced by a path relative to `SCENEFLOW_PRIVATE_GENERATED_DIR`, never
by URL. Signed links expire after 30 days, so a URL stored in a row would turn every asset in
a long-running series into a 404; `schemas/serializers.py` mints a fresh link per response
instead. `_migrate_scene_assets` in `app/core/database.py` upgrades older rows in place and
drops references whose token no longer decodes, since those links were already dead.

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

- Data access goes through SQLModel (SQLAlchemy 2.x) sessions; `app/models/` owns the schema and `init_db()` creates it with `SQLModel.metadata.create_all()`.
- Request bodies are Pydantic models in `app/schemas/requests.py`, all extending `CamelModel`: the frontend sends camelCase, the backend reads snake_case, and an unknown field is a 422 rather than a silently dropped value.
- Timestamp columns stay ISO-8601 strings (not `datetime`) because the code compares them as strings and the API passes them straight through.
- The hand-written `ALTER TABLE` compatibility steps and the `user_configs`/`official_model_configs` -> `model_configs` data migration in `app/core/database.py` deliberately remain raw SQL; they operate on tables that no longer have models.
- Databases created before the episode layer keep unused `scenes.image_url`/`audio_url` columns only if the rename could not run; the current column names are `image_path`/`audio_path`.
- Starting work on a project takes a conditional UPDATE on `projects.status` (`claim_project_status`), so a double-clicked button cannot start two runs over the same rows.
- Passwords are stored by bcrypt hash; model API keys are encrypted with AES-GCM.
- Generated media is stored under `private_generated` and served only through expiring signed URLs.
- Provider API keys are encrypted by AES-256-GCM before persisting.
- Existing SQLite data is kept compatible with the old GORM table names and columns.
- Generate flow streams per-scene progress events over WebSocket (`SCENE_UPDATE`).
