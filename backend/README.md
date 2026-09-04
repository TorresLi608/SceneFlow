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
- `scripts/`: developer helpers that are not part of the app.

`Pillow` builds the merged reference sheets and `ffmpeg` concatenates audio; `ffprobe`
measures clip length. Both binaries ship in the Docker image and must be on PATH locally.

Run all backend checks:

```bash
cd backend
# One process and one throwaway database per file. `tests/run_all.py` runpy's everything in a
# single process and aborts on the first failure, so state leaks between files and a green run
# there proves less than it looks.
sh scripts/run_tests.sh $(ls tests/test_*.py | xargs -n1 basename | sed 's/\.py$//')
```

Check a schema change without touching the real development database:

```bash
cd backend
SCENEFLOW_DB_PATH=/tmp/sf_check.db .venv/bin/alembic upgrade head
SCENEFLOW_DB_PATH=/tmp/sf_check.db .venv/bin/alembic check   # must report no new operations
rm -f /tmp/sf_check.db
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
- Image generation supports OpenAI, Gemini, and Qwen/Wan; video supports Doubao, Gemini, and Qwen/Wan; standalone voice work supports Qwen Voice Design only. `/api/voices/design` creates an unsaved preview and `/api/voices/:id/save` saves it.
- Qwen chat defaults to the OpenAI-compatible `https://dashscope.aliyuncs.com/compatible-mode/v1` endpoint. Native image/video calls use DashScope's media APIs; voice design uses the configured Qwen `baseUrl`, with fixed API model `qwen-voice-design` and the user-entered `modelSeries` as `target_model`. `GET /api/settings/video-models` returns the video models the admin picker suggests — `wan2.7`, `wan2.7-r2v`, `wan3.0-video`, `wan3.0-video-prime`, and the Seedance ids below — with the capabilities each implies; the field stays editable so relay model ids still work. Media type names follow the model family: Wan 3.0 uses `reference_image` / `reference_video` / `reference_audio` plus the `audio` output switch, Wan 2.7 uses `reference_image` / `reference_video` / `reference_voice`, and older models keep `video` / `driving_audio`. Configurable video quality is `480p`, `720p`, `1080p`, `2K`, or `4K`.
- Doubao Seedance video uses the official `volcengine-python-sdk[ark]` `Ark.content_generation.tasks` API, with the configured `baseUrl` passed through unchanged so official and relay endpoints use the same code. Known model IDs include `doubao-seedance-2.0`, `doubao-seedance-2.0-fast`, `doubao-seedance-2.0-mini`, and `doubao-seedance-2.5`. The catalog follows the provider capability table: 2.5 accepts 30 images + 10 videos + 10 audios and 4–30 second output; the 2.0 variants accept 9 images + 3 videos + 3 audios and 4–15 second output.
- New model configurations start with an empty `modelSeries`. Model discovery does not filter by purpose: it uses the provider or relay `/models` endpoint when available, while native Qwen media returns its known models. Voice Design leaves `modelSeries` user-editable and does not run discovery. Saving never performs a remote connectivity check; enabled configs still require their local fields and API key.
- Image configurations store `imageMaxReferenceImages` (default 4, non-negative); image generation rejects reference uploads above the selected model's configured limit.
- `POST /api/prompts/optimize` uses the active script model to optimize image, video, or voice-generation text with media-specific instructions and returns the result for review without starting generation. Image/video callers may choose automatic, Chinese, or English output; voice text always keeps its source language.

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

### Voice design (JWT required)
- `GET /api/voices`
- `POST /api/voices/design`
- `POST /api/voices/:id/save`

### Admin (superAdmin required)
- `GET /api/admin/users`
- `GET /api/admin/usage-logs?search=&page=&pageSize=`
- `GET /api/admin/error-logs?search=&errorCode=&projectId=&requestId=&page=&pageSize=`
- `PATCH /api/admin/users/:id`
- `DELETE /api/admin/users/:id`
- `GET /api/admin/default-models`
- `POST /api/admin/default-models`
- `PATCH /api/admin/default-models/:id`
- `DELETE /api/admin/default-models/:id`

