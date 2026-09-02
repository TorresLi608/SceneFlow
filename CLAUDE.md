# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

SceneFlow turns a script into a storyboarded short-drama series: parse text into shots, render an image and a voice track per shot, keep the cast looking the same across episodes. Two processes — a FastAPI + SQLite backend and a Next.js frontend.

**`docs/` is the working knowledge base.** This file is the orientation layer; `docs/` carries the detail and is the thing to update when a rule changes.

| Need | Read |
|---|---|
| How the system fits together | `docs/architecture/overview.md` |
| What may call what, and why | `docs/architecture/boundaries.md` |
| Parse / render / chat / billing traced end to end | `docs/architecture/data-flow.md` |
| The rules that break things when violated | `docs/conventions/README.md` → naming, error-handling, testing, logging |
| A feature's design and known gaps | `docs/design/feature-{auth,chat,search,billing}.md` |
| What is being worked on / what is open | `docs/plans/current-sprint.md`, `docs/plans/backlog.md` |
| Endpoint contracts, error inventory | `docs/reference/api-spec.yaml` (generated), `docs/reference/error-codes.md` |
| First-time setup, ports, troubleshooting | `docs/reference/local-setup.md` |

Before changing the chat surface, read `docs/design/feature-chat.md` — assistant-ui and the AI SDK split ownership there in a way that a framework quickstart will tell you to undo.

## Commands

