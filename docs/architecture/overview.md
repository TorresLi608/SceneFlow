# Architecture overview

SceneFlow turns a script into a storyboarded short-drama series: parse text into shots, render an image and a voice track per shot, and keep the cast looking the same across episodes.

Two processes, one repo. Neither is a library of the other; they talk over HTTP and one WebSocket.

```
browser ──▶ Next.js (port 4000)  ──▶ FastAPI (port 8080) ──▶ SQLite (backend/sceneflow.db)
             app + BFF proxy            API + services         private_generated/ (media)
                   ▲                          │
                   └────── ws://…/ws/projects/:id ──────┘
```

## Stack

| Side | Runtime | Core libraries |
|---|---|---|
| `backend/` | Python 3.11, uvicorn | FastAPI, SQLModel (SQLAlchemy 2.x), LangChain, LangGraph, PyJWT, cryptography |
| `frontend/` | Node 22+, pnpm 10 | Next.js 16 (App Router, React Compiler), React 19, React Query, Zustand, assistant-ui, AI SDK, Tailwind 4, `@base-ui/react` |

The Next.js version has breaking changes relative to most training data — read the relevant guide in `frontend/node_modules/next/dist/docs/` before writing framework code.

## Runtime topology

**The browser never calls the backend directly.** Components call `src/actions/*`, which hit `/api/bff/*` on the Next origin. `next.config.ts` declares a *fallback* rewrite from `/api/bff/:path*` to `${BACKEND_API_BASE_URL}/api/:path*`. Fallback means a real route file wins over the proxy; today only the chat stream is a real route. See `boundaries.md` for why that matters when adding routes.

The one exception is the WebSocket: the browser opens `ws://…/ws/projects/:id` straight against the backend using `NEXT_PUBLIC_WS_BASE_URL`, authenticating through the `sceneflow-auth.<JWT>` subprotocol because browsers cannot set headers on a WebSocket handshake.

## Where state lives

| State | Home | Notes |
|---|---|---|
| Users, projects, episodes, shots, characters, chat, usage | SQLite | The only source of truth for business data |
| Generated media | `backend/private_generated/` | Referenced by relative path; served only via expiring signed URLs |
| Server cache | React Query | Keys centralised in `src/actions/query-keys.ts` |
| Auth token, locale, theme | Zustand persisted (`localStorage`) | Nothing else is persisted client-side |
| Working copy of the open project/episode | Zustand session store | Discarded on reload; the server is re-read |

A standing product rule: project and shot CRUD always goes to the backend. Do not add business data to `localStorage`.

## Backend layout

| Path | Owns |
|---|---|
| `app/api/v1/` | Endpoints, request/response orchestration, auth dependencies |
| `app/services/` | Business logic (project, episode, character, generation, chat, usage, job, artifact, tts, video, config, agent) |
| `app/models/` | SQLModel tables — the schema source used by Alembic autogenerate |
| `migrations/` | Alembic schema versions and historical data migrations |
| `app/schemas/` | `requests.py` (Pydantic bodies), `serializers.py` (response shaping) |
| `app/llms/` | Provider routing and the model registry; provider switching lives here and nowhere else |
| `app/graph/` | Context assembly and agent orchestration |
| `app/core/` | Config, database/engine, logging, security, realtime broadcast |
| `tests/` | Executable self-checks (no pytest) |

## Frontend layout

| Path | Owns |
|---|---|
| `src/app/(workspace)/` | Authenticated pages; route-local UI in `_components/` |
| `src/app/projects/[projectId]/` | The workbench (episode editor, scene cards, character panel, production settings) |
| `src/app/api/bff/` | Real BFF routes only where the proxy is not enough |
| `src/actions/` | Every HTTP call the UI makes, plus `query-keys.ts` |
| `src/store/` | Zustand stores |
| `src/lib/` | http client, i18n, money, project factory, provider metadata |
| `src/components/ui/` | Shared shadcn-style primitives |

## Domain shape in one paragraph

A `Project` is a **series** and owns no shots directly. Content hangs off `Episode`, and each `Scene` is one shot inside an episode. `Character` + `CharacterState` form the series bible that keeps a cast member's look, image model, and voice stable across episodes; `Prop` does the same for objects; `SceneCharacter` records who appears in a shot. Shot order restarts at 1 per episode, so a serialized project carries **one** episode's shots. Full detail in `data-flow.md` and the root `CLAUDE.md`.

## Operational facts

- Ports: backend 8080, frontend 4000. Health check: `GET /healthz` → `{"status":"ok"}`.
- Startup upgrades Alembic to `head`, then creates `superAdmin` if missing (dev password `superAdmin@123`).
- Production startup **refuses to boot** on the development JWT, AES, or super-admin secrets.
- Env vars are listed in `backend/README.md`; setup, ports, and troubleshooting in `../reference/local-setup.md`.
