# SceneFlow Backend

Verified on **2026-09-07**. Start with the [documentation index](../docs/README.md), [code map](../docs/architecture/code-map.md), and [data flow](../docs/architecture/data-flow.md). This file owns environment variables, provider notes, and the endpoint inventory.

## Run and check

Python 3.11; the repository's existing virtual environment is `backend/.venv`. For a first setup:

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Copy .env.example to .env only if no local configuration exists yet.
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

From the root, `npm run install:backend` creates/installs the venv and `npm run dev:backend` starts it through `scripts/dev-backend.mjs`. That launcher terminates processes occupying `PORT` before starting; inspect the owner or use direct uvicorn on a free port. It forwards termination signals and cleans up its child. It does not enable uvicorn reload.

`app/core/config.py` loads `backend/.env`; process environment takes precedence. Startup upgrades Alembic, seeds/enables the configured super admin, clears orphaned project/media busy flags, and starts the in-process job worker. Completed media survives startup cleanup; interrupted work is not resumed.

FFmpeg and ffprobe must be on PATH for auditions, timbre sheets, and exports. Pillow merges images. The Docker image includes FFmpeg; [local setup](../docs/reference/local-setup.md) describes ports, persistent volumes, and backups.

```bash
cd backend
check_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh $(rg --files tests -g 'test_*.py' | sed 's#^tests/##; s#\.py$##')
DATABASE_URL= SCENEFLOW_DB_PATH="$check_dir/schema.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" .venv/bin/alembic upgrade head
DATABASE_URL= SCENEFLOW_DB_PATH="$check_dir/schema.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" .venv/bin/alembic check
```

