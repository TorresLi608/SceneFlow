# SceneFlow Backend

## Run

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

`app/core/config.py` loads `backend/.env` automatically. Existing process environment variables take precedence.

From the repository root, `npm run docker:build` builds both images and `npm run docker:up` builds and starts them; see `../docs/reference/local-setup.md` for persistent volumes and production settings.

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

## Environment

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
  - request body: `{ "script": "...", "model": "gpt-4o", "episodeId": null, "replaceAll": false }`
  - parses script to scenes and persists them into one episode; `episodeId` omitted targets
    the current (highest-numbered) episode
  - Re-splitting is destructive. When the target episode already has shots carrying a
    generated image or voice track, the response comes back with `applied: false`,
    `discardsGeneratedScenes: N`, and the parsed shots under `pendingScenes` instead of
    overwriting them. The client confirms, then repeats the call with `replaceAll: true`.

### Episodes (JWT required)
- `GET /api/projects/:id/episodes` — summaries (no script, no shots) plus a shot count each
- `POST /api/projects/:id/episodes` — append the next episode; the number comes from the
  highest live one, so a soft-deleted number is reused
- `GET /api/projects/:id/episodes/:episodeId` — the episode with its script and ordered shots
- `PATCH /api/projects/:id/episodes/:episodeId` — title, synopsis, source text, status
- `DELETE /api/projects/:id/episodes/:episodeId` — soft-deletes the episode and its shots;
  refused with 409 while the project is busy, since a run holds those rows open

### Characters (JWT required)
- `GET /api/projects/:id/characters` — the series bible, each card with its variants
- `POST /api/projects/:id/characters`, `PATCH .../:characterId`, `DELETE .../:characterId`
  - deleting soft-deletes the card and its variants and drops it from every shot's cast,
    since a deleted character left in a cast would keep steering prompts
- `POST /api/projects/:id/characters/:characterId/portrait`
  - renders the reference portrait and freezes the provider/model that produced it, so
    changing the account default later cannot restyle an established character
  - synchronous, and refused with 409 on a locked card
- `POST /api/projects/:id/characters/:characterId/variants`, `PATCH .../:variantId`, `DELETE .../:variantId`
- `PUT /api/projects/:id/scenes/:sceneId/characters` — replace a shot's cast; `[]` clears it

### Project Generate (JWT required)
- `POST /api/projects/:id/generate`
  - requires an active image configuration
  - renders one episode's shots; `episodeId` omitted targets the current episode
  - shots with `isLocked` are skipped; all of them locked is a 400 rather than a silent no-op
  - generates real storyboard images and TTS audio concurrently
  - TTS supports Edge/System/OpenAI audio configurations
  - the terminal status reflects what landed: `done`, `partial`, or `failed`, written to both
    the project (which holds the busy lock) and the episode that was rendered
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

Order numbers restart at 1 in every episode, so a serialized project carries **one episode's**
shots under `scenes` — never the whole series' merged together — alongside `episodes` (summaries)
and `currentEpisodeId`. Anything that renders or reorders resolves a target episode first;
`episode_service.resolve_episode` defaults an unnamed one to the highest-numbered episode.
`project_service.project_and_scenes` still spans the whole series and is only for series-wide work.

Generated media is referenced by a path relative to `SCENEFLOW_PRIVATE_GENERATED_DIR`, never
by URL. Signed links expire after 30 days, so a URL stored in a row would turn every asset in
a long-running series into a 404; `schemas/serializers.py` mints a fresh link per response
instead. The baseline Alembic migration upgrades older rows in place and
drops references whose token no longer decodes, since those links were already dead.

A character card pins a look, an image model, and a voice; a `CharacterVariant` is how a
series says "this one changed in episode 5" without the drift being accidental.
`character_service.resolve_character` folds the variant covering an episode over the card,
and a variant only overrides the fields it actually sets — an empty appearance prompt means
"the look did not change". Overlapping ranges resolve to the latest change.

At render time a shot's cast contributes two things: the appearance prompts, which work on
every provider, and the reference portraits, which are passed image-to-image through
`edit_image` and are what actually holds a face steady. A voice override is honoured only on
the configured audio provider, because a card stores a provider and a model but never
credentials. `ExportJob` is still schema only — no service or endpoint reads it yet.

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

- Data access goes through SQLModel (SQLAlchemy 2.x) sessions; `app/models/` defines the schema and Alembic versions it. `init_db()` runs `alembic upgrade head`.
- Request bodies are Pydantic models in `app/schemas/requests.py`, all extending `CamelModel`: the frontend sends camelCase, the backend reads snake_case, and an unknown field is a 422 rather than a silently dropped value.
- Timestamp columns stay ISO-8601 strings (not `datetime`) because the code compares them as strings and the API passes them straight through.
- Historical compatibility and the `user_configs`/`official_model_configs` -> `model_configs` data migration live in the baseline Alembic revision, outside runtime startup code.
- The baseline migration gives every episode-less project an episode 1 that adopts its shots, then attaches any remaining episode-less shot to its project's earliest episode. Listing projects never creates one: a GET has no business writing rows.
- Starting work on a project takes a conditional UPDATE on `projects.status` (`claim_project_status`), so a double-clicked button cannot start two runs over the same rows. The lock stays at project level even though rendering is per episode, so one run owns the series at a time.
- Passwords are stored by bcrypt hash; model API keys are encrypted with AES-GCM.
- Generated media is stored under `private_generated` and served only through expiring signed URLs.
- Provider API keys are encrypted by AES-256-GCM before persisting.
- Existing SQLite data is kept compatible with the old GORM table names and columns.
- Generate flow streams per-scene progress events over WebSocket (`SCENE_UPDATE`).
