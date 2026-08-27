# Current sprint

> **Status of this file.** Derived from repository state on 2026-08-24 (branch `feat/script`). Items below are verified against the code, not planned commitments — **owners and dates need to be filled in by the team.** Keep this file short; move anything not being worked on now to `backlog.md`.

## Theme

**Making the workbench's six sections controllable.** The previous refactor built the shape — project list → six management sections → per-episode editor — and this one makes each section do the job it was standing in for. Three threads run through all of it:

1. **The user says what they want, not what the model should infer.** A cover is drawn from a cover prompt rather than from the synopsis; a breakdown works against the bible entries the user ticked rather than guessing; a voice is described rather than named by model string.
2. **Every long call can be stopped**, and stopping is not a failure. Prompt optimisation, cover generation, prompt drafting, reference drawing, voice design, storyboard renders, and clip renders all carry an abort path.
3. **A shot carries enough to become a clip.** The old split produced a narration line and a picture prompt; a clip needs a camera move, a transition, a length, and a motion prompt, and now gets all four.

## Landed

| Phase | Change |
|---|---|
| 1 | Project synopsis and cover (upload or AI, both optional, placeholder fallback); `ModelRouter.complete_text`; house style wired into `build_image_prompt` |
| 2 | `media_service` contact sheets (uniform pre-scale, 10MB ceiling); `CharacterVariant` → `CharacterState` with turnaround sheets and drafted-then-reviewed prompts; `Prop`; workbench shell with six sections |
| 3 | `VoiceProfile` per project, bound to characters, ffmpeg-merged into one timbre reference; per-shot TTS removed |
| 4 | Episode list CRUD with required titles; per-episode editor (script above, shots below); `storyboard_service` — tone sheet then sequential per-shot renders |
| 5 | Per-shot clips with an optional timbre track; `ExportJob` woken up as multi-select merge and export in the video section |
| 6 | **Project-level model configuration** (`project_model_config`, project-first with account fallback) and the generation defaults every render in a series starts from |
| 7 | **`breakdown_script`** — camera move, transition, duration, motion prompt, speaker; `target` splits the shot pass from the video pass so re-deriving motion cannot discard rendered frames; reference selection drives what the model defers to |
| 8 | **Tone sheet as its own step**, then batch or single frame renders, then batch or single clips, each gated on the previous stage |
| 9 | **Cooperative cancellation** (`app/core/runs.py`), checked between shots so paid-for work is kept |
| 10 | Voice management rebuilt on the `/audio` design flow, plus import from the account's voice library; `qwen_voice_service` made async so a client abort reaches the provider |
| 11 | Shared `PromptField` — preset templates, zh/en output language, optimise, stop — across cover, character, prop, and voice |

Earlier, on `feat/episode-layer`: the series/episode data model, path-based artifacts, start guards, and the character CRUD this refactor builds on.

Consequences worth knowing before building on it: shot order restarts per episode, a serialized project carries one episode's shots, the busy lock stays at project level, and references are capped at `MAX_REFERENCE_IMAGES` = 4 — which is why a cast of any size travels as one merged sheet. See `../architecture/data-flow.md`.

## Fixed

- **The episode editor never stopped rendering.** Two independent causes, both in `../architecture/data-flow.md` now:
  - the busy flag was read from `queryKeys.projects` (5-minute `staleTime`, no interval) while the poll wrote to `[...projects, "poll"]` — a different cache entry — so the status never refreshed and the 3-second poll ran for the rest of the session;
  - `_sign` stamped `iat` from the clock, so every response minted a different URL for the same file; combined with rows keyed on the image URL that remounted every shot and re-downloaded every frame each tick.
- **Character and prop "system prompt" removed from the UI.** The built-in template *is* the system prompt; an editable copy of it beside `final_prompt` gave users two prompt fields where one was meant. Columns kept, marked legacy, read by nothing.
- **The baseline revision no longer breaks on new `Scene` columns.** `_migrate_scene_assets` and `_backfill_first_episode` read legacy tables with core SQL naming only the columns they touch — the hazard the latter already documented for `projects` but not for `scenes`.
- `tests/run_all.py` is still not isolated, but `backend/scripts/run_tests.sh` runs each file in its own process against a throwaway database, which is what the gate below actually needs.

## Ready to pick up

Verified gaps, ordered by how much they cost to leave alone. Owner and sizing to be assigned.

- [ ] **Fix `tests/run_all.py` isolation.** All 32 test files pass individually (and through `scripts/run_tests.sh`); the runner still `runpy`s everything in one process and aborts on the first failure. Either make it shell out per file the way that script does, or make it restore module state and continue.
- [ ] **Move the remaining generation onto the jobs worker.** The worker exists now (`app/services/job_worker.py`) and drains reference images, prompt drafts, voice design, and auditions. Storyboard, tone sheet, project generation, and export still start in the API process via `asyncio.create_task`, so a restart mid-run still orphans them and `app/core/runs.py` cancellation is still in-process. These are the harder half: a run spans many shots, holds the project busy lock, and broadcasts per shot. See `../architecture/boundaries.md`.
- [ ] **The legacy single-screen editor is still reachable** at `/projects/:id/workbench`, and nothing links to it. It is the only remaining caller of `POST /api/projects/:id/parse` and of the WebSocket client code; deleting it would let both go.
- [ ] **Project job UI.** The endpoints exist (`GET /api/projects/:id/jobs`, cancel, retry); the workbench does not surface them.

## Definition of done

A change is done when: the touched backend test files pass **individually** (`sh scripts/run_tests.sh <name>…`), `pnpm exec tsc --noEmit` and `pnpm lint` are clean, `alembic check` reports no pending operations, any endpoint or schema change is reflected in a regenerated `../reference/api-spec.yaml`, and any rule this work establishes or invalidates is updated in `../conventions/`.
