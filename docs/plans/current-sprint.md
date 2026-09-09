# Current implementation snapshot

Base snapshot verified on **2026-09-07**; voice-design, media-preview, and export-audio entries updated from the working tree on **2026-09-08**; project asset management updated on **2026-09-09**. The filename is retained for existing links; this is a source snapshot, not a scheduled sprint or an assignment of owners. See the [code map](../architecture/code-map.md) for implementation/test locations and [backlog](backlog.md) for remaining work.

## Available today

| Area | Implemented behavior |
|---|---|
| Series workbench | Project list → seven sections (info, characters, props, voices, assets, episodes, videos) → full-screen episode editor; old workbench remains directly reachable |
| Project settings | Synopsis, cover upload/generation, production settings, project-first text/image/video/audio choices with account fallback |
| Unsaved model settings | Info panel sets an in-memory dirty flag; episode image/video generation can warn and continue with saved configuration |
| Bible | Character states as parallel/ranged looks, prop ownership, labelled setting sheets, merged cast/prop references |
| Voices | Qwen design and project redesign preserving profile IDs/bindings; optional project sample line, save-only/save-and-generate editing, account library/import, local auditions, merged timbre track; [editing flow](../architecture/data-flow.md#project-voice-design-and-editing) |
| Media preview | Shared image/video dialog with open-in-new-tab link; cover, character/state and prop sheets, episode media, asset/reference pickers, and project videos |
| Breakdown | Separate frame/motion targets, four detail levels, selected bible context, shot labels/continuity instructions, confirmation before replacing existing shots |
| Storyboard | Separate tone-sheet action, persisted tone prefixes, sequential frame batches, model-dependent references, selected/pending-only shots |
| Prompt editing | `prompt-area` mentions, asset picker, ordered prefixes, shared reference budgets, preset/optimization and compiled-prompt preview endpoints |
| Asset management | One shared project/episode manager for custom imports plus character/state/prop media, voices, tone sheets, and every live episode’s shot images/videos; search, media/source/episode filters, episode/shot labels, preview/source links, deletion and image merging |
| Video/export | Per-shot motion generation, separate first/last frames, project defaults/audio controls, up to two concurrent video calls; merge up to 60 finished clips in selected order, retaining detected source audio and padding silent clips |
| Standalone generation | Image/video/audio editors reset without deleting history; unsupported FPS is omitted from standalone video requests |
| Queue | In-process three-lane worker for reference images, prompt drafts, project voice design and preview; persisted lease/cancel/retry state |
| Run lifecycle | Project claim guards, attached-task cancellation, unfinished-media cleanup, startup recovery of abandoned project/episode status |
| Chat | AI SDK stream/message owner, assistant-ui composer, custom Streamdown list, context compression, artifact tools, admin-only diagnostic tool |
| Diagnosis | Request IDs, redacted HTTP 5xx records, admin search UI, breakdown JSON compatibility samples |
| Development | Cross-platform venv/install launcher, backend child/signal/port handling, pnpm build allowlist, isolated test runner |

## Boundaries that are still active

- The episode editor uses React Query polling and local drafts. `project-store` and the browser WebSocket live in the legacy editor.
- The queue migration is partial. Tone/storyboard/video/legacy-generation and export tasks still execute in the API process; startup cleanup releases abandoned state but does not resume work.
- Canceling a local task does not guarantee a provider-side stop/refund. Request-scoped calls still lack the queue's database-backed stop semantics.
- Frame slots, legacy default references, save-time budgets, and preview numbering still have inconsistencies; the map does not imply those are fixed.
- A full breakdown replaces shot rows, including their prior references/prefixes. Only the in-place video pass preserves them.

## Next work needs an explicit owner

Candidate work and evidence are maintained in [backlog.md](backlog.md), particularly reference/prefix consistency, durable long-running work, safe logging, job visibility, and test-runner cleanup. There is no source-backed active assignment or delivery date to record here.

## Verification policy

Use the scoped [testing gate and test inventory](../conventions/testing.md), check migrations when schema changes, and regenerate OpenAPI when routes or contracts change. This documentation refresh does **not** assert that the application suite passes. Record actual commands/results in the change handoff, not as an undated evergreen claim. Every bug fix also updates its detail and the [Bug history index](../bugs/README.md) before handoff.
