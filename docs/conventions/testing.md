# Testing

There is no pytest and no frontend test framework. Both setups are deliberately dependency-free.

## Backend

Tests are plain modules under `backend/tests/`. Each defines test functions and calls them from `if __name__ == "__main__":`. They drive the **real ASGI app** through `fastapi.testclient.TestClient` with providers monkeypatched out, against a temporary SQLite file.

```bash
cd backend
PYTHONPATH=. .venv/bin/python tests/test_episodes_api.py    # one file — the reliable way
sh scripts/run_tests.sh test_episodes_api test_characters_api   # several, each isolated
sh scripts/run_tests.sh $(ls tests/test_*.py | xargs -n1 basename | sed 's/\.py$//')   # everything
```

### Use `scripts/run_tests.sh`, not `run_all.py`

`scripts/run_tests.sh` gives each file its own interpreter and its own throwaway database,
reports every result, and exits non-zero listing the failures. That is what the pre-commit
gate needs.

`tests/run_all.py` `runpy`s every file in one process instead. Two consequences:

1. **Module-level state leaks between files.** All test files pass individually and through
   `run_tests.sh`; `run_all.py` has failed inside `test_characters_api.py`, reproducibly, when
   `test_artifact_service.py` or `test_admin_usage_logs.py` ran first in the same process.
2. **The first failure aborts the run** — there is no error handling, so every later file is
   skipped and reports nothing.

**Treat a `run_all.py` failure as unproven until you rerun that file on its own.**

### Writing a backend test

Follow `tests/test_episodes_api.py`:

- A `@contextmanager _app(directory)` that saves the originals, points `database.DB_PATH` and `artifact_service.PRIVATE_GENERATED_DIR` at a `tempfile.TemporaryDirectory()`, patches the provider entry points (`models.parse_script`, `projects.run_generation`), calls `init_db()`, seeds a user and configs, and **restores every original in a `finally`**. Restoration is not optional — that is what `run_all.py` currently trips over.
- Name test functions as sentences: `test_deleting_an_episode_takes_its_shots_with_it`. The name is the failure message.
- Add the function to the `__main__` block at the bottom, or it never runs.
- Assert on the response body with the text in the message: `assert response.status_code == 200, response.text`.
- Never let a test reach a real provider or the developer database. Point `SCENEFLOW_DB_PATH` at a temp path; never touch `backend/sceneflow.db`.

### Testing a queued endpoint

Reference images, prompt drafts, voice design, and voice auditions return `202 {job}` and do the work in the job worker (see `../architecture/data-flow.md` §2c). A test that wants to assert on the *result* has to run the job itself:

```python
from tests.job_queue import drain_one, succeeded

queued = client.post(f"/api/projects/{project_id}/props/{prop_id}/image", json={...}, headers=headers)
assert queued.status_code == 202, queued.text
prop = succeeded(drain_one())["prop"]
```

`drain_jobs`/`drain_one` run the real path — `claim_next_job` → `dispatch` → `finish_job` — just without lease renewal and the poll interval, so the real handler and the real terminal write are still exercised.

Two rules that follow from this:

- **Patch the provider on `app.services.job_handlers`, not on the endpoint module.** The call moved when the endpoint became an enqueue; patching `app.api.v1.voices.synthesize` now patches a name nothing reads.
- **Keep the stub installed until after the drain.** The provider call happens while the job drains, not during the POST, so a `finally: restore` around only the POST restores it too early.

Importing `tests.job_queue` sets `SCENEFLOW_WORKER_ENABLED=0`, which keeps the in-process worker the app lifespan would otherwise start from racing the test for the same rows. Two claimants make which one runs a job a coin flip.

### What is covered today

Auth and admin (users, usage logs, invitation/redemption codes), model config resolution and the legacy table merge, project guards and production settings, the episode layer and its migration, characters and casting, artifacts and signed paths, jobs (lease/cancel/retry), local voice audition, video, usage/billing, websocket, and the database migrations themselves.

## Frontend

Tests are `*.test.mts` beside the code under test, run by Node's built-in runner with type stripping:

```bash
cd frontend
node --no-warnings --experimental-strip-types --test src/lib/money.test.mts
node --no-warnings --experimental-strip-types --test 'src/app/(workspace)/admin/users/_components/user-list.test.mts'
```

- Imports inside a `.test.mts` must use the **`.ts` extension** (`from "./money.ts"`) — type stripping does no resolution. The `@ts-expect-error` above such an import is expected.
- Use `node:test` + `node:assert/strict`, no framework.
- This only works for **pure modules**. There is no DOM or component-rendering setup, so extract logic worth testing into a plain `.ts` module — `user-list.ts` exists precisely so the filtering rules could be tested apart from the component.

## The standard gate

Before handing work over:

```bash
cd backend && PYTHONPATH=. .venv/bin/python tests/<the files you touched>.py
cd frontend && pnpm exec tsc --noEmit && pnpm lint
```

`pnpm build` is slow and has hung in this project before; `tsc --noEmit` is the type gate. If you do run a build, do not report it as passing unless it finished.

### Build and tooling gotchas

Each of these has cost time in this repo already:

- **Turbopack production builds have hung** at `Creating an optimized production build ...` with no output for minutes. `pnpm build -- --webpack` (the webpack path) has completed when Turbopack did not. An interrupted build is **not** a pass.
- **`next build` needs network** for `next/font` — a sandboxed run fails with `getaddrinfo ENOTFOUND fonts.googleapis.com`. Nothing is wrong with the code.
- **`.next/types` goes stale after deleting or moving a route.** `tsc` will report errors about files that no longer exist; run a successful build once to regenerate route types, then re-run `tsc`.
- **Run backend Python from `backend/`.** From the repo root you get `ModuleNotFoundError: No module named 'app'`. `PYTHONPATH=. .venv/bin/python tests/x.py` and `.venv/bin/python -m tests.x` both work from there.
- **Quote bracketed route paths in zsh** — `src/app/projects/[projectId]/page.tsx` is a glob and fails with `no matches found`.
- **`npm install` does nothing useful here.** This is a pnpm project; use `pnpm add` or the lockfile silently diverges.

## Reporting

State what you ran and what happened. A skipped check is reported as skipped, not implied by silence — an interrupted build that is reported as green is worse than no build at all.
