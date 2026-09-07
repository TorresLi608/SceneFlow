# AGENTS.md

Shared guidance for coding agents working in SceneFlow. Verified against application code on **2026-09-07**. `CLAUDE.md` imports this file; keep instructions here instead of maintaining two copies.

SceneFlow turns scripts into short-drama series: projects own episodes, episodes own shots, and the workbench manages cast, props, voices, storyboard images, generated clips, and exports. FastAPI + SQLite and Next.js run as two processes. Project voices are timbre references; there is no per-shot TTS pipeline.

## Start here

**[docs/README.md](docs/README.md) is the knowledge-base index.** This file is the orientation layer; detailed rules and current implementation belong in `docs/`.

| Need | Read |
|---|---|
| Find the page, action, service, model, and test for a change | [Code map](docs/architecture/code-map.md) |
| Runtime topology and state ownership | [Overview](docs/architecture/overview.md) |
| Layer boundaries, BFF, jobs, concurrency | [Boundaries](docs/architecture/boundaries.md) |
| Breakdown, references, rendering, cancellation, chat, billing | [Data flow](docs/architecture/data-flow.md) |
| Naming, PATCH, errors, logging, checks | [Conventions](docs/conventions/README.md) |
| Chat UI and stream ownership | [Chat design](docs/design/feature-chat.md) |
| Auth / filtering / money | [Auth](docs/design/feature-auth.md), [Search](docs/design/feature-search.md), [Billing](docs/design/feature-billing.md) |
| Implemented work and verified gaps | [Current state](docs/plans/current-sprint.md), [Backlog](docs/plans/backlog.md) |
| Investigate or fix a bug — read this first | [Bug history index](docs/bugs/README.md), then the matching issue details |
| API contracts and incident diagnosis | [OpenAPI](docs/reference/api-spec.yaml), [Errors](docs/reference/error-codes.md) |
| Setup, ports, environment, Docker | [Local setup](docs/reference/local-setup.md), [Backend reference](backend/README.md) |

Before changing chat, read its design document. Before changing a shared function, find every caller and trace the actual flow; some comments still describe superseded behavior. Record verified discrepancies in the relevant doc instead of copying them into new instructions.

## Bug-fix workflow

Every bug-fix task must follow this workflow, including small fixes:

1. **Read [docs/bugs/README.md](docs/bugs/README.md) first.** Search its summaries by symptom, error code, or module, then read matching issue details before investigating implementation. Check historical fixes against current code; use incident logs when available.
2. **Update the existing issue for the same root cause.** Append recurrence/fix/verification history instead of creating a duplicate summary. New root causes get a separate `docs/bugs/YYYY-MM-DD-short-topic.md` record and a unique index entry.
3. **Before handing off each fix, update both the detail and index.** Record symptoms/reproduction, confirmed root cause, affected code/callers, changes, actual validation commands/results, and remaining limits. The index carries the issue ID, searchable keywords, short summary, status, update date, and detail link. A missing history update means the bug-fix handoff is incomplete.
4. **Do not invent validation or resolution.** Mark unexecuted checks, failures, blockers, and unconfirmed causes explicitly. Migrated historical reports are not fresh passing results. Link existing commits/PRs when known and link the issue detail in the handoff.
5. **Never create bug reports or fix-summary files at the repository root.** `docs/bugs/README.md` is the sole history index; `docs/reference/known-errors.md` is a compatibility pointer only. Keep permanent architecture/convention changes in their owning docs and link them from the issue. Store only redacted minimal evidence, never secrets or complete user/provider payloads.

The index includes the detail template and naming rules. Routine feature work and documentation reorganization do not need invented bug records.

## Commands

Python 3.11, Node 22+, pnpm 10. Use the existing `backend/.venv`; frontend dependencies and lockfile are managed with pnpm.

```bash
# From the repository root, in separate terminals
npm run dev:backend
npm run dev:frontend
```

Backend listens on **8080**, frontend on **4000**. `scripts/dev-backend.mjs` uses `PORT` and terminates processes occupying that port before launch; check the port owner first. Direct uvicorn startup is documented in [local setup](docs/reference/local-setup.md).

```bash
cd backend
check_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_episodes_api test_project_guards
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh $(rg --files tests -g 'test_*.py' | sed 's#^tests/##; s#\.py$##')
```

`run_tests.sh` requires test names as arguments and isolates each file in its own interpreter and temporary database. `tests/run_all.py` uses `runpy` in one process and stops at the first failure; rerun a failing file independently before diagnosing it. There is no pytest.

```bash
cd frontend
pnpm exec tsc --noEmit
pnpm lint
node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts'
```

