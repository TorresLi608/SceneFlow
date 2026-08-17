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

`Pillow` builds the merged reference sheets and `ffmpeg` concatenates audio; `ffprobe`
measures clip length. Both binaries ship in the Docker image and must be on PATH locally.

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
- Image generation supports OpenAI, Gemini, and Qwen/Wan; video supports Doubao, Gemini, and Qwen/Wan; audio supports Edge, system, OpenAI, and Qwen TTS. Audio is used by voice-profile auditioning, not by per-shot rendering.
- Qwen media uses Alibaba's official `dashscope` SDK for the native `https://dashscope.aliyuncs.com/api/v1` API. Video uses `wan2.7-t2v` without a reference image, `wan2.7-i2v` with a first frame and optional driving audio, `wan2.7-r2v` with up to five references, or `videoedit` with a reference video. Each video model config declares its allowed inputs, quality, pixel resolution, FPS, prompt enhancement, and duration range; unsupported parameters are omitted and rejected if submitted. Native DashScope media uploads use the SDK's OSS uploader; a configured relay Base URL remains supported through its HTTP-compatible API and receives data URLs. Qwen quality is `480p`, `720p`, or `1080p`, and prompt enhancement maps to `prompt_extend`. Audio `modelSeries` is `model:voice`, for example `qwen3-tts-flash:Cherry`.
- New model configurations start with an empty `modelSeries`. Model discovery does not filter by purpose: it uses the provider or relay `/models` endpoint when available, while native Qwen media and local TTS return all known models for that provider. Saving never performs a remote connectivity check; enabled configs still require their local fields and API key.

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

### Projects (JWT required)
- `GET /api/projects` — the caller's live series, each with its current episode's shots
- `POST /api/projects` — `{ "title", "description", "originalScript", "productionSettings" }`
- `PATCH /api/projects/:id` — title, description, source script, series bible
- `DELETE /api/projects/:id` — soft-deletes the series
- `POST /api/projects/cover/generate` — draws a cover from `{ "title", "description", "stylePrompt" }`
  and returns it as `{ "imageData": "data:image/png;base64,..." }`
  - project-less on purpose: the create dialog runs before a project row exists, and the edit
    dialog runs against unsaved edits. Nothing is written; the caller applies the result below
  - synchronous, and requires an active image configuration (`openai`/`gemini`/`qwen`)
- `POST /api/projects/description/optimize` — polishes a synopsis and returns it for review;
  never saved behind the user
- `PUT /api/projects/:id/cover` — stores an uploaded or generated cover from a base64 data URL
  (png/jpeg/webp, 10MB ceiling); the row keeps a path, and responses mint a signed link
- `DELETE /api/projects/:id/cover` — drops the cover so the card falls back to the placeholder

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
- `POST /api/projects/:id/episodes` — append the next episode; `title` is required, and the
  number comes from the highest live one, so a soft-deleted number is reused
- `GET /api/projects/:id/episodes/:episodeId` — the episode with its script and ordered shots
- `PATCH /api/projects/:id/episodes/:episodeId` — title, synopsis, source text, status
- `DELETE /api/projects/:id/episodes/:episodeId` — soft-deletes the episode and its shots;
  refused with 409 while the project is busy, since a run holds those rows open
- `POST /api/projects/:id/episodes/:episodeId/storyboard` — renders the episode in two passes
  - **the tone sheet first**: one image holding thumbnails of every shot, generated in a
    single sampling. It is never a deliverable — each cell is far too small — but one
    sampling is what makes lighting, palette, and render style agree across the episode
  - **then a frame per shot**, full resolution, each carrying the tone sheet, the merged
    context sheet, and the previous shot's render. Style, cast, and scene continuity each
    get their own anchor; the list is truncated to `MAX_REFERENCE_IMAGES`
  - shots render **sequentially**, because each references its predecessor's output
  - a failed tone sheet aborts the run rather than rendering unanchored shots the user
    would still be billed for
  - `mergeReferences` (default true) tiles the cast sheet, prop sheet, and previous anchor
    into one reference; false sends them separately, which costs more tokens
  - `regenerate` resamples the tone sheet instead of reusing it, which also restyles shots
    that were already approved. `previousEpisodeId` carries the look across an episode
    boundary; it must name a different episode

### Characters (JWT required)
- `GET /api/projects/:id/characters` — the series bible, each card with its states
- `POST /api/projects/:id/characters`, `PATCH .../:characterId`, `DELETE .../:characterId`
  - deleting soft-deletes the card and its states and drops it from every shot's cast,
    since a deleted character left in a cast would keep steering prompts
- `POST /api/projects/:id/characters/:characterId/states`, `PATCH .../:stateId`, `DELETE .../:stateId`
  - a state is one look the character can appear in (an age, an outfit). `fromEpisode` /
    `toEpisode` are optional: set, they narrow the state to an episode range; unset, the
    state is one of several parallel looks and never hijacks episode resolution
- `POST /api/projects/:id/characters/:characterId/states/:stateId/prompt`
  - drafts the turnaround prompt from the character and the state and returns it for review;
    never saved, because the preview step is the point
- `POST /api/projects/:id/characters/:characterId/states/:stateId/image` — draws the state's
  turnaround sheet from the approved prompt, and freezes the provider/model that produced it
  - synchronous, and refused with 409 on a locked card
- `PUT /api/projects/:id/characters/:characterId/states/:stateId/image` — upload one instead
- `POST /api/projects/:id/characters/:characterId/sheet` — tile one character's states into a sheet
- `POST /api/projects/:id/characters/sheet` — tile the whole cast into the single sheet a
  storyboard render carries; 400 when nothing has been drawn yet