Official script configs support OpenAI-compatible relays by setting `provider: "custom"`,
`modelSeries`, and `baseUrl` such as `https://www.juaiapi.com/v1`.

### Prompt optimization (JWT required)
- `POST /api/prompts/optimize` — rewrites a prompt with the active script model and returns the
  editable result. `kind` picks the wording: `image` / `video` / `voice` / `audio` /
  `character` / `prop` / `cover`. `context.outputLanguage` (`auto` / `zh` / `en`) chooses the
  language it answers in
  - the three setting-sheet kinds (`character`, `prop`, `cover`) deliberately preserve the
    on-image labelling the reference depends on rather than optimising it away
- `GET /api/prompts/presets?kind=character|prop|cover` — built-in starting templates, so a
  blank prompt box is never the only option. Static text; no model call and no balance check
- `GET /api/prompts/prefix-presets?projectId=&sceneId=` — ready-to-insert prefix prompts
  (前置提示词) for one shot's quick-fill bar. Only the tone-sheet preamble exists today, and the
  list comes back empty until the episode has an anchor: the wording is about locating this
  shot's cell in the grid. Served rather than templated in the browser so it stays identical
  to what a successful tone sheet writes
- `POST /api/prompts/compile` — `{ projectId, kind, sceneId?, prompt, dialogue?, references[],
  prefixes[] }` → the editor's `@素材` rewritten to the provider's positional `图N` / `视频N` /
  `音频N`. `prefixes` are combined server-side, prefix-first, so the previewed numbering is
  the numbering the render sends

### Projects (JWT required)
- `GET /api/projects` — the caller's live series, each with its current episode's shots
- `POST /api/projects` — `{ "title", "description", "coverPrompt", "originalScript", "productionSettings" }`
- `PATCH /api/projects/:id` — title, description, cover prompt, source script, series bible,
  and `modelSettings` (below)
- `DELETE /api/projects/:id` — soft-deletes the series
- `POST /api/projects/cover/generate` — draws a cover from `{ "prompt", "title", "stylePrompt" }`
  and returns it as `{ "imageData": "data:image/png;base64,..." }`
  - `prompt` is the subject and is required. The cover used to be derived from the title and
    synopsis, which meant the only way to change the picture was to rewrite the story
  - project-less on purpose: the create dialog runs before a project row exists, and the edit
    dialog runs against unsaved edits. Nothing is written; the caller applies the result below
  - synchronous, and requires an active image configuration (`openai`/`gemini`/`qwen`)
- `PUT /api/projects/:id/cover` — stores an uploaded or generated cover from a base64 data URL
  (png/jpeg/webp, 10MB ceiling); the row keeps a path, and responses mint a signed link
- `DELETE /api/projects/:id/cover` — drops the cover so the card falls back to the placeholder
- `POST /api/projects/:id/cancel` — asks whatever this project is rendering to stop
  - cooperative, not an interrupt: the run checks the flag between shots, so a frame the
    provider is already drawing finishes and is kept. A stopped run reports `partial` when
    something landed and `idle` when nothing did — never `failed`
  - the run releases the busy lock as it unwinds; this endpoint never does, or a second
    render could start while the first is still writing
  - `{ "canceled": false }` when nothing was running is a normal answer, not an error