Use relevant backend self-checks plus frontend typecheck/lint for code changes. Schema changes also need a reviewed Alembic revision and `alembic check` against a temporary database. Regenerate OpenAPI after endpoint/schema changes with the [documented command](docs/conventions/README.md#keeping-generated-docs-current). For documentation-only edits, verify links, commands, and generated contracts; do not claim an old test run as current. `pnpm build` has hung before and is not the routine type gate.

## Ownership to preserve

- **HTTP:** frontend actions use axios `httpClient` → `/api/bff/*` → the fallback rewrite in `frontend/next.config.ts`. Chat uses the AI SDK transport and the only real BFF route, which converts backend NDJSON to an AI SDK UI stream. A new BFF route overrides the proxy for that path and must forward auth/errors itself. Signed media URLs and the legacy WebSocket client can reach the backend directly.
- **State:** React Query owns fetched data, with keys in `frontend/src/actions/query-keys.ts`. Zustand persists auth and preferences only. `project-store` is the legacy editor's in-memory working copy; the episode editor uses React Query plus local drafts. `unsaved-settings-store` holds per-project model-settings dirty flags, not saved configuration or persistent drafts.
- **Backend:** endpoints orchestrate, services own workflows, SQLModel defines tables, Alembic versions them. Text/image routing is in `app/llms/router.py`; video and voice adapters live in their respective services. `app/graph/graphs/context_graph.py` assembles chat history; it is not a durable generation workflow.
- **Jobs:** `job_worker.py` runs inside FastAPI with three lanes. Only character-state/prop images, their prompt drafts, project voice design, and voice auditions use `generation_jobs` today. Tone sheets, storyboard frames, legacy generation, video batches, and exports still use `asyncio.create_task`. `export_jobs` is a separate table, not a generation-worker queue.
- **Stops and restarts:** `runs.cancel()` sets a flag and cancels its attached task; completed media is retained, but a provider already called may still bill. Job cancellation is a database write observed by the heartbeat. Startup clears orphaned project/media busy markers; it does not resume renders. These mechanisms and realtime delivery require a single backend process.

## Invariants

1. **A project is a series.** Resolve an episode before rendering or reordering; order restarts at 1 per episode. Project serialization carries one episode's shots plus episode summaries. `project_and_scenes` is for series-wide operations. The render lock remains project-level; exports read finished files without taking it.
2. **Frame and motion fields are separate.** `visual_prompt` describes a still; `video_prompt`, `camera_move`, `transition`, and `duration_ms` describe motion. `target: "video"` breakdown updates existing shots in place. Replacing shots requires the `applied: false` / `replaceAll` confirmation, even when those shots have no generated media.
3. **Model resolution is project-first with account fallback.** Use `project_model_config`; a missing, disabled, or deleted pick falls through. A model-settings PATCH uses `0` to clear a config ID. Read image limits and `videoCapabilities` from the resolved model; four references is a default, not a universal limit.
4. **References have identity and order.** Store `{kind, id}` selections. Resolve ownership in `reference_service`, combine prefix references before shot references with `prompt_prefix_service`, and compile labels with `prompt_compiler`. Prefixes and shot text share one reference budget. First/last video frames are separate slots. Do not reintroduce hidden storyboard anchors after an explicit removal. Known compatibility gaps are in the backlog.
5. **camelCase on the wire, snake_case in Python/storage.** Typed request bodies extend `CamelModel` (`extra="forbid"`); legacy dict-body endpoints still exist and validate manually. Response serializers build the wire shape; `CamelModel` does not serialize arbitrary response dictionaries.
6. **Preserve explicit empty values in PATCH.** Use `model_dump(exclude_unset=True)` and field-specific validation. For typed workbench PATCHes, absent/`null` means leave alone; `""`, `false`, `0`, and `[]` can be real edits. `value is not None` preserves `false`; truthiness filtering does not. Frame `""` becomes stored JSON `null`, with `…Explicit` flags distinguishing cleared from never chosen.
7. **Generated media stores relative paths, never signed URLs.** `artifact_service` signs links for 30 days, stable within a UTC day. Asset-library imports may intentionally store external HTTP(S) URLs. Key shot rows by stable IDs and reconcile via `updatedAt`, never via a signed URL.
8. **Money is Decimal/strings end to end.** Backend micros and frontend `decimal.js` / `lib/money.ts`; no price round-trip through JS `number`. Gate official calls before execution, meter after success, and keep historical price snapshots.
9. **Alembic owns schema changes.** Change SQLModel first; no runtime `ALTER TABLE` or `create_all()` compatibility logic. Timestamps remain ISO-8601 strings. Preserve manual cleanup for plain ID columns such as character voice bindings.
10. **Secrets stay private.** Passwords use bcrypt, provider keys AES-256-GCM; production rejects development secrets. Signed media URLs are bearer credentials. Log IDs and decisions, not scripts, prompts, chat content, or keys. HTTP 5xx records are redacted and available only to super admins.

## Frontend conventions

- Next.js **16.2.3**, React **19.2.4**, React Compiler enabled. Read the relevant installed guide under `frontend/node_modules/next/dist/docs/` before writing framework code.
- Reuse existing libraries and helpers before custom infrastructure: `@base-ui/react` primitives, shadcn-style organization, `@assistant-ui/react` for the chat composer, `prompt-area` for mentions, and existing provider SDKs. Vendored assistant-ui skills are under `.agents/skills/`.
- All new user-facing strings go into both `zh` and `en` in `frontend/src/lib/i18n.ts`, via `useI18n()`.
- Standalone image/video history is stored separately in localStorage (latest 20 results); saved voices live in the backend. Reset clears only the current editor/preview and restores initial choices, never history or saved voices. An empty video FPS capability list means omit the parameter, not default to 24.
- Route-local components live in `_components/`; shared primitives in `src/components/ui/`. Preserve accessibility and comments explaining constraints.
- Quote paths containing `[projectId]`, `[episodeId]`, or route-group parentheses in shell commands.

## Local data and documentation

`data/app.db` and `backend/private_generated/` contain real local data. Do not reset, overwrite, or delete them unless explicitly asked. `DATABASE_URL` is the only database setting; when unset/empty, it defaults to the absolute repository-root `data/app.db`. Use a temporary `DATABASE_URL` (e.g. `sqlite:////tmp/sceneflow-check/app.db`) **and** `SCENEFLOW_PRIVATE_GENERATED_DIR` for checks that import/start the app. The test runner overrides `DATABASE_URL` with a temporary database. Development login defaults to `superAdmin` / `superAdmin@123`; `SCENEFLOW_SUPER_ADMIN_USERNAME` configures the login name.

Update the relevant `docs/` page when a rule changes; update the code map when ownership or paths move, and `backend/README.md` when endpoints, environment variables, or provider behavior change. Keep plans factual: separate source-verified gaps from user reports and do not invent owners, schedules, or passing checks.
