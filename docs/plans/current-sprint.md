# Current sprint

> **Status of this file.** Derived from repository state on 2026-08-12 (branch `feat/episode-layer`, 6 commits ahead of `main`, working tree otherwise clean). Items below are verified against the code, not planned commitments — **owners and dates need to be filled in by the team.** Keep this file short; move anything not being worked on now to `backlog.md`.

## Theme

**The episode layer and the series bible.** A project stopped being a flat list of shots and became a series: content hangs off `Episode`, and `Character`/`CharacterVariant` keep a cast member's look, image model, and voice stable across episodes.

## Landed on this branch

| Change | Commit |
|---|---|
| Series/episode data model, path-based artifacts, start guards | `aeda4cc` |
| Episode layer wired through API, store, and workbench | `4fc2c7d` |
| Series bible drives rendering (appearance prompts + reference portraits) | `58a12ce` |
| Character CRUD, scene casting, extended generation timeouts | `fca956d` |

Consequences worth knowing before building on it: shot order restarts per episode, a serialized project carries one episode's shots, the busy lock stays at project level, and reference portraits are passed image-to-image (capped at `MAX_REFERENCE_IMAGES` = 4). See `../architecture/data-flow.md`.

## In flight

- [x] **Documentation harness.** `CLAUDE.md` plus this `docs/` tree are now the knowledge base. Everything that used to live in root-level notes and per-directory agent files was folded in and removed: the chat stack to `../design/feature-chat.md`, setup and troubleshooting to `../reference/local-setup.md`, the frontend routing rules to `../architecture/boundaries.md`, and the build/tooling gotchas to `../conventions/testing.md`.

## Ready to pick up

Verified gaps, ordered by how much they cost to leave alone. Owner and sizing to be assigned.

- [ ] **Fix `tests/run_all.py` isolation.** All 22 test files pass individually; the runner fails inside `test_characters_api.py` because it `runpy`s everything in one process and state leaks (reproducible with `test_artifact_service.py` or `test_admin_usage_logs.py` first). It also aborts on the first failure, so later files silently never run. Either run each file in a subprocess or make the runner restore module state and continue on failure. **This is the highest-value item here: the suite currently cannot be trusted as a gate.**
- [ ] **`backend/README.md` says image generation is OpenAI-only.** `app/llms/router.py` has `IMAGE_PROVIDERS = {"openai", "gemini"}` with a native Gemini path. One-line doc fix.
- [ ] **Generation-jobs worker.** `generation_jobs` provides persistence, idempotency, leases, cancel, and retry, but there is no worker process — generation still starts in the API process via `asyncio.create_task`, so a restart mid-run orphans it. See `../architecture/boundaries.md`.
- [ ] **Project job UI.** The endpoints exist (`GET /api/projects/:id/jobs`, cancel, retry); the workbench does not surface them.

## Definition of done

A change is done when: the touched backend test files pass **individually**, `pnpm exec tsc --noEmit` and `pnpm lint` are clean, any endpoint or schema change is reflected in a regenerated `../reference/api-spec.yaml`, and any rule this work establishes or invalidates is updated in `../conventions/`.