Backend (Python 3.11, venv already at `backend/.venv`):

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080   # or: npm run dev:backend (from repo root)
PYTHONPATH=. .venv/bin/python tests/test_episodes_api.py              # one test file — the reliable way to run tests
sh scripts/run_tests.sh $(ls tests/test_*.py | xargs -n1 basename | sed 's/\.py$//')   # whole suite, one process per file
```

Frontend (Node 22+, pnpm 10):

```bash
cd frontend
pnpm dev                                                # or: npm run dev:frontend (from repo root)
pnpm lint                                               # eslint
pnpm exec tsc --noEmit                                  # typecheck — run this, `pnpm build` is slow and has hung before
node --no-warnings --experimental-strip-types --test src/lib/money.test.mts
```

The usual pre-commit gate is: backend tests, then frontend `tsc --noEmit` and `pnpm lint`.

### Testing notes

There is no pytest and no frontend test framework. Backend tests are plain modules that call their own test functions from `if __name__ == "__main__"`, driving the real ASGI app through `TestClient` with providers monkeypatched out. Frontend tests are `*.test.mts` run by Node's built-in runner with type stripping (note the `.ts` extension in their relative imports — required by stripping).

**`tests/run_all.py` is not isolated.** It `runpy`s every file in one process, so module-level state from one file leaks into the next, and the first failure aborts the run — later files never execute. Use `scripts/run_tests.sh` instead: one interpreter and one throwaway database per file, every result reported. Treat a `run_all.py` failure as unproven until you rerun that file on its own.

## Architecture

### Request path

The browser never calls the backend directly. Components call `src/actions/*` (axios `httpClient`, which injects the JWT and logs out on 401), which hit `/api/bff/*` on the Next.js origin. `next.config.ts` declares a **fallback** rewrite from `/api/bff/:path*` to `${BACKEND_API_BASE_URL}/api/:path*` — fallback, so a real route file wins over the proxy. Today only the chat stream (`src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts`) is a real route: it translates the backend's NDJSON into an AI SDK UI stream. Everything else is pure proxy. Adding a route file under `app/api/bff/**` silently takes that path over from the rewrite.

Server state is React Query, keyed through `src/actions/query-keys.ts`. Zustand holds client state only: `user-store` (persisted auth), `preferences-store` (locale/theme), `project-store` (session-scoped project/episode/scene working copy). Project and shot data is never persisted client-side — the backend SQLite is the source of truth.

### Data model

`Project` is a **series** and owns no shots directly. Content hangs off `Episode`, and each `Scene` is one shot inside an episode. Shot `order` restarts at 1 per episode, so a serialized project carries **one** episode's shots under `scenes`, plus `episodes` (summaries) and `currentEpisodeId`. Anything that renders or reorders resolves a target episode first; `episode_service.resolve_episode` defaults to the highest-numbered episode. `project_service.project_and_scenes` spans the whole series and is only for series-wide work.

A `Scene` carries a **frame side** (`narration`, `dialogue`, `speaker_character_id`, `visual_prompt`, `shot_type`) and a **motion side** (`camera_move`, `transition`, `video_prompt`, `duration_ms`). They are separate on purpose: one describes a frame, the other describes several seconds, and collapsing them produced clips that either stood still or ignored the composition the storyboard image had already fixed. `transition` is a property of the seam rather than the frame, so it never reaches the still prompt.

**Which model a call uses is project-first.** `config_service.project_model_config` reads the project's `text/image/video/audio_config_id`, and an unset pick — or one whose config was deleted or disabled — falls through to the account default. The same row holds the generation defaults (image resolution/ratio, video quality/ratio/duration/fps) so a storyboard and the clips made from it agree. Those four id columns are plain, not foreign keys, for the same reason as `characters.voice_profile_id`. In a PATCH, **`0` clears a pick** — `null` already means "leave alone".

`Character` + `CharacterState` are the series bible that keeps a cast member's look, image model, and voice stable across episodes; `Prop` does the same for objects (and `owner_character_id` records whose it is, drawn onto the reference); `SceneCharacter` records who is in a shot. A state is one look a character can appear in (an age, an outfit) and holds a turnaround sheet; states are parallel forms by default, and pinning `from_episode` is what turns one into a change at a point in the series. `character_service.resolve_character` folds the state covering an episode over the card, and a state overrides only the fields it sets. Because providers cap reference images at `MAX_REFERENCE_IMAGES` = 4, a cast of any size reaches the renderer as a merged sheet built by `media_service.merge_images` — sources scaled to one uniform width **before** tiling, then compressed under 10MB. At render time a shot's cast contributes appearance prompts (work everywhere) and reference images (passed image-to-image through `edit_image` — this is what actually holds a face steady).

Those sheets are **setting sheets**: they carry names and written setting alongside the drawing, so a reference is self-describing. That is why `prompt_service.shot_prompt` states so firmly that the rendered shot must contain no text — a labelled reference passed image-to-image will otherwise copy its captions into the episode. The built-in instruction templates in `prompt_service` are not user-overridable; `CharacterState.system_prompt` and `Prop.system_prompt` are retained but read by nothing.

`VoiceProfile` is the same idea for sound, and there is **no per-shot TTS**: voices are managed once per project, auditioned one line at a time, and ffmpeg-concatenated into `projects.voice_sheet_path` — a timbre reference the video model hears, not a finished soundtrack. A profile is created by designing a timbre (`POST .../voices/design`, Qwen voice design, provider and model taken from the project's audio config) or by importing one from the account library. A character binds to a profile through `characters.voice_profile_id`, a plain column rather than a foreign key (SQLite cannot add a constrained column in place), so `voice_service.delete_voice_profile` clears bindings by hand.

Starting work takes a conditional UPDATE on `projects.status` (`claim_project_status`), so a double-clicked button cannot start two runs. The lock is **project-level** even though rendering is per-episode: one run owns the series at a time. `POST /api/projects/:id/cancel` sets a flag in `app/core/runs.py` that the run polls **between shots** — cooperative, so a frame the provider is already drawing finishes and is kept; the run releases the lock as it unwinds, never the cancel endpoint.

### Breaking a script into shots

`POST /api/projects/:id/episodes/:episodeId/breakdown` (`breakdown_service` + `ModelRouter.breakdown_script`) is the path the episode editor uses. `target` splits it: `shots` fills the frame side, `video` fills the motion side **in place** so re-deriving camera moves cannot discard rendered frames, `both` fills everything. `references` decides what the model defers to, and the three cases are distinct — a selected character *with* a drawn sheet is named so the prompt says "参照《…》三面图"; one with only written setting is reasoned about from that text; anyone the bible has never heard of is invented from the script. Selecting nothing is a valid fourth case. Re-splitting reports `applied: false` with `discardsGeneratedScenes` before it destroys anything.

`POST /api/projects/:id/parse` still produces the old narration-plus-frame-prompt shape and still serves the legacy single-screen editor. The two schemas are not compatible, which is why `breakdown_script` sits beside `parse_script` rather than replacing it.

### Rendering an episode

`storyboard_service` is the path that matters. Rendering shots independently gives each frame its own sampling of lighting, palette, set dressing, and render style — the cast sheet pins faces and nothing else — so an episode renders in two passes: a **tone sheet** (thumbnails of every shot in one sampling, stored on `episodes.tone_image_path`, never a deliverable) fixes the look, then each shot renders full-resolution carrying that sheet, the merged context sheet, and **the previous shot's render**. The anchor is its own endpoint (`/tone-sheet`) so the user can approve it before paying for a frame per shot; `/storyboard` still generates one when none exists. Consequences: shots render sequentially, not fanned out, because each references its predecessor; a failed tone sheet aborts the batch rather than billing for unanchored frames; and re-running reuses the existing anchor unless `regenerate` is set, since resampling restyles shots the user already approved. `sceneIds` selects a subset, so one shot regenerates and several render as a batch through the same path.

### Backend layers

`app/api/v1/` (endpoints, orchestration) → `app/services/` (business logic) → `app/models/` (SQLModel tables, the single source of truth for the schema). `app/llms/router.py` owns provider switching and nothing else; services own workflows. `app/graph/` holds context assembly and agent orchestration (SQLite history → token budget → summary compression → model messages). LangGraph is reserved for checkpointed LLM decisions and human approval; the `generation_jobs` table is the home for deterministic image/TTS/video/FFmpeg work, drained in-process by `app/services/job_worker.py`.

**The queue migration is half done.** Reference images, prompt drafts, voice design, and voice auditions are queued — those endpoints return `202 {job}` and the work happens in a handler in `app/services/job_handlers.py`. Storyboard, tone sheet, project generation, and export still start in the API process via `asyncio.create_task`. The reason any of this moved: **Starlette does not cancel a handler when the client disconnects**, so with the work inside the request a stop button could only hang up the browser while the provider call ran on and billed. Stopping is now a database write the worker notices within a heartbeat. Paid jobs carry `max_attempts=1` and are never retried automatically — a dead worker may or may not have been billed, so `/api/jobs/:id/retry` is a decision the user makes. On the client, `src/actions/job-actions.ts` enqueues and polls, so callers still await one value; a passed `AbortSignal` now cancels the *job*.

### Invariants that bite

- **camelCase in, snake_case out.** Every request body extends `CamelModel` (`app/schemas/requests.py`) with `alias_generator=to_camel` and `extra="forbid"` — a misspelled field is a 422, never a silent no-op. Responses are shaped in `app/schemas/serializers.py`.
- **Timestamps are ISO-8601 strings, not `datetime`.** The code compares them as strings and the API passes them straight through.
- **Media is stored as a path relative to `SCENEFLOW_PRIVATE_GENERATED_DIR`, never as a URL.** Signed links expire after 30 days, so a stored URL would turn every asset in a long-running series into a 404. `serializers.py` mints a fresh signed link per response. Columns are `image_path`/`audio_path`. The link is **stable for a given file within a day** (`_sign` floors `iat` to the UTC day), which is what lets a browser cache a frame while the editor polls — so **key list rows on `updatedAt`, never on an asset URL**, or every poll remounts the list.
- **Money is `Decimal`/strings end to end** (`decimal.js` on the frontend, micros in `lib/money.ts`). Never round-trip a price through a JS number.
- **Alembic owns schema changes.** Change the SQLModel first, generate and review an Alembic revision, then run `alembic check`. `init_db()` upgrades to `head`; do not add runtime `ALTER TABLE` or `create_all()` compatibility logic.
- **PATCH semantics distinguish absent from false.** The backend drops `null` fields to mean "leave alone", so a client clearing a value sends `""`/`false`, not `null`. Filtering with `is not None` on the backend has broken `isLocked: false` before.
- WebSocket auth rides the subprotocol: `sceneflow-auth.<JWT>` in `Sec-WebSocket-Protocol` on `/ws/projects/:id`. Events: `WS_CONNECTED`, `PROJECT_UPDATE`, `SCENE_UPDATE`.
- Passwords are bcrypt; provider API keys are AES-256-GCM encrypted. Production startup rejects the development JWT/AES/super-admin secrets.

Backend env vars, the full endpoint list, and provider support are documented in `backend/README.md` — keep it current when you change either.

## Conventions

- **Next.js 16 + React 19 with the React Compiler on.** This version has breaking changes versus what you may remember — APIs, conventions, and file structure all differ. Read the relevant guide in `frontend/node_modules/next/dist/docs/` before writing framework code rather than assuming.
- **Check for an existing library before hand-rolling.** A standing instruction from the user: use mature open-source or an existing dependency; write custom code only when nothing fits or the library clearly adds complexity. LangChain/LangGraph on the backend, `@base-ui/react` + shadcn-style organization on the frontend, `@assistant-ui/react` for chat UI (do not rebuild composer/thread behavior it already ships). Skills for assistant-ui are vendored under `.agents/skills/`; an MCP docs server is available via `npx -y @assistant-ui/mcp-docs-server`.
- **All UI strings go in `frontend/src/lib/i18n.ts`**, in both the `zh` and `en` dictionaries, reached through `useI18n()`. No literal user-facing text in components.
- Route-local components live in `_components/` next to the page that uses them; shared primitives in `src/components/ui/`.
- Comments in this codebase explain *why*, not *what* — several encode hard-won constraints (see `project-store.ts`, `generation_service.py`, `main.py`). Match that when editing; don't strip them.

## Local data

`backend/sceneflow.db` is real local development data and is gitignored. Do not reset, overwrite, or delete it unless asked — point a test at a temp path with `SCENEFLOW_DB_PATH` instead. Same for `backend/private_generated/`. The default super admin is `superAdmin` / `superAdmin@123`.

## Repo docs

`docs/` (indexed at the top of this file) is the maintained knowledge base — architecture, conventions, feature designs, plans, and generated reference. Keep it current; it is the only place where a rule change belongs.

The one doc outside it is `backend/README.md` — env vars, full endpoint list, provider support, data-model notes.

Earlier notes (`AI_HANDOFF.md`, the `AI_SHORT_DRAMA_*.md` specs, `findings.md`, `RUNNING.md`, `progress.md`, `task_plan.md`) and the per-directory `AGENTS.md`/`CLAUDE.md` files were folded into `docs/` and removed. Their history is still in git — `git log --diff-filter=D --name-only` finds them, `git show <commit>^:<path>` reads one.
