# Testing

Verified on **2026-09-07**. The tree contains **35 backend `test_*.py` files** and **4 frontend `*.test.mts` files**. These are inventory counts, not passing results. There is no pytest or frontend DOM/component test framework.

## Backend: one file per process

Tests are executable modules under `backend/tests/`: plain service assertions and ASGI `TestClient` checks with temporary databases and stubbed providers. Each module calls its checks from `if __name__ == "__main__":`.

```bash
cd backend
check_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_episodes_api test_project_guards
```

For the whole suite, replace the last line with:

```bash
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh $(rg --files tests -g 'test_*.py' | sed 's#^tests/##; s#\.py$##')
```

The runner takes **module basenames without `.py`**; no arguments runs no checks. It gives each file a separate interpreter and overrides `DATABASE_URL` with a temporary database, reports every result, writes `/tmp/<name>.log`, and exits nonzero if any file fails. It does not supply a separate media root, so the command above supplies one before app import. `main.py` creates/chmods that directory at import time. For direct checks, explicitly set `DATABASE_URL` to a temporary SQLite URL so the default or a URL from `.env` cannot select a real database.

`tests/run_all.py` instead `runpy`s files in one interpreter and aborts on the first failure. Module state can leak between files. A failure there is not isolated evidence: rerun the file through `run_tests.sh`. Conversely, do not call the suite green unless every selected file actually ran and passed.

### Adding a check

Follow an existing test for the affected feature, found through the [code map](../architecture/code-map.md).

- Set temporary database **and media** paths before app import/startup; never use the developer's database or real provider keys.
- Patch provider entry points and restore all globals in `finally`. Use `TemporaryDirectory` for test-owned data.
- Name a check after the behavior, and call it from the module's `__main__` block.
- Include response text in status assertions: `assert response.status_code == 200, response.text`.
- Add the smallest meaningful regression for changed logic; no new test framework or implementation-mirroring test boilerplate.

### Queued endpoints

Character-state/prop reference images and prompt drafts, project voice design, and auditions return `202 {job}`. Test their result by draining the real handler:

```python
from tests.job_queue import drain_one, succeeded

queued = client.post(f"/api/projects/{project_id}/props/{prop_id}/image", json={...}, headers=headers)
assert queued.status_code == 202, queued.text
prop = succeeded(drain_one())["prop"]
```

`drain_one`/`drain_jobs` execute claim → dispatch → finish without waiting on polling/heartbeats. Importing `tests.job_queue` sets `SCENEFLOW_WORKER_ENABLED=0` so lifespan does not race the manual drain. Patch the provider where the handler reads it (`app.services.job_handlers`), and keep the stub installed until the drain finishes.

Useful entry points include `test_breakdown_api.py` (replacement and error records), `test_prompt_prefixes.py`, `test_prompt_compiler.py`, `test_storyboard_api.py`, `test_project_guards.py` (selection/cancel cleanup/restart locks), and `test_job_service.py`. Existing test names can also lag behavior; inspect assertions rather than treating names as specification.

## Frontend

```bash
cd frontend
node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts'
pnpm exec tsc --noEmit
pnpm lint
```

The four pure-module suites cover money, artifact URLs, shared reference budgets, and admin user filtering. Tests use `node:test` and `node:assert/strict`, with explicit `.ts` extensions in imports because Node type stripping does no TypeScript path resolution. There is no DOM; extract nontrivial pure logic when a regression needs it, rather than introducing a component framework for one check.

## Schema and contract checks

After changing SQLModel, review the Alembic revision and check a disposable database:

```bash
cd backend
schema_dir=$(mktemp -d)
DATABASE_URL="sqlite:///$schema_dir/check.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$schema_dir/media" .venv/bin/alembic upgrade head
DATABASE_URL="sqlite:///$schema_dir/check.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$schema_dir/media" .venv/bin/alembic check
```

Regenerate OpenAPI using [the existing script and isolated command](README.md#keeping-generated-docs-current). Importing `app.openapi()` does not run lifespan or test handlers; it verifies schema generation, not business behavior.

## Scope of the gate

Code changes: relevant backend self-checks, relevant frontend pure-module checks, frontend `tsc --noEmit` and lint. Add migration/OpenAPI checks when their inputs changed. Broaden testing when failures, shared behavior, or an unresolved concern warrants it.

Every bug-fix handoff also updates its detail under `docs/bugs/` and the [Bug history index](../bugs/README.md), including commands actually run, results, and unexecuted/blocked checks. An existing test or historical report is not evidence of a current pass; do not mark the issue verified without verification.

Documentation-only changes: check local links/anchors, code paths, commands, and generated contract consistency. A documentation refresh does not establish a new passing application-test baseline. Report checks actually executed, with failures or skips, and never claim an interrupted build passed.

## Tooling gotchas

- `pnpm build` has previously hung in Turbopack; use typecheck/lint for the normal loop. If a build is needed, `pnpm exec next build --webpack` is the explicit alternate bundler path.
- `next build` can require network for `next/font`; distinguish a network failure from a source error.
- After moving/deleting routes, regenerate stale route types with `pnpm exec next typegen`, then rerun `tsc`.
- Run Python from `backend/` with `PYTHONPATH=.` for direct `tests/*.py` or `scripts/*.py` execution. The shell runner supplies it for tests.
- Quote Next route paths containing brackets or parentheses in zsh.
- Use pnpm to change frontend dependencies; npm install does not maintain `frontend/pnpm-lock.yaml`.
