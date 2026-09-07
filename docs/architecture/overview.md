# Architecture overview

Verified on **2026-09-07**. Use the [code map](code-map.md) to find concrete files and [data flow](data-flow.md) to trace a feature.

SceneFlow turns scripts into storyboarded short-drama series. A project owns episodes and a shared cast/prop/voice bible; episodes own shots, storyboard frames, and generated clips. Voice profiles supply timbre references to video generation, not a per-shot TTS soundtrack.

## Processes and stack

```text
Browser ── /api/bff/* ──▶ Next.js :4000 ── /api/* ──▶ FastAPI :8080
                           fallback proxy              ├── SQLite
                           + chat stream adapter       ├── private_generated/
                                                       ├── provider APIs / FFmpeg
                                                       └── in-process job worker
Browser ── signed artifact URL ──────────────────────▶ FastAPI
Legacy workbench ── /ws/projects/:id ─────────────────▶ FastAPI
```

| Side | Runtime | Main dependencies |
|---|---|---|
| Backend | Python 3.11, uvicorn | FastAPI, SQLModel/SQLAlchemy, Alembic, LangChain, provider SDKs, Pillow, PyJWT, cryptography |
| Frontend | Node 22+, pnpm 10 | Next.js 16.2.3, React 19.2.4 + React Compiler, React Query 5, Zustand 5, Tailwind 4, Base UI |
| Chat UI | Frontend | AI SDK 7 / `@ai-sdk/react` 4, `@assistant-ui/react` 0.14 line, Streamdown |
| Media/editor | Both | `prompt-area`, dnd-kit; backend FFmpeg/ffprobe and Pillow |

Versions above follow the manifests; [frontend/package.json](../../frontend/package.json), its pnpm lockfile, and [backend/requirements.txt](../../backend/requirements.txt) are the dependency sources. LangGraph arrives through LangChain; no app-authored checkpointed production graph is configured. Read installed Next.js guides under `frontend/node_modules/next/dist/docs/` before changing framework code.

## Request topology

Ordinary business HTTP calls go through `frontend/src/actions/*` and the shared axios client to `/api/bff/*` on the Next origin. The rewrite in `next.config.ts` is a **fallback**: a real route file takes precedence.

The only real BFF route is [the chat stream adapter](../../frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts). AI SDK `DefaultChatTransport` calls it directly from the chat controller; it forwards auth, translates backend NDJSON into UI-stream events, and propagates errors. It is an explicit exception to the actions/axios path.

Media links are absolute signed URLs rooted at `SCENEFLOW_PUBLIC_BASE_URL`; browser image/video/download requests can therefore reach the backend directly. The legacy workbench also opens the backend WebSocket using `NEXT_PUBLIC_WS_BASE_URL` and the `sceneflow-auth.<JWT>` subprotocol. The current episode editor does not open a socket: it polls project and episode queries every three seconds while busy and invalidates the episode at completion.

## State ownership

| State | Home | Notes |
|---|---|---|
| Users, series, episodes, shots, bible, assets, chat, usage, jobs, errors | SQLite | Source of truth for business data |
| Generated/uploaded media | `SCENEFLOW_PRIVATE_GENERATED_DIR` | Relative stored paths; signed URLs generated for responses |
| External asset imports | `assets.path` | Deliberate HTTP(S)-URL exception; these are not signed local files |
| Fetched server data | React Query | Shared keys in `frontend/src/actions/query-keys.ts` |
| Auth and preferences | Persisted Zustand stores | User/token and locale/theme only |
| Standalone image/video history | Per-surface localStorage lists | Latest 20 results/prompts; separate from project/shot data and preserved by editor reset |
| Saved standalone voices | Backend `user_voices` + React Query | Reset clears the selection/draft, not saved voices |
| Current episode/shot drafts | Component state | Saved through actions, reconciled with query results |
| Legacy workbench project copy | `project-store.ts` | In memory; server reload and WebSocket reconciliation |
| Unsaved model-settings flag | `unsaved-settings-store.ts` | In memory per project; does not preserve the settings draft |
| Active render cancel flags / socket subscriptions | Backend process memory | Not shared across workers |

Do not persist project or shot data in localStorage. Stable shot IDs are React keys; `updatedAt` drives draft synchronization. Asset URLs are not row identities.

## Startup and execution

`app/main.py::lifespan` configures logging, upgrades Alembic to `head`, seeds/enables the configured super admin, calls `release_orphaned_runs()`, then starts the generation-job worker. Shutdown stops the worker.

- The worker has three lanes and four registered types: reference images, prompt drafts, project voice design, and auditions. Jobs persist in `generation_jobs`; leases and cancellation are database state.
- Tone sheets, storyboard runs, legacy image batches, shot video batches, and exports still start as asyncio tasks in the API process. `export_jobs` stores export progress separately; a row is not a durable executor.
- Startup marks abandoned project/episode runs failed and clears media `generating` flags while retaining completed artifacts. It does not resume provider calls or recover pending exports.
- WebSocket subscriptions, project task cancellation, and startup lock cleanup assume **one backend process**. A second worker could both miss broadcasts and clear a lock held by the first.

## Domain shape

A `Project` is a series; `Episode` is an installment; `Scene` is one shot. Shot order restarts at 1 per episode. A serialized project includes one episode's shots, episode summaries, and `currentEpisodeId`; resolving without an episode ID selects the highest-numbered live episode.

`Character` + `CharacterState`, `Prop`, and `VoiceProfile` make the series bible. `SceneCharacter` records cast membership; frame and motion prompts are separate fields. `Asset` holds project media imports, and ordered prompt prefixes share the same media budget as a shot's own mentions. First/last video frame slots are separate from additional references. See [data flow](data-flow.md) for resolution and compatibility details.

## Operations

- Backend **8080**, frontend development **4000**. `GET /healthz` returns `{"status":"ok"}` without probing storage or the worker.
- Development login: `superAdmin` / `superAdmin@123`. Production rejects the default JWT, AES, and super-admin secrets.
- `DATABASE_URL` is the only database setting; local fallback is repository-root `data/app.db`. Docker defaults to `/app/data/app.db`, with Compose binding the host data directory at `/app/data`. [Local setup](../reference/local-setup.md#docker-deployment) covers permissions, backups, and migrating old storage.
- `SCENEFLOW_SUPER_ADMIN_USERNAME` customizes the login; the legacy default account is renamed in place. [Authentication](../design/feature-auth.md#super-admin) documents collision handling and subsequent changes.
- The development launcher can kill processes occupying `PORT`; use the [local runbook](../reference/local-setup.md) before starting another server.
- [Backend reference](../../backend/README.md) lists environment variables/providers/endpoints. [Backlog](../plans/backlog.md) separates current gaps from field reports.
