# Current sprint

> **Status of this file.** Derived from repository state on 2026-08-17 (branch `feat/ai-video2.0`). Items below are verified against the code, not planned commitments — **owners and dates need to be filled in by the team.** Keep this file short; move anything not being worked on now to `backlog.md`.

## Theme

**Rebuilding AI 生剧 as a project workbench with anchored storyboard production.** The feature was two screens: a project list, and one 1,500-line editor holding script, shots, cast, settings, and video. It is becoming `project list → six management sections → per-episode editor`, and the render path is moving from "each shot generated independently" to **a tone sheet that locks style, then full-resolution per-shot renders** whose references are the tone sheet, the merged cast sheet, the merged prop sheet, and the previous shot.

Why: the old path had three consistency levers and all three only pinned faces. Nothing held lighting, colour, set dressing, or render style, and `Project.style_prompt` / `negative_prompt` were stored, edited, and serialized without ever reaching a prompt.

## Landed

| Phase | Change |
|---|---|
| 1 | Project synopsis and cover (upload or AI, both optional, placeholder fallback); `ModelRouter.complete_text`; house style wired into `build_image_prompt` |
| 2 | `media_service` contact sheets (uniform pre-scale, 10MB ceiling); `CharacterVariant` → `CharacterState` with turnaround sheets and drafted-then-reviewed prompts; `Prop`; workbench shell with six sections |
| 3 | `VoiceProfile` per project, bound to characters, ffmpeg-merged into one timbre reference; per-shot TTS removed |
| 4 | Episode list CRUD with required titles; per-episode editor (script above, shots below); `storyboard_service` — tone sheet then sequential per-shot renders |
| 5 | Per-shot clips with an optional timbre track; `ExportJob` woken up as multi-select merge and export in the video section |

Earlier, on `feat/episode-layer`: the series/episode data model, path-based artifacts, start guards, and the character CRUD this refactor builds on.

Consequences worth knowing before building on it: shot order restarts per episode, a serialized project carries one episode's shots, the busy lock stays at project level, and references are capped at `MAX_REFERENCE_IMAGES` = 4 — which is why a cast of any size travels as one merged sheet. See `../architecture/data-flow.md`.

## Next

The refactor is complete. What it leaves open:

- **The legacy single-screen editor is still reachable** at `/projects/:id/workbench`, and the episodes section no longer links to it. It is superseded by the episode editor and should be deleted once the new path has been exercised on real projects.
- **Storyboard renders are sequential**, since each shot references its predecessor. Long episodes take proportionally longer; if that becomes the complaint, the fix is a windowed pipeline, not a return to independent shots.
- **`tests/run_all.py` is still not isolated** (below) — the whole suite passes file by file.

## In flight

- [x] **Documentation harness.** `CLAUDE.md` plus this `docs/` tree are now the knowledge base. Everything that used to live in root-level notes and per-directory agent files was folded in and removed: the chat stack to `../design/feature-chat.md`, setup and troubleshooting to `../reference/local-setup.md`, the frontend routing rules to `../architecture/boundaries.md`, and the build/tooling gotchas to `../conventions/testing.md`.

## Ready to pick up

Verified gaps, ordered by how much they cost to leave alone. Owner and sizing to be assigned.

- [ ] **Fix `tests/run_all.py` isolation.** All 28 test files pass individually; the runner fails inside `test_characters_api.py` because it `runpy`s everything in one process and state leaks (reproducible with `test_artifact_service.py` or `test_admin_usage_logs.py` first). It also aborts on the first failure, so later files silently never run. Either run each file in a subprocess or make the runner restore module state and continue on failure. **This is the highest-value item here: the suite currently cannot be trusted as a gate.**
- [ ] **Generation-jobs worker.** `generation_jobs` provides persistence, idempotency, leases, cancel, and retry, but there is no worker process — generation still starts in the API process via `asyncio.create_task`, so a restart mid-run orphans it. See `../architecture/boundaries.md`.
- [ ] **Project job UI.** The endpoints exist (`GET /api/projects/:id/jobs`, cancel, retry); the workbench does not surface them.

## Definition of done

A change is done when: the touched backend test files pass **individually**, `pnpm exec tsc --noEmit` and `pnpm lint` are clean, any endpoint or schema change is reflected in a regenerated `../reference/api-spec.yaml`, and any rule this work establishes or invalidates is updated in `../conventions/`.