- `PUT /api/projects/:id/scenes/:sceneId/characters` — replace a shot's cast; `[]` clears it
- `POST /api/projects/:id/scenes`, `DELETE /api/projects/:id/scenes/:sceneId` — add or soft-delete a shot in an episode

### Props (JWT required)
Same shape as characters, one level down: an object the series must draw identically every time.
- `GET /api/projects/:id/props`, `POST /api/projects/:id/props`, `PATCH .../:propId`, `DELETE .../:propId`
- `POST /api/projects/:id/props/:propId/prompt` — draft the image prompt for review
- `POST /api/projects/:id/props/:propId/image` — draw it; `PUT` the same path uploads one instead
- `POST /api/projects/:id/props/sheet` — tile every prop into one sheet

### Voices (JWT required)
Per-shot TTS is gone. Voices are managed once per project, and what the pipeline consumes is
the merged track — every voice introducing itself in its own timbre, so a video model given
it as a reference can keep speakers apart.
- `GET /api/projects/:id/voices`, `POST /api/projects/:id/voices`, `PATCH .../:voiceId`, `DELETE .../:voiceId`
  - deleting releases every character bound to the profile; the binding is a plain column
    rather than a foreign key, so the service does what ON DELETE SET NULL would have
- `POST /api/projects/:id/voices/:voiceId/preview` — synthesises the sample line so the user
  can audition it. A model from a provider the project is not configured for falls back to
  the default voice, because a profile stores a provider and a model but never credentials
- `POST /api/projects/:id/voices/merge` — ffmpeg-concatenates every auditioned clip into
  `projects.voice_sheet_path`; 400 when nothing has been auditioned yet
- bind one to a character with `PATCH .../characters/:characterId` and `voiceProfileId`;
  `""` unbinds, since a JSON null reads as an absent field

### Project Generate (JWT required)
- `POST /api/projects/:id/generate`
  - request body takes optional `sceneIds`; omitted IDs target all unlocked shots
  - requires an active image configuration
  - renders one episode's shots; `episodeId` omitted targets the current episode
  - shots with `isLocked` are skipped; all of them locked is a 400 rather than a silent no-op
  - renders up to three shots concurrently
  - the terminal status reflects what landed: `done`, `partial`, or `failed`, written to both
    the project (which holds the busy lock) and the episode that was rendered
- `PATCH /api/projects/:id/production-settings`
- `GET /api/projects/:id/jobs`
- `POST /api/jobs/:id/cancel`
- `POST /api/jobs/:id/retry`

- `POST /api/projects/:id/generate-video`
  - renders one clip per shot; models cap out at a handful of seconds, so an episode is
    assembled from clips rather than generated in one call
  - `withAudio` passes the project's merged timbre reference as driving audio. A model that
    does not accept audio is a 400, and so is a project whose voices have not been merged —
    silently dropping it would bill the user for a render they did not ask for
  - options are validated against the model's declared capabilities; unsupported parameters
    are rejected rather than ignored

### Video export (JWT required)
- `GET /api/projects/:id/exports` — history, newest first
- `POST /api/projects/:id/exports` — `{ "sceneIds": [...], "rangeLabel" }`; queues a merge and
  returns 202. `sceneIds` order **is** the output order: the section exists to assemble a cut,
  which need not follow the storyboard. Up to `MAX_EXPORT_CLIPS` (60) clips
  - shots with no rendered video are refused up front rather than failing the job later
  - concatenation always re-encodes and letterboxes to the project's `width`x`height`/`fps`;
    a stream copy across clips of different geometry plays only up to the first mismatch,
    which looks like a truncated export rather than an error
- `GET /api/projects/:id/exports/:exportId` — status, progress, and a signed download link

`generation_jobs` currently provides persistence, idempotency, leases, cancel, and retry services. The worker processor and project job UI are still pending; image and video generation still starts in the API process.

## Data model

`Project` is a series. Its content hangs off `Episode` rows, and each `Scene` is one shot
inside an episode. `Character` plus `CharacterState` form the series bible that keeps a
cast member's look, image model, and voice stable across episodes; `Prop` does the same for
objects, and `SceneCharacter` records who appears in a shot. `ExportJob` tracks a merged render of up to
`MAX_EXPORT_CLIPS` (60) chosen shots.

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

A character card pins a look, an image model, and a voice. A `CharacterState` is one look
that character can appear in — an age, an outfit, a transformation — and its
`reference_image_path` holds a turnaround sheet (front, three-quarter, profile in one image).
States are parallel forms by default; pinning `from_episode` is what turns one into "this one
changed in episode 5" without the drift being accidental. `character_service.resolve_character`
folds the state covering an episode over the card, and a state only overrides the fields it
actually sets — an empty appearance prompt means "the look did not change". Overlapping ranges
resolve to the latest change, and an unpinned state never wins that resolution.

`Prop` is the same idea one level down, for objects rather than people.

Because providers cap how many reference images one request may carry
(`MAX_REFERENCE_IMAGES` = 4), a cast or prop list of any size has to reach the renderer as a
merged sheet. `services/media_service.py` builds those: sources are scaled to one uniform
width **before** tiling — never pasted at native size — and the result is compressed under a
10MB ceiling, quality first and resolution only once quality has bottomed out. The merged
sheets live on `characters.sheet_image_path`, `projects.character_sheet_path`, and
`projects.prop_sheet_path`.

At render time a shot's cast contributes two things: the appearance prompts, which work on
every provider, and the reference images, which are passed image-to-image through
`edit_image` and are what actually holds a face steady. The project's `style_prompt` and
`negative_prompt` ride along on the same payload. A voice override is honoured only on the
configured audio provider, because a card stores a provider and a model but never
credentials.

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
