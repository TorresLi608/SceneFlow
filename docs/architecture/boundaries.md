# Boundaries

Which layer may call which, and the crossings that have caused bugs here before. When a change forces you to violate one of these, that is a design signal — raise it rather than routing around it.

## Backend call direction

```
api/v1/  ──▶  services/  ──▶  models/          (+ core/ available to all)
   │             │
   │             └──▶ llms/ (providers)   graph/ (context + agents)
   └──▶ schemas/ (requests in, serializers out)
```

**Rules**

1. **Endpoints orchestrate; services decide.** An endpoint may validate, resolve the current user, call services, and shape a response. Business rules that another caller would need go in `app/services/`.
2. **`app/llms/router.py` owns provider switching and nothing else.** It knows base URLs, adapters, and per-provider quirks. It must not know about projects, episodes, or billing. Services call it.
3. **`app/models/` is the schema source; Alembic versions it.** Change the SQLModel first, generate and review a revision under `backend/migrations/versions/`, then run `alembic check`. `init_db()` upgrades to `head`; it does not mutate schema itself.
4. **Historical compatibility belongs in migrations, not runtime startup code.** Runtime queries and data backfills use SQLModel/SQLAlchemy expressions where the mapped schema permits it.
5. **Do not hold a database session across a provider call.** SQLite has one writer. The established shape is: short session to authorise and load config → `await` the provider → new short session to write results and usage.
6. **Serializers own the wire shape.** Never return an ORM entity directly; `app/schemas/serializers.py` is where signed URLs get minted and fields get renamed.

## Frontend call direction

```
page / _components  ──▶  actions/  ──▶  /api/bff/*  ──▶  backend /api/*
        │                                  ▲
        └──▶ store/ (client state)         └── rewrite in next.config.ts (fallback)
```

**Rules**

1. **Components never call `axios`/`fetch` against the backend directly.** Every request goes through `src/actions/*`, which uses the shared `httpClient` that injects the JWT and logs out on 401.
2. **The rewrite is a `fallback`, so any file you add under `src/app/api/bff/**` silently takes that path over from the proxy.** Add a route file only when you must transform the payload — today the only one is the chat stream, which converts backend NDJSON into an AI SDK UI stream. If you add one, it is now responsible for auth forwarding and error shape.
3. **Server state belongs to React Query, client state to Zustand.** Do not mirror fetched data into a store "so it is easier to read" — the exception is the project/episode working copy, which exists because the workbench edits optimistically and reconciles over WebSocket.
4. **No user-facing string literals in components.** Add the key to both `zh` and `en` in `src/lib/i18n.ts` and read it through `useI18n()`.
5. **Route-local components live in `_components/` beside their page.** Promote to `src/components/ui/` only when a second route needs it.
6. **Fetch per route, not globally.** Projects load on `/ai-script`; model configs load on `/chat` and `/images`. Nothing hoists a query into the shared layout "so it is ready" — that pulls unrelated data and client modules onto every route.

### Route structure

- `(workspace)` is a **route group**: a shared authenticated layout with no URL segment. Use native Next.js composition rather than wrapper components that fake a layout.
- **Active navigation derives from `usePathname()`**, never from a duplicated `activeView` state.
- `AppSidebar` is deliberately concrete. There is one sidebar in this app; a configurable navigation framework would be abstraction without a second caller.
- `/admin` is a `redirect()` to `/admin/models`, keeping the old address alive without a second admin shell.

## The frontend/backend contract

- **The frontend speaks camelCase; the backend speaks snake_case.** `CamelModel` bridges both directions automatically, so neither side translates by hand.
- **`extra="forbid"`**: an unknown field is a 422, not a silently dropped value. A typo in a request body fails loudly — keep it that way.
- **`null` means "leave alone" in a PATCH.** To clear a value the client sends `""` or `false`. Backend code that filters with `is not None` will drop legitimate `false` values; this has already broken `isLocked: false` once.
- **Money crosses the wire as strings** (micros). Never parse a price into a JS number.
- **Timestamps are ISO-8601 strings on both sides**, never `datetime` objects — the code compares them as strings and the API passes them through.

## Media boundary

Generated media is referenced by a **path relative to `SCENEFLOW_PRIVATE_GENERATED_DIR`**, never by URL. Signed links expire after 30 days, so a URL stored in a row would turn every asset in a long-running series into a 404. `serializers.py` mints a fresh signed link per response. The columns are `image_path`/`audio_path`; older databases may retain unused `image_url`/`audio_url` columns.

## Orchestration boundary

- **LangGraph** is reserved for checkpointed LLM decisions and human approval (script structure, continuity review).
- **`generation_jobs`** is the home for deterministic image/video/TTS/FFmpeg work. It provides persistence, idempotency, leases, cancel, and retry, and `app/services/job_worker.py` is the consumer that drains it.
- **The migration is half done.** Reference images, prompt drafts, voice design, and voice auditions are queued (`app/services/job_handlers.py`). Storyboard, tone sheet, project generation, and export still start in the API process via `asyncio.create_task`, and `app/core/runs.py` cancellation is in-process for that reason. For those, the jobs table is still the destination rather than the current path.
- **The worker runs in-process, not as a second process.** `app/core/realtime.py` keeps its WebSocket registry in one process's memory and `docker-compose.yml` runs a single backend container, so a worker started elsewhere could not deliver a single `SCENE_UPDATE`. A shared broker is the prerequisite for splitting it out (see `../plans/backlog.md`); that is a separate change. What the queue buys even in-process is a stop that is a database write rather than a hung-up socket, plus a row that outlives a restart.

A handler receives the job as `job_json` — a plain dict, never an ORM row — because it runs long after the claiming session closed. Holding a session across a provider call is forbidden outright (see the session boundary above). The resolved model configuration is looked up inside the handler rather than carried in `input_json`: a resolved config holds a decrypted provider API key, and jobs are long-lived rows the user can list over the API.

## Concurrency boundary

Starting work takes a conditional UPDATE on `projects.status` (`claim_project_status`), so a double-clicked button cannot start two runs over the same rows. **The lock is project-level even though rendering is per-episode** — one run owns the series at a time. Anything that would let two runs touch one series concurrently needs a new locking story, not a wider status value.