### Project model configuration (JWT required)
- `GET /api/projects/:id/models` — what each purpose actually resolves to, plus the limits the
  UI must enforce (`imageMaxReferenceImages`; the video config's declared `videoCapabilities`).
  Never returns an API key
- set them through `PATCH /api/projects/:id` under `modelSettings`:
  `textConfigId` / `imageConfigId` / `videoConfigId` / `audioConfigId`, plus the defaults every
  render in the series starts from — `imageResolution`, `imageRatio`, `videoQuality`,
  `videoAspectRatio`, `videoDuration`, `videoFps`, `videoPromptExtend`
  - **project-first, never project-only.** An unset pick, or one whose config was deleted or
    disabled, falls through to the account default (`active_model_config`), so a series made
    before this panel existed keeps working
  - **`0` clears a pick**; `null` cannot, because in a PATCH it already means "leave alone"

### Project Parse (JWT required)
- `POST /api/projects/:id/parse`
  - request body: `{ "script": "...", "model": "gpt-4o", "episodeId": null, "replaceAll": false }`
  - parses script to scenes and persists them into one episode; `episodeId` omitted targets
    the current (highest-numbered) episode
  - Re-splitting is destructive. When the target episode already has shots carrying a
    generated image or voice track, the response comes back with `applied: false`,
    `discardsGeneratedScenes: N`, and the parsed shots under `pendingScenes` instead of
    overwriting them. The client confirms, then repeats the call with `replaceAll: true`.
  - **Legacy.** It produces only `narration` + `visualPrompt`, which is a comic storyboard —
    silent on how the camera moves, how the cut is made, and how long the shot runs. The
    episode editor uses `/breakdown` below; this serves the old single-screen editor, whose
    schema the wider one is not compatible with.

### Episodes (JWT required)
- `GET /api/projects/:id/episodes` — summaries (no script, no shots) plus a shot count each
- `POST /api/projects/:id/episodes` — append the next episode; `title` is required, and the
  number comes from the highest live one, so a soft-deleted number is reused
- `GET /api/projects/:id/episodes/:episodeId` — the episode with its script and ordered shots
- `PATCH /api/projects/:id/episodes/:episodeId` — title, synopsis, source text, status
- `DELETE /api/projects/:id/episodes/:episodeId` — soft-deletes the episode and its shots;
  refused with 409 while the project is busy, since a run holds those rows open
- `POST /api/projects/:id/episodes/:episodeId/breakdown` — splits the script into shots that a
  renderer and a video model can both act on
  - `{ "target", "script", "references", "replaceAll", "model" }`
  - `target` picks which half is produced. `shots` fills narration, dialogue, speaker, frame
    prompt, and shot size. `video` fills camera move, transition, duration, and motion prompt.
    `both` fills everything
  - **`target: "video"` updates the existing rows in place** rather than replacing them:
    re-deriving how the camera moves is no reason to discard frames already rendered and paid
    for. It requires existing shots and 400s without them
  - `references` — `characterIds` / `propIds` / `voiceProfileIds` plus `useCastSheet` /
    `usePropSheet` / `useVoiceSheet` — decides what the model defers to. A selected character
    **with** a drawn sheet is named, so the prompt says "参照《…》三面图" instead of
    re-describing a face the renderer already pins; one with only written setting is reasoned
    about from that text; anyone the bible has never heard of is invented from the script.
    Selecting nothing is a valid fourth case: decide everything from the script
  - re-splitting is destructive in the same way as `/parse`: `applied: false` plus
    `discardsGeneratedScenes` first, `replaceAll: true` to confirm
  - `speaker` is matched back to a character by name and aliases, best-effort — an unmatched
    speaker is a walk-on working as intended
- `POST /api/projects/:id/episodes/:episodeId/tone-sheet` — anchors the episode's look, on its own
  - one image holding thumbnails of every shot in a single sampling. Never a deliverable —
    each cell is far too small — but one sampling is what makes lighting, palette, and render
    style agree across the episode
  - its own step because every frame that follows is matched against it: approving it first is
    much cheaper than discovering after twenty full-resolution renders that the episode is wrong
  - `references` selects existing character, character-state, prop, or episode-tone images by `{kind, id}`;
    selected images are tiled into one reference before the provider call
- `POST /api/projects/:id/episodes/:episodeId/storyboard` — renders frames against that anchor
  - `sceneIds` selects a subset — one shot to regenerate, several for a batch. Omitted means
    every unlocked shot; all-locked is a 400 rather than a silent no-op
  - generates the tone sheet first when none exists, so a caller that skipped the step above
    still gets an anchored render rather than twenty unrelated frames
  - each frame carries the tone sheet, user-selected image references, and the previous
    shot's render, capped by the active image model's `imageMaxReferenceImages`
  - shots render **sequentially**, because each references its predecessor's output, and the
    loop checks the cancel flag between them
  - a failed tone sheet aborts the run rather than rendering unanchored shots the user
    would still be billed for
  - `references` explicitly selects project-owned images. Requests that omit it retain the
    legacy cast-sheet / prop-sheet / `previousEpisodeId` behaviour
  - `regenerate` resamples the tone sheet instead of reusing it; the editor sends it only
    from the explicit tone-sheet action, not from frame generation

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
  - `preset` names which built-in template to draft against (`GET /api/prompts/presets`). The
    instruction template itself is **not** overridable: it *is* the system prompt, and offering
    an editable copy of it beside the prompt that draws gave users two fields where one was
    meant. `CharacterState.system_prompt` is retained but read by nothing
- `POST /api/projects/:id/characters/:characterId/states/:stateId/image` — draws the state's
  turnaround sheet from the approved prompt, and freezes the provider/model that produced it
  - the sheet is a *setting sheet*: it carries the character's name, summary, and setting
    alongside the drawing, so the reference is self-describing. `shot_prompt` states firmly
    that the rendered shot must carry no text, or those captions leak into the episode
  - drawn at the project's `imageRatio` / `imageResolution`
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
  - `ownerCharacterId` records whose prop it is, and the reference image is labelled with it —
    an unattributed object is the first thing continuity loses. `""` unbinds; a JSON null reads
    as an absent field. Responses resolve it to `ownerName` so a card renders without a second
    request. A plain column, not a foreign key, matching `characters.voice_profile_id`
- `POST /api/projects/:id/props/:propId/prompt` — draft the image prompt for review; takes the
  same `preset`, and the same non-overridable instruction template, as characters
- `POST /api/projects/:id/props/:propId/image` — draw it; `PUT` the same path uploads one instead
- `POST /api/projects/:id/props/sheet` — tile every prop into one sheet, each cell labelled with
  its owner where it has one

### Voices (JWT required)
Per-shot TTS is gone. Voices are managed once per project, and what the pipeline consumes is
the merged track — every voice introducing itself in its own timbre, so a video model given
it as a reference can keep speakers apart.
- `GET /api/projects/:id/voices`, `POST /api/projects/:id/voices`, `PATCH .../:voiceId`, `DELETE .../:voiceId`
  - deleting releases every character bound to the profile; the binding is a plain column
    rather than a foreign key, so the service does what ON DELETE SET NULL would have
- `POST /api/projects/:id/voices/design` — designs a timbre from a description and binds it to
  the series in one step: `{ "name", "voicePrompt", "previewText", "note", "sampleText" }`
  - provider and model come from the project's audio configuration, never from the request.
    The old form asked the user to type them, which is how a series ended up with profiles no
    synthesiser here could voice
  - the result is also saved to the account's voice library: a timbre that cost a paid request
    should be reusable in the next series for free
  - the provider call is async, so a client disconnect actually cancels it
- `POST /api/projects/:id/voices/import` — bind a timbre already in the account library
  (`{ "userVoiceId", "name", "note", "sampleText" }`). Copies the audition rather than
  referencing it, so the series survives a library tidy-up
- `POST /api/projects/:id/voices/:voiceId/preview` — synthesises the sample line with local
  Edge/system TTS so the user can audition it; unsupported providers fall back to built-in Edge
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
- `GET /api/jobs/:id` — one job, for a client waiting on the work it queued. Its own endpoint
  rather than filtering the project list: a panel waiting on one image should not pull every
  job in the series on a three-second interval.
- `POST /api/jobs/:id/cancel`
- `POST /api/jobs/:id/retry`

- `POST /api/projects/:id/generate-video`
  - `sceneIds` selects a subset — one shot to regenerate, several for a batch
  - renders one clip per shot; models cap out at a handful of seconds, so an episode is
    assembled from clips rather than generated in one call
  - the prompt is `video_prompt` first, falling back to `visual_prompt`: the latter describes a
    still, and a clip generated from it tends to hold still. The shot's camera move and
    transition are appended — they reach the video model or nothing
  - duration comes from the shot's `duration_ms`, clamped to the model's declared min/max, and
    falls back to the project default when the breakdown gave no estimate. One fixed length
    for a six-second beat and a two-second reaction is the pacing problem the estimate fixes
  - the project's saved video defaults sit under whatever the request sent, so a batch started
    from the episode editor renders at the settings the model panel shows
  - `references` selects project-owned images, rendered scene videos, and voice samples by
    `{kind, id}`. The storyboard frame still occupies the first image slot when supported;
    every media kind and count is validated against the model's declared capabilities
  - `withAudio` remains for older callers that pass the merged timbre track
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

`generation_jobs` provides persistence, idempotency, leases, cancel, and retry, and `app/services/job_worker.py` drains it in-process (three lanes, started and stopped by the app lifespan; set `SCENEFLOW_WORKER_ENABLED=0` to keep it down, which is what the tests do so they can drive the queue by hand).

Queued today, via handlers in `app/services/job_handlers.py`: character-state and prop reference images, prompt drafts, project voice design, and voice auditions. Those endpoints return **202 with a `job`** rather than the finished row — poll `GET /api/jobs/:id`, or wait for the `PROP_UPDATE`/`CHARACTER_UPDATE`/`VOICE_UPDATE` broadcast the handler emits. Storyboard, tone sheet, project generation, and export still start in the API process via `asyncio.create_task`; the project job UI is still pending.

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
instead. The link is **stable for a given file within a day** — `_sign` floors `iat` to the
start of the UTC day rather than reading the clock, so the same artifact yields the same URL
across responses. That is what lets a browser cache a frame and a list row stay mounted while
the editor polls; key list rows on `updatedAt`, never on an asset URL. The baseline Alembic
migration upgrades older rows in place and drops references whose token no longer decodes,
since those links were already dead.

A `Scene` carries both halves of a shot. The frame side is `narration`, `dialogue`,
`speaker_character_id`, `visual_prompt`, and `shot_type`; the motion side is `camera_move`
(运镜), `transition` (场景过渡, a property of the seam rather than the frame, which is why it
never reaches the still prompt), `video_prompt`, and `duration_ms`. They are separate because
one describes a frame and the other describes several seconds — collapsing them produced clips
that either stood still or ignored the composition the storyboard image had already fixed.

Each of those two prompts also carries an ordered list of **prefix prompts** (前置提示词) in
`image_prompt_prefixes_json` / `video_prompt_prefixes_json`: `{id, name, prompt, references,
source}` items concatenated ahead of the prompt at compile time. Stored beside the prompt
rather than inside it, so re-running the breakdown — which rewrites `visual_prompt` and
`video_prompt` wholesale — cannot take the episode-level context with it. Their `@素材`
mentions are real reference slots: `prompt_prefix_service.combined_references` folds them and
the shot's own into one deduplicated, prefix-first list, which is also the order
`compile_prompt` numbers `图1`, `图2`… in. A successful tone sheet writes one item with
`source: "tone"` into every shot of the episode, pointing each at its own cell in the grid;
regenerating rewrites that item in place rather than stacking a second copy, and the editor's
quick-fill preset (`GET /api/prompts/prefix-presets`) reproduces it after a user deletes one.

A character card pins a look, an image model, and a voice. A `CharacterState` is one look
that character can appear in — an age, an outfit, a transformation — and its
`reference_image_path` holds a turnaround sheet (front, three-quarter, profile in one image).
States are parallel forms by default; pinning `from_episode` is what turns one into "this one
changed in episode 5" without the drift being accidental. `character_service.resolve_character`
folds the state covering an episode over the card, and a state only overrides the fields it
actually sets — an empty appearance prompt means "the look did not change". Overlapping ranges
resolve to the latest change, and an unpinned state never wins that resolution.

`Prop` is the same idea one level down, for objects rather than people. `owner_character_id`
records whose it is and is drawn onto the reference; it is a plain column rather than a foreign
key for the same reason as `characters.voice_profile_id` — SQLite cannot add a constrained
column in place. The four `projects.*_config_id` columns are plain for the same reason, and a
pick that no longer resolves simply falls back to the account default.

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
`negative_prompt` ride along on the same payload. Project voice-profile auditions use local
Edge/system TTS and do not consume the standalone Voice Design configuration.

## Short-drama orchestration
- LangGraph is reserved for checkpointed LLM decisions and human approval, such as script structure and continuity review.
- `generation_jobs` plus `app/services/job_worker.py` owns deterministic image, video, TTS, and FFmpeg tasks. Reference images, prompt drafts, voice design, and auditions run there now; storyboard, tone sheet, project generation, and export have not moved yet. Project voice auditions remain local Edge/system TTS.
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
