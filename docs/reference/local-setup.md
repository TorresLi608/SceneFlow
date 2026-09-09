# Local setup

Verified on **2026-09-07**. See [the code map](../architecture/code-map.md) for owners and [backend/README.md](../../backend/README.md) for the complete environment/endpoint reference.

## Requirements

Python 3.11, Node.js 22+, pnpm 10, and FFmpeg/ffprobe on PATH for voice auditions and media merging. Docker includes the media binaries. Frontend dependency changes use pnpm so `frontend/pnpm-lock.yaml` stays current.

## Backend

For a first setup:

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
test -f .env || cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

For an existing checkout, reuse `.venv` and the local `.env`. Process environment overrides values loaded from `backend/.env`.

| Address | Purpose |
|---|---|
| `http://127.0.0.1:8080/healthz` | Process health: `{"status":"ok"}`; no DB/worker probe |
| `http://127.0.0.1:8080/docs` | Live FastAPI OpenAPI UI |
| `ws://127.0.0.1:8080/ws/projects/:id` | Legacy project WebSocket |

### Root development commands

Run these from the repository root, with backend/frontend in separate terminals:

```bash
npm run install:backend
npm run install:frontend
npm run dev:backend
npm run dev:frontend
```

`install:backend` uses `scripts/install-backend.mjs`: it reuses the venv or creates one using the first available Python executable. Ensure that executable is the intended Python version. `install:frontend` delegates to pnpm.

`dev:backend` uses `scripts/dev-backend.mjs`, not a bare uvicorn alias. It selects the platform-specific venv interpreter, reads `PORT` (default 8080), **terminates processes occupying that port**, starts uvicorn without reload, forwards SIGINT/SIGTERM/SIGHUP, and cleans up its child on exit. Inspect the port owner first; use direct uvicorn with a free `--port` to avoid taking over another service.

### Startup and account

Startup upgrades Alembic, creates/enables the configured super admin, clears orphaned project/media busy flags, and starts the three-lane job worker. It retains completed media but does not resume interrupted provider calls. `SCENEFLOW_WORKER_ENABLED=0` disables queue consumption for manual tests.