The test runner requires module names, overrides both database variables with a temporary database, runs each module in a separate interpreter, and reports all failures. `tests/run_all.py` is not isolated. See [testing](../docs/conventions/testing.md) for targeted checks and [OpenAPI regeneration](../docs/conventions/README.md#keeping-generated-docs-current) for the existing script. Do not test against `data/app.db`, legacy `backend/sceneflow.db`, or `backend/private_generated/`.

## Environment

| Variable | Default / effect |
|---|---|
| `PORT` | `8080`; read by the development launcher (direct uvicorn uses its CLI `--port`) |
| `DATABASE_URL` | SQLite URL; defaults to repository-root `data/app.db`, or `sqlite:////app/data/app.db` in the Docker image. Takes precedence over `SCENEFLOW_DB_PATH`. |
| `SCENEFLOW_DB_PATH` | Unset; legacy SQLite file path used only when `DATABASE_URL` is unset/empty. Relative paths follow the working directory. |
| `SCENEFLOW_PRIVATE_GENERATED_DIR` | `./private_generated`; created/chmodded at app import |
| `SCENEFLOW_ENV` | `development`; production rejects development security secrets |
| `SCENEFLOW_JWT_SECRET` | Development default; signs sessions and derives the artifact-signing key |
| `SCENEFLOW_AES_KEY` | Development default, SHA-256-derived AES-256 key for provider secrets |
| `SCENEFLOW_SUPER_ADMIN_USERNAME` | `superAdmin`; trimmed login name, 3–64 characters. Renames the legacy default admin in place; occupied names fail startup. |
| `SCENEFLOW_SUPER_ADMIN_PASSWORD` | `superAdmin@123`; applied when creating the account, not a password reset on every startup |
| `SCENEFLOW_PUBLIC_BASE_URL` | `http://127.0.0.1:8080`; absolute signed artifact URL origin |
| `SCENEFLOW_CORS_ORIGINS` | `http://localhost:4000,http://127.0.0.1:4000`; comma separated |
| `SCENEFLOW_MAX_CONTEXT_TOKENS` | `100000`, minimum configured budget 10000 |
| `SCENEFLOW_LOG_LEVEL` | `INFO` |
| `SCENEFLOW_WORKER_ENABLED` | Enabled; `0`, `false`, or `no` disables queue consumption for manual test draining |
| `SCENEFLOW_CJK_FONT_PATH` | Optional PDF font override; common local fonts are auto-detected |
| `SCENEFLOW_CJK_FONT_NAME` | `Arial Unicode MS`; generated Word document font |
| `SCENEFLOW_SMTP_HOST` | Empty; SMTP server |
| `SCENEFLOW_SMTP_USER` | Empty; SMTP login and default sender |
| `SCENEFLOW_SMTP_PASSWORD` | Empty |
| `SCENEFLOW_SMTP_FROM` | SMTP user, otherwise the built-in SceneFlow sender |
| `SCENEFLOW_SMTP_PORT` | `465` with SSL, otherwise `587` |
| `SCENEFLOW_SMTP_SSL` | `true`; otherwise STARTTLS (port 465 also selects SSL) |

When SMTP host/user are absent, `email_service` logs the registration code instead of sending email; this fallback currently has no production guard. Email is optional at registration; if supplied it requires a verification code. Codes expire after 300 seconds, with a 60-second sending cooldown.

The engine creates the database parent directory before opening SQLite; both startup and Alembic use the same configuration. `sqlite://` and `sqlite:///:memory:` retain a shared in-memory database for tests. SQLite URI filenames (`uri=true`) and non-SQLite backends are not supported. Existing development `.env` files can keep `SCENEFLOW_DB_PATH=./sceneflow.db`; see [migration instructions](../docs/reference/local-setup.md#migrating-existing-data) before switching storage.

Compose binds `${SCENEFLOW_DATA_DIR:-./data}` to `/app/data`, with the default database at `/app/data/app.db`. `SCENEFLOW_DATA_DIR` and Compose URL overrides belong in the shell or repository-root `.env`; `backend/.env` holds backend settings such as the admin name/password. The image entrypoint fixes `/app/data` ownership and then drops to UID 10001. Media remains in `sceneflow_media`; database and media backups are both still needed.

Startup keeps the configured admin enabled. A legacy `superAdmin` row is renamed without changing its ID or password; a non-admin username is never promoted. After that initial rename, a different configured name must already match an admin, otherwise startup fails instead of creating another admin. See [authentication](../docs/design/feature-auth.md#super-admin). Disabled ordinary users cannot log in or authenticate new HTTP requests. JWTs expire after 24 hours. Provider secrets are revealed only through authorized `POST .../secret` endpoints; metadata GETs omit them.

## Providers and model configuration

- `llms/router.py` owns text/image adapters; `video_service.py`, `qwen_voice_service.py`, and `tts_service.py` own their media adapters. Services own workflows, configuration resolution, and billing.
- Script/chat providers: `qwen`, `doubao`, `deepseek`, `openai`, `gemini`, `anthropic`, `custom`. Chat uses LangChain adapters, with `ChatOpenAI(base_url=...)` for compatible endpoints and `ChatAnthropic` for Anthropic.
- Image providers: OpenAI, Gemini, Qwen/Wan. `imageMaxReferenceImages` is configurable (default 4, non-negative), not a global provider cap.
- Video providers: Doubao, Gemini, Qwen/Wan. Capabilities come from `config_service.py` and the saved configuration: media limits, first/last frames, ratios, quality, duration, prompt extension, and audio switch. Both standalone and project video paths use `video_service`; the project endpoint additionally requires storyboard images.
- An empty FPS capability list means callers omit `fps`; it is not an instruction to send 24. Explicit unsupported FPS values remain validation errors. The standalone form follows this contract; see the [FPS fix record](../docs/bugs/2026-09-07-video-unsupported-fps.md).
- Doubao uses `volcengine-python-sdk[ark]` and the configured `baseUrl`. The current catalog declares Seedance 2.0 variants and 2.5; its capability defaults are application declarations, with provider discrepancies still recorded as field reports in the backlog.
- Qwen chat defaults to `https://dashscope.aliyuncs.com/compatible-mode/v1`; image/video use DashScope media APIs. Wan media keys and audio switches differ by family (`reference_audio` / `audio` versus `reference_voice`, and older `video` / `driving_audio`). The model catalog is served by `/api/settings/video-models` and allows custom relay IDs.
- Standalone audio is Qwen Voice Design. The fixed design model is `qwen-voice-design`; configured `modelSeries` becomes `target_model`. `/api/voices/design` creates a draft preview and `/api/voices/:id/save` promotes it to the saved account library. Project design/import creates a project profile; project auditions use local Edge/system TTS.
- New model configs have an empty `modelSeries`. Discovery uses the submitted provider/base URL/key when supported; saving validates fields without a remote connectivity test. Official and personal configs share `model_configs`, with account official defaults in `user_official_config_defaults`.
- Generation resolves the project's model pick first, then account/system fallback. Four project config IDs and generation defaults are updated through `modelSettings`; `0` clears a pick and `null` means leave alone. Unsupported saved defaults can be omitted for a changed model; explicit unsupported options fail validation.
- Prompt optimization uses the configured text model and returns editable text. Prefix presets and compilation do not start generation. See [prompt/reference flow](../docs/architecture/data-flow.md#4-references-prefix-prompts-and-asset-library).

Chat context is SQLite history → token budget → older-context summary. LangChain `create_agent` has image/PDF/Word tools and an extra read-only error-log tool for super admins. There is no configured durable production checkpointer or approval workflow. [Chat design](../docs/design/feature-chat.md) documents the frontend/backend stream split.

## HTTP endpoints

Inventory checked against the router decorators on **2026-09-07**. Paths below use the actual FastAPI parameter names. [OpenAPI](../docs/reference/api-spec.yaml) is the generated HTTP/schema reference; behavior and background execution are described in [data flow](../docs/architecture/data-flow.md).

Except for auth, health, static prompt presets, and token-signed artifact downloads, endpoints require JWT authentication. `/api/admin/*` requires super-admin access. Public layout/navigation is not authorization.

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Process liveness only |

### auth — app/api/v1/auth.py

| Methods | Path |
|---|---|
| POST | `/api/auth/send-verification-code` |
| POST | `/api/auth/register` |
| POST | `/api/auth/login` |

### users — app/api/v1/users.py

| Methods | Path |
|---|---|
| GET, PATCH, DELETE | `/api/users/me` |
| POST | `/api/users/redeem` |

### settings — app/api/v1/settings.py

| Methods | Path |
|---|---|
| GET | `/api/settings/video-models` |
| GET, POST | `/api/settings/keys` |
| POST | `/api/settings/models` |
| GET, PATCH, DELETE | `/api/settings/keys/{config_id}` |
| POST | `/api/settings/keys/{config_id}/secret` |
| POST, DELETE | `/api/settings/official/{config_id}/activate` |

### admin — app/api/v1/admin.py

| Methods | Path |
|---|---|
| GET, POST | `/api/admin/users` |
| GET | `/api/admin/usage-logs` |
| GET | `/api/admin/error-logs` |
| PATCH, POST, DELETE | `/api/admin/users/{target_user_id}` |
| GET, POST | `/api/admin/invitation-codes` |
| GET, POST | `/api/admin/redemption-codes` |
| GET, POST | `/api/admin/default-models` |
| POST | `/api/admin/model-configs/{config_id}/secret` |
| PATCH | `/api/admin/model-configs/{config_id}` |
| PATCH, DELETE | `/api/admin/default-models/{config_id}` |

### projects — app/api/v1/projects.py

| Methods | Path |
|---|---|
| GET, POST | `/api/projects` |
| PATCH, DELETE | `/api/projects/{project_id}` |
| PATCH | `/api/projects/{project_id}/production-settings` |
| POST | `/api/projects/cover/generate` |
| PUT, DELETE | `/api/projects/{project_id}/cover` |
| GET | `/api/projects/{project_id}/jobs` |
| GET | `/api/projects/{project_id}/models` |
| POST | `/api/projects/{project_id}/cancel` |
| PATCH | `/api/projects/{project_id}/scenes/reorder` |
| PATCH, DELETE | `/api/projects/{project_id}/scenes/{scene_id}` |
| POST | `/api/projects/{project_id}/scenes` |
| DELETE | `/api/projects/{project_id}/references/{kind}/{asset_id}` |
| POST | `/api/projects/{project_id}/parse` |
| POST | `/api/projects/{project_id}/optimize` |
| POST | `/api/projects/{project_id}/generate` |
| POST | `/api/projects/{project_id}/generate-video` |

### episodes — app/api/v1/episodes.py

| Methods | Path |
|---|---|
| GET, POST | `/api/projects/{project_id}/episodes` |
| GET, PATCH, DELETE | `/api/projects/{project_id}/episodes/{episode_id}` |
| POST | `/api/projects/{project_id}/episodes/{episode_id}/breakdown` |
| POST | `/api/projects/{project_id}/episodes/{episode_id}/tone-sheet` |
| POST | `/api/projects/{project_id}/episodes/{episode_id}/storyboard` |

### characters — app/api/v1/characters.py

| Methods | Path |
|---|---|
| GET, POST | `/api/projects/{project_id}/characters` |
| PATCH, DELETE | `/api/projects/{project_id}/characters/{character_id}` |
| POST | `/api/projects/{project_id}/characters/{character_id}/states` |
| PATCH, DELETE | `/api/projects/{project_id}/characters/{character_id}/states/{state_id}` |
| POST | `/api/projects/{project_id}/characters/{character_id}/states/{state_id}/prompt` |
| POST, PUT | `/api/projects/{project_id}/characters/{character_id}/states/{state_id}/image` |
| POST | `/api/projects/{project_id}/characters/{character_id}/sheet` |
| POST | `/api/projects/{project_id}/characters/sheet` |
| PUT | `/api/projects/{project_id}/scenes/{scene_id}/characters` |

### props — app/api/v1/props.py

| Methods | Path |
|---|---|
| GET, POST | `/api/projects/{project_id}/props` |
| PATCH, DELETE | `/api/projects/{project_id}/props/{prop_id}` |
| POST | `/api/projects/{project_id}/props/{prop_id}/prompt` |
| POST, PUT | `/api/projects/{project_id}/props/{prop_id}/image` |
| POST | `/api/projects/{project_id}/props/sheet` |

### voices — app/api/v1/voices.py

| Methods | Path |
|---|---|
| GET, POST | `/api/projects/{project_id}/voices` |
| POST | `/api/projects/{project_id}/voices/design` |
| POST | `/api/projects/{project_id}/voices/import` |
| PATCH, DELETE | `/api/projects/{project_id}/voices/{voice_id}` |
| POST | `/api/projects/{project_id}/voices/{voice_id}/preview` |
| POST | `/api/projects/{project_id}/voices/merge` |

### user_voices — app/api/v1/user_voices.py

| Methods | Path |
|---|---|
| GET | `/api/voices` |
| POST | `/api/voices/design` |
| POST | `/api/voices/{voice_id}/save` |
| DELETE | `/api/voices/{voice_id}` |

### assets — app/api/v1/assets.py

| Methods | Path |
|---|---|
| GET, POST | `/api/projects/{project_id}/assets` |
| PATCH, DELETE | `/api/projects/{project_id}/assets/{asset_id}` |
| POST | `/api/projects/{project_id}/assets/merge` |

### prompts — app/api/v1/prompts.py

| Methods | Path |
|---|---|
| POST | `/api/prompts/compile` |
| GET | `/api/prompts/presets` |
| GET | `/api/prompts/prefix-presets` |
| POST | `/api/prompts/optimize` |

### jobs — app/api/v1/jobs.py

| Methods | Path |
|---|---|
| GET | `/api/jobs/{job_id}` |
| POST | `/api/jobs/{job_id}/cancel` |
| POST | `/api/jobs/{job_id}/retry` |

### exports — app/api/v1/exports.py

| Methods | Path |
|---|---|
| GET, POST | `/api/projects/{project_id}/exports` |
| GET, DELETE | `/api/projects/{project_id}/exports/{export_id}` |

### images — app/api/v1/images.py

| Methods | Path |
|---|---|
| POST | `/api/images/generate` |

### videos — app/api/v1/videos.py

| Methods | Path |
|---|---|
| POST | `/api/videos/generate` |

### chat — app/api/v1/chat.py

| Methods | Path |
|---|---|
| GET | `/api/chat/artifacts/{token}` |
| GET, POST | `/api/chat/sessions` |
| DELETE | `/api/chat/sessions/{session_id}` |
| GET, POST | `/api/chat/sessions/{session_id}/messages` |
| POST | `/api/chat/sessions/{session_id}/messages/stream` |

### usage — app/api/v1/usage.py

| Methods | Path |
|---|---|
| GET | `/api/usage/logs` |

## Execution contracts

| Flow | Current execution / response |
|---|---|
| Character-state/prop prompt or image, project voice design/audition | `202 {job}` → `generation_jobs` → `job_worker` / `job_handlers` |
| Tone sheet, storyboard, legacy `/generate`, `/generate-video` | `202` → attached asyncio task in the API process |
| Export | `202 {export}` → separate `export_jobs` row + asyncio task; not the generation worker |
| Breakdown, optimize, cover, standalone media | Request-scoped provider call; browser abort alone does not guarantee server cancellation |
| Chat | Request/NDJSON stream, translated by the frontend's real BFF stream route |

The worker uses three lanes, 60-second leases, and 20-second heartbeats. Paid jobs have `max_attempts=1`; an expired lease is `WORKER_LOST`, not an automatic paid retry. Manual `/retry` also enforces the attempt cap and returns 409 for an exhausted paid job; a user-requested fresh enqueue is a separate attempt. Clients poll the job or observe its events. Project job-history UI remains absent.

Project cancellation sets an event **and cancels the attached task**. Task cleanup releases the project and resets unfinished media markers; successful files remain. A provider can still bill a request already submitted. Startup clears abandoned project/media state without resuming calls; exports have no equivalent recovery. These mechanisms assume one backend process.

## Data model and behavior notes

- `Project` is a series; `Episode` owns ordered shots. Project serialization includes one episode's scenes and `currentEpisodeId`, not every shot in the series. Resolve an episode before rendering/reordering; an omitted ID selects the highest-numbered live episode.
- `Scene` keeps frame fields separate from motion fields. `target: "video"` breakdown annotates existing shots; `shots`/`both` requires confirmation before replacing any existing rows, including their references/prefixes. `discardsScenes` and `discardsGeneratedScenes` describe the impact.
- `CharacterState` represents parallel or episode-ranged looks; `Prop` records objects/ownership; project `VoiceProfile` and account `UserVoice` have different lifetimes. There is no per-shot TTS pipeline. Setting sheets intentionally contain labels; rendered shot prompts forbid those labels in the finished frame.
- `Asset` is project-owned imported image/video/audio media. Its path may intentionally be an external HTTP(S) URL. Generated/uploaded artifacts use relative local paths and 30-day signed URLs, stable within a UTC day. JWT rotation invalidates old links, not the stored paths.
- Image/video prompt prefixes are ordered, separate columns with a shared deduplicated reference budget. First/last video frames are separate from additional references. Newly generated tone sheets write prefixes to every shot; frames use saved per-shot references, not hidden automatic anchors. Remaining preview/budget/snapshot inconsistencies are explicit in the backlog.
- Render selection skips locked shots by default; explicitly selected locked shots are rejected. `pendingOnly` excludes successes. One run claims the project across episodes; exports read finished clips without this lock. Export selection order is output order, with a 60-clip cap and FFmpeg normalization to the project canvas/FPS.
- SQLModel is the schema source; Alembic owns history/backfills. Some ID columns are deliberately plain, requiring service cleanup/fallback. Typed workbench requests extend `CamelModel`; older dict-body endpoints still perform manual validation. Responses use camelCase, storage/Python snake_case, and timestamps remain ISO strings.
- Money is integer micros internally and strings on the wire, with Decimal arithmetic and immutable pricing snapshots. Personal configs are metered but not charged to account balance; super admins are exempt from official balance gates/deductions.

See [the model map](../docs/architecture/code-map.md#data-model-map), [data flow](../docs/architecture/data-flow.md), and [backlog](../docs/plans/backlog.md) for detail. Preserve existing local data; migration checks belong in temporary databases.

## Realtime and errors

`/ws/projects/{project_id}` authenticates via `sceneflow-auth.<JWT>` in `Sec-WebSocket-Protocol` and provides heartbeat/project broadcasts. Events include project/scene/video/episode, character/prop/voice, job, and deletion updates; the complete current list is in [data flow](../docs/architecture/data-flow.md#realtime-events). The legacy workbench consumes this socket; the episode editor uses 3-second query polling.

Request middleware creates `req_*` IDs and adds `X-Request-Id` to responses passing through it. HTTP 5xx handlers attempt to persist redacted `error_logs`; super admins can search them in the UI or through chat. Stream and background failures use their own error/status channels. See [error inventory](../docs/reference/error-codes.md), [Bug history index](../docs/bugs/README.md), and [logging](../docs/conventions/logging.md).
