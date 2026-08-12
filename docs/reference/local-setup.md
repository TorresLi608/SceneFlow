# Local setup

Runbook for getting SceneFlow running on a development machine. Backend env vars are listed in `../../backend/README.md`; architecture is in `../architecture/overview.md`.

## Requirements

- Python 3.11
- Node.js 22+, pnpm 10

**This is a pnpm project.** `npm install` will not update `pnpm-lock.yaml`, so a dependency added that way is invisible to everyone else. Use `pnpm add`.

## 1. Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

From the repo root, `npm run dev:backend` runs the same uvicorn command against the existing venv.

- API: `http://127.0.0.1:8080`
- Health: `http://127.0.0.1:8080/healthz` → `{"status":"ok"}`
- OpenAPI UI: `http://127.0.0.1:8080/docs`
- WebSocket: `ws://127.0.0.1:8080`

On startup the backend initialises SQLite, runs the compatibility migrations, and creates the super admin if it is missing:

| | |
|---|---|
| Username | `superAdmin` |
| Password | `superAdmin@123` (development default) |

Production startup **refuses to boot** while `SCENEFLOW_JWT_SECRET`, `SCENEFLOW_AES_KEY`, or `SCENEFLOW_SUPER_ADMIN_PASSWORD` are still the development defaults.

## 2. Frontend environment

```bash
cd frontend
cp .env.example .env.local
```

Four variables are read by the code:

| Variable | Read by | Default if unset |
|---|---|---|
| `BACKEND_API_BASE_URL` | `next.config.ts` rewrite, `lib/http/backend-client.ts` | `http://127.0.0.1:8080` |
| `NEXT_PUBLIC_API_BASE_URL` | fallback for `backend-client.ts` only | — |
| `NEXT_PUBLIC_BFF_BASE_URL` | axios `baseURL` | empty → same origin, i.e. the Next BFF |
| `NEXT_PUBLIC_WS_BASE_URL` | browser WebSocket target | `ws://127.0.0.1:8080` |

> **`.env.example` is incomplete** — it ships only `NEXT_PUBLIC_API_BASE_URL`, which is the legacy fallback. The defaults cover a standard local run, so copying it as-is works, but a non-default backend port needs the full set:

```env
NEXT_PUBLIC_BFF_BASE_URL=
NEXT_PUBLIC_WS_BASE_URL=ws://127.0.0.1:8080
BACKEND_API_BASE_URL=http://127.0.0.1:8080
```

Changing `.env.local` requires restarting the dev server.

**Never put a real credential in `.env.local` that the app does not read.** The file is gitignored, but it is still plaintext on disk.

## 3. Frontend

```bash
cd frontend
pnpm install
pnpm dev            # or `npm run dev:frontend` from the repo root
```

`http://localhost:3000`

## 4. Verify

1. Backend first — `http://127.0.0.1:8080/healthz` returns `{"status":"ok"}`.
2. Then the frontend — open `http://localhost:3000`.
3. Log in as `superAdmin` / `superAdmin@123`, or register a new account (registration consumes an invitation code — create one from the admin pages).

## Troubleshooting

**Frontend requests fail.** Confirm the backend is on 8080 and that `frontend/.env.local` points at it. Restart the dev server after editing.

**Port already in use.** Start the backend elsewhere and point the frontend at it:

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8090
```

```env
BACKEND_API_BASE_URL=http://127.0.0.1:8090
NEXT_PUBLIC_WS_BASE_URL=ws://127.0.0.1:8090
```

**Reset local data.** The database is `backend/sceneflow.db`. Stop the backend, delete the file, restart. **Do not do this casually** — it is real development data and is gitignored, so there is no recovering it from the repo. For a throwaway database, point the process at a temp path instead:

```bash
SCENEFLOW_DB_PATH=/tmp/sf-scratch.db .venv/bin/python -m uvicorn app.main:app --port 8099
```

Generated media lives under `backend/private_generated/` and is also gitignored.

## Production build

```bash
cd frontend && pnpm build && pnpm start
cd backend  && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

`pnpm build` has hung in this project before — see `../conventions/testing.md` for the fallback and why `tsc --noEmit` is the routine type gate.

## Shell notes

**Quote bracketed Next.js route paths.** zsh treats `[projectId]` as a glob and fails with `no matches found`:

```bash
cat 'src/app/projects/[projectId]/page.tsx'      # correct
cat src/app/projects/[projectId]/page.tsx        # zsh: no matches found
```

**Run backend Python from `backend/`.** The package root is that directory; running a test or script from the repo root raises `ModuleNotFoundError: No module named 'app'`.