Development login defaults to **`superAdmin` / `superAdmin@123`**. Set `SCENEFLOW_SUPER_ADMIN_USERNAME` and `SCENEFLOW_SUPER_ADMIN_PASSWORD` in `backend/.env`. The username is trimmed and must contain 3–64 characters. Startup only uses the configured password when creating the account; it does not reset an existing password. Changing the legacy default name renames the same admin row, preserving its ID and owned data. Occupied names fail startup; [authentication](../design/feature-auth.md#super-admin) covers subsequent name changes. Production rejects the default JWT, AES, and super-admin secrets.

SQLite uses `DATABASE_URL` for both local development and deployment. When unset or empty, it defaults to `<repository>/data/app.db`, an absolute path independent of the launch directory. Explicit relative SQLite URLs retain working-directory semantics, normally relative to `backend/`. Parent directories are created before engine initialization. Both startup and Alembic use this configuration; no schema migration is needed just to change a database location.

Registration requires an invitation code. Email is optional; supplying it requires a verification code. SMTP settings are listed in [the backend reference](../../backend/README.md#environment). With SMTP host/user absent, the current implementation logs the code instead of sending it, without checking the environment; configure SMTP for deployed email registration.

## Frontend environment and start

```bash
cd frontend
test -f .env.local || cp .env.example .env.local
pnpm install
pnpm dev
```

The dev script runs `next dev -p 4000`: open `http://localhost:4000`.

| Variable | Read by | Default |
|---|---|---|
| `BACKEND_API_BASE_URL` | Fallback rewrite and server `backend-client.ts` | `http://127.0.0.1:8080` |
| `NEXT_PUBLIC_API_BASE_URL` | Legacy fallback in `backend-client.ts`, not the rewrite | None |
| `NEXT_PUBLIC_BFF_BASE_URL` | Axios `baseURL` | Empty → same origin |
| `NEXT_PUBLIC_WS_BASE_URL` | Legacy workbench WebSocket | `ws://127.0.0.1:8080` |

Restart after environment changes. `NEXT_PUBLIC_*` values used in browser bundles are build-time configuration for production. The episode editor uses HTTP polling; it does not require its own WebSocket subscription. Signed media URLs use the backend's `SCENEFLOW_PUBLIC_BASE_URL`, which must be reachable from the browser.

To use backend port 8090, start direct uvicorn with `--port 8090`, set `BACKEND_API_BASE_URL=http://127.0.0.1:8090` and `NEXT_PUBLIC_WS_BASE_URL=ws://127.0.0.1:8090`, and set backend `SCENEFLOW_PUBLIC_BASE_URL` accordingly for media links.

## Verify and check changes

1. Confirm `/healthz`, then load the frontend and log in.
2. Open the relevant route from [the code map](../architecture/code-map.md).
3. Run the scoped [testing gate](../conventions/testing.md). Do not start paid provider calls just to validate a documentation or UI-only change.

For migration development, use a disposable database:

```bash
cd backend
schema_dir=$(mktemp -d)
DATABASE_URL="sqlite:///$schema_dir/check.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$schema_dir/media" .venv/bin/alembic upgrade head
# After changing SQLModel, generate and review a revision before applying it.
DATABASE_URL="sqlite:///$schema_dir/check.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$schema_dir/media" .venv/bin/alembic revision --autogenerate -m "description"
DATABASE_URL="sqlite:///$schema_dir/check.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$schema_dir/media" .venv/bin/alembic upgrade head
DATABASE_URL="sqlite:///$schema_dir/check.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$schema_dir/media" .venv/bin/alembic check
```

Only generate a revision when intentionally changing schema. Reuse [regen_api_spec.py](../../backend/scripts/regen_api_spec.py) with the [isolated command](../conventions/README.md#keeping-generated-docs-current) for HTTP schema updates.

## Docker deployment

```bash
# From the repository root; configure production secrets before starting in production.
test -f backend/.env || cp backend/.env.example backend/.env
npm run docker:up
```

`docker:up` builds and starts the services; `docker:build` remains useful for preparing images separately. Compose runs one backend and one frontend, exposing 8080/4000.

| Data | Container location | Persistent storage |
|---|---|---|
| SQLite database and its WAL/SHM/journal files | `/app/data/app.db` and adjacent files | Whole host directory `${SCENEFLOW_DATA_DIR:-./data}` bound to `/app/data` |
| Generated media | `/app/backend/private_generated` | Named volume `sceneflow_media` |

Rebuilds, container recreation, and `docker compose down` preserve both. `down -v` deletes the media volume, although the database bind mount remains. Losing either the database or media breaks the installation. Neither storage is automatically imported from the old database volume or the local development directories.

For a server, put `SCENEFLOW_DATA_DIR=/srv/sceneflow/data` in the repository-root `.env`, so replacing a release checkout does not switch to another empty `./data`. Compose reads this variable and any `DATABASE_URL` override from the host environment/root `.env`, not `backend/.env`. The Compose default URL is `sqlite:////app/data/app.db`; keep overrides inside `/app/data`. The standalone image has the same default URL but still needs a directory mount, e.g. `--mount type=bind,src=/srv/sceneflow/data,dst=/app/data`.

The image creates `/app/data` for UID 10001 (`app`). Since a bind mount hides image ownership, `docker-entrypoint.sh` starts as root, assigns the mounted data directory to `app`, sets directory mode `0700`, then uses `gosu` to execute the backend as `app`. SQLite startup sets the database file to `0600`. A deployment that overrides `--user` must prepare matching host permissions itself. Filesystems that prohibit ownership changes also need operator-side permissions. Git and both Docker build contexts exclude data directories, database files, and SQLite sidecars.

```bash
npm run docker:backup
```

`backup.sh` exports the entire `/app/data` directory and generated media to a timestamped archive under ignored `backups/`. It briefly stops a running backend for a consistent snapshot and restores its prior running state, including after a failed copy. New archives contain `data/` (including any WAL/SHM files) and `private_generated/`; old archives contained `sceneflow.db` at the archive root. Restore into empty target storage rather than overlaying a database onto unrelated WAL files. Persistence does not replace this backup, so `docker:backup` is retained along with `docker:up`.

Configure `SCENEFLOW_ENV=production`, a chosen admin username, non-development secrets, public media origin, and appropriate CORS/browser addresses before deploying beyond localhost. Preserve the existing AES/JWT secrets when moving data; generating a new AES key makes existing provider keys unreadable.

### Migrating existing data

Do this before the first startup with the new mount, after stopping every process that uses the source database. The following examples use the new default filename `app.db` and refuse to overwrite an existing destination. Keep the old Docker volume and a backup until login, projects, and media have been verified. The local procedure removes the old database files after checking the migrated database's integrity.

**Old Compose named volume (`sceneflow_db`).** Build the new backend image, then stop the old backend. The old configuration already used a persistent named volume, so ordinary image rebuilds should retain it; a missing deployment's volume still needs investigation, not an assumed recovery.

```bash
docker compose build backend
docker compose stop backend
docker compose run --rm --no-deps -T --user root --entrypoint python \
  --volume sceneflow_db:/legacy:ro backend - <<'PY'
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile

destination = Path("/app/data/app.db")
if not Path("/legacy/sceneflow.db").is_file() or destination.exists():
    raise SystemExit("Source missing or destination already exists; migration stopped")
destination.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as snapshot:
    # Copy the whole stopped database directory, including any uncheckpointed WAL.
    shutil.copytree("/legacy", snapshot, dirs_exist_ok=True)
    with closing(sqlite3.connect(Path(snapshot) / "sceneflow.db")) as source:
        with closing(sqlite3.connect(destination)) as target:
            source.backup(target)
destination.chmod(0o600)
PY
docker compose up -d --build
```

The source volume is read-only and remains intact. The media volume name is unchanged. If the old database was stored in a container's writable layer instead, export its actual database directory (including sidecars) from that old container before replacing it, then use a SQLite backup from the exported copy. Data from an already-deleted writable layer cannot be recovered by a path change.

**Old local development database (`backend/sceneflow.db`).** Move it to the shared local default, `data/app.db`. Stop the local backend and run from the repository root:

```bash
backend/.venv/bin/python - <<'PY'
from contextlib import closing
from pathlib import Path
import sqlite3

source_path = Path("backend/sceneflow.db").resolve()
destination = Path("data/app.db")
if not source_path.is_file() or destination.exists():
    raise SystemExit("Source missing or destination already exists; migration stopped")
destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
with closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)) as source:
    with closing(sqlite3.connect(destination)) as target:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise SystemExit("Target integrity check failed; source retained")
destination.chmod(0o600)
for suffix in ("", "-wal", "-shm", "-journal"):
    Path(str(source_path) + suffix).unlink(missing_ok=True)
PY
```

Remove obsolete database settings from `backend/.env`; leave `DATABASE_URL` unset to use the default, or set it to the desired SQLite URL, then restart. This uses SQLite's backup API so committed WAL content is included, checks integrity, and removes the original database and its sidecars. Local media stays at `backend/private_generated/`; if also switching from local development to Docker, transfer that media into the container's media volume as well.

## Local data and troubleshooting

`data/app.db` and `backend/private_generated/` are real gitignored development data. Do not delete/reset them as a routine troubleshooting step. For an isolated scratch server:

```bash
cd backend
scratch_dir=$(mktemp -d)
DATABASE_URL="sqlite:///$scratch_dir/app.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$scratch_dir/media" .venv/bin/python -m uvicorn app.main:app --port 8099
```

- **Requests fail:** verify backend port and frontend rewrite origin, then restart the frontend after env edits.
- **Media fails while APIs work:** inspect `SCENEFLOW_PUBLIC_BASE_URL`; artifact requests can go directly from browser to backend.
- **Queued work never starts:** check `SCENEFLOW_WORKER_ENABLED`, worker logs, and the job's lease/status. A 202 is not completion.
- **Interrupted render:** startup clears abandoned project busy state but does not resume work. Inspect existing media before explicitly retrying; exports have separate state.
- **Port occupied:** inspect its owner or choose a free port; the root launcher forcibly frees its selected port.
- **Python cannot import `app`:** run from `backend/`; direct test/script files need `PYTHONPATH=.`.
- **Shell rejects a route path:** quote brackets/parentheses, e.g. `cat 'frontend/src/app/projects/[projectId]/page.tsx'` from the root.

## Production build

```bash
cd frontend
pnpm build
PORT=4000 pnpm start
```

`next start` defaults to 3000 without `PORT`/`--port`, unlike the dev script. The Docker image uses Next's standalone output instead. Routine source checks use `tsc --noEmit` and lint; see [testing](../conventions/testing.md#tooling-gotchas) for explicit Webpack fallback and `next typegen` after route changes.
