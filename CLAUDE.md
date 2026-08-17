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
.venv/bin/python tests/run_all.py                                     # whole suite; see caveat below
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

**`tests/run_all.py` is not isolated.** It `runpy`s every file in one process, so module-level state from one file leaks into the next, and the first failure aborts the run — later files never execute. At the current HEAD all 28 files pass individually but `run_all.py` dies in `test_characters_api.py` (reproducible with `test_artifact_service.py` or `test_admin_usage_logs.py` running first in the same process). Treat a `run_all.py` failure as unproven until you rerun that file on its own.

## Architecture

### Request path

The browser never calls the backend directly. Components call `src/actions/*` (axios `httpClient`, which injects the JWT and logs out on 401), which hit `/api/bff/*` on the Next.js origin. `next.config.ts` declares a **fallback** rewrite from `/api/bff/:path*` to `${BACKEND_API_BASE_URL}/api/:path*` — fallback, so a real route file wins over the proxy. Today only the chat stream (`src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts`) is a real route: it translates the backend's NDJSON into an AI SDK UI stream. Everything else is pure proxy. Adding a route file under `app/api/bff/**` silently takes that path over from the rewrite.

Server state is React Query, keyed through `src/actions/query-keys.ts`. Zustand holds client state only: `user-store` (persisted auth), `preferences-store` (locale/theme), `project-store` (session-scoped project/episode/scene working copy). Project and shot data is never persisted client-side — the backend SQLite is the source of truth.

### Data model

`Project` is a **series** and owns no shots directly. Content hangs off `Episode`, and each `Scene` is one shot inside an episode. Shot `order` restarts at 1 per episode, so a serialized project carries **one** episode's shots under `scenes`, plus `episodes` (summaries) and `currentEpisodeId`. Anything that renders or reorders resolves a target episode first; `episode_service.resolve_episode` defaults to the highest-numbered episode. `project_service.project_and_scenes` spans the whole series and is only for series-wide work.

`Character` + `CharacterState` are the series bible that keeps a cast member's look, image model, and voice stable across episodes; `Prop` does the same for objects; `SceneCharacter` records who is in a shot. A state is one look a character can appear in (an age, an outfit) and holds a turnaround sheet; states are parallel forms by default, and pinning `from_episode` is what turns one into a change at a point in the series. `character_service.resolve_character` folds the state covering an episode over the card, and a state overrides only the fields it sets. Because providers cap reference images at `MAX_REFERENCE_IMAGES` = 4, a cast of any size reaches the renderer as a merged sheet built by `media_service.merge_images` — sources scaled to one uniform width **before** tiling, then compressed under 10MB. At render time a shot's cast contributes appearance prompts (work everywhere) and reference images (passed image-to-image through `edit_image` — this is what actually holds a face steady).

`VoiceProfile` is the same idea for sound, and there is **no per-shot TTS**: voices are managed once per project, auditioned one line at a time, and ffmpeg-concatenated into `projects.voice_sheet_path` — a timbre reference the video model hears, not a finished soundtrack. A character binds to a profile through `characters.voice_profile_id`, a plain column rather than a foreign key (SQLite cannot add a constrained column in place), so `voice_service.delete_voice_profile` clears bindings by hand.

Starting work takes a conditional UPDATE on `projects.status` (`claim_project_status`), so a double-clicked button cannot start two runs. The lock is **project-level** even though rendering is per-episode: one run owns the series at a time.

### Rendering an episode

`storyboard_service.run_storyboard` is the path that matters. Rendering shots independently gives each frame its own sampling of lighting, palette, set dressing, and render style — the cast sheet pins faces and nothing else — so an episode renders in two passes: a **tone sheet** (thumbnails of every shot in one sampling, stored on `episodes.tone_image_path`, never a deliverable) fixes the look, then each shot renders full-resolution carrying that sheet, the merged context sheet, and **the previous shot's render**. Consequences: shots render sequentially, not fanned out, because each references its predecessor; a failed tone sheet aborts the batch rather than billing for unanchored frames; and re-running reuses the existing anchor unless `regenerate` is set, since resampling restyles shots the user already approved.

### Backend layers

`app/api/v1/` (endpoints, orchestration) → `app/services/` (business logic) → `app/models/` (SQLModel tables, the single source of truth for the schema). `app/llms/router.py` owns provider switching and nothing else; services own workflows. `app/graph/` holds context assembly and agent orchestration (SQLite history → token budget → summary compression → model messages). LangGraph is reserved for checkpointed LLM decisions and human approval; the `generation_jobs` table (persistence, idempotency, leases, cancel, retry) is the intended home for deterministic image/TTS/video/FFmpeg work — though the worker does not exist yet and generation still starts in the API process via `asyncio.create_task`.

### Invariants that bite

- **camelCase in, snake_case out.** Every request body extends `CamelModel` (`app/schemas/requests.py`) with `alias_generator=to_camel` and `extra="forbid"` — a misspelled field is a 422, never a silent no-op. Responses are shaped in `app/schemas/serializers.py`.
- **Timestamps are ISO-8601 strings, not `datetime`.** The code compares them as strings and the API passes them straight through.
- **Media is stored as a path relative to `SCENEFLOW_PRIVATE_GENERATED_DIR`, never as a URL.** Signed links expire after 30 days, so a stored URL would turn every asset in a long-running series into a 404. `serializers.py` mints a fresh signed link per response. Columns are `image_path`/`audio_path`.
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
