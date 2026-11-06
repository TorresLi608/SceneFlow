# Current implementation snapshot

Base snapshot verified on **2026-09-07**; voice-design, media-preview, and export-audio entries updated from the working tree on **2026-09-08**; project asset management updated on **2026-09-09**; the model-provider row updated from the working tree on **2026-10-12**. Workspace Activity and concurrent-chat entries updated from the working tree on **2026-11-03**, with frontend checks and isolated browser simulations recorded in the [workspace issue](../bugs/2026-11-03-workspace-page-state-reset.md) and [chat issue](../bugs/2026-11-03-chat-session-switch-blocked.md); real provider calls were not tested. Subsequent assistant-ui compatibility fixes were checked in the running Next.js 16.2.3/Turbopack app with repeated menu switches and an unsent draft; see [resource lifecycle](../bugs/2026-11-03-assistant-ui-activity-lifecycle.md) and [runtime snapshots](../bugs/2026-11-03-assistant-ui-runtime-snapshot.md). The filename is retained for existing links; this is a source snapshot, not a scheduled sprint or an assignment of owners. See the [code map](../architecture/code-map.md) for implementation/test locations and [backlog](backlog.md) for remaining work.

## Available today

| Area | Implemented behavior |
|---|---|
| Series workbench | Project list → seven sections (info, characters, props, voices, assets, episodes, videos) → full-screen episode editor; old workbench remains directly reachable |
| Project settings | Synopsis, cover upload/generation, production settings, project-first text/image/video/audio choices with account fallback |
| Model providers | Text: Qwen, Doubao, DeepSeek, OpenAI, Gemini, Claude, Grok, custom relay; image: OpenAI, Gemini, Qwen/Wan, Grok; video: Doubao, Gemini, Qwen/Wan, Grok; audio: Qwen voice design. Grok resolves the official `api.x.ai` host natively (xAI image fields, JSON image edits, asynchronous video tasks) and treats any other base URL as an OpenAI-compatible relay such as new-api; provider contracts are listed in the [backend reference](../../backend/README.md#providers-and-model-configuration) |
| Unsaved model settings | Info panel sets an in-memory dirty flag; episode image/video generation can warn and continue with saved configuration |
| Bible | Character states as parallel/ranged looks, prop ownership, labelled setting sheets, merged cast/prop references |
| Voices | Qwen design and project redesign preserving profile IDs/bindings; optional project sample line, save-only/save-and-generate editing, local auditions, merged timbre track; project voices are isolated from the standalone voice library (no shared writes, no import); [editing flow](../architecture/data-flow.md#project-voice-design-and-editing) |
| Media preview | Shared image/video dialog with open-in-new-tab link; cover, character/state and prop sheets, episode media, asset/reference pickers, and project videos |
| Breakdown | Separate frame/motion targets, four detail levels, selected bible context, shot labels/continuity instructions, confirmation before replacing existing shots |
| Storyboard | Separate tone-sheet action, persisted tone prefixes, sequential frame batches, model-dependent references, selected/pending-only shots |
| Prompt editing | `prompt-area` mentions, asset picker, ordered prefixes, shared reference budgets, preset/optimization and compiled-prompt preview endpoints |
| Asset management | One shared project/episode manager for custom imports plus character/state/prop media, voices, tone sheets, and every live episode’s shot images/videos; search, media/source/episode filters, episode/shot labels, preview/source links, deletion and image merging |
| Video/export | Per-shot generation → episode composition in selected shot order → final export in selected episode order; up to 60 inputs per merge, shared audio retention/silent padding, previous episode video retained on failed recomposition |
| Standalone generation | Image/video/audio editors reset without deleting history; the image/video history panels, the chat session list, and the saved-voice list each show their menu's admin retention window as a cleanup notice when one is set; image/video history items and their fullscreen sidebars show the provider and model that produced them, and saved voices show their target model; unsupported FPS is omitted from standalone video requests; the chat/image/audio/video request controllers stay mounted across workspace menu switches while their views use React Activity; hidden UI effects disconnect, dialogs close, and media pauses, while in-flight results remain available on return; leaving the workspace layout resets local editor state |
| GPT Image 2.6 / GIF (2026-11-06) | OpenAI Sunburst/Flare work through the existing Images API. The standalone image panel offers PNG/GIF, frame count and duration, automatic GIF frame dimensions on OpenAI / 1024×1024 on relays, original animated preview/download and history restoration; reference cards show only uploaded images. Project/chat image generation retains PNG defaults. See [image contract](../../backend/README.md#images--appapiv1imagespy). |
| Queue | In-process three-lane worker for reference images, prompt drafts, project voice design and preview; persisted lease/cancel/retry state |
| Run lifecycle | Project claim guards, attached-task cancellation, unfinished-media cleanup, startup recovery of abandoned project/episode status |
| Chat | AI SDK stream/message owner with one `Chat` instance per session (switch sessions, create a new one, or leave the menu while an answer streams; running sessions show a live marker and cannot be deleted until done), assistant-ui composer, custom Streamdown list, context compression, artifact tools, admin-only diagnostic tool |
| Diagnosis | Request IDs, redacted HTTP 5xx records, admin search UI, breakdown JSON compatibility samples |
| Development | Cross-platform venv/install launcher, backend child/signal/port handling, pnpm build allowlist, isolated test runner |

### GPT Image 2.6 validation — 2026-11-06

Subsequent user feedback exposed New API rejecting `size=auto`; the mock originally accepted it. The adapter now substitutes explicit dimensions on relays. Fresh reproduction and validation for that correction are recorded separately in the [relay size issue](../bugs/2026-11-06-image-relay-auto-size.md); the original feature checks below remain historical evidence.

- In `backend`, with temporary media and the runner's per-file temporary databases: `sh scripts/run_tests.sh test_images test_generation_records test_artifact_service test_config_service`, followed by `sh scripts/run_tests.sh test_storyboard_api test_project_cover test_media_service test_generation_retention`: 8/8 passed. Actual OpenAI SDK requests were inspected through `httpx.MockTransport` for both 2.6 models, official/relay-shaped URLs, JSON generation and multipart reference edits; no network provider call was made. A real two-frame GIF retained its bytes, loop and duration through persistence and signed serving; thumbnail and original deletion passed.
- In `frontend`: `pnpm exec tsc --noEmit`, `pnpm lint`, and `node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts' 'src/app/(workspace)/chat/_components/chat-message-state.test.mts'` passed (25 tests).
- Playwright used a temporary fixture at `/private/tmp/sceneflow-gif-ui-check/`, bundling the actual image panel, React Compiler, Next Image, React Query and application styles, with simulated generation/history responses. Verified zero default cards, two uploads → one after removal → zero after clearing; GIF defaults and invalid-value blocking; text/reference GIF request fields; original GIF preview/fullscreen/format badge; reset/history option restoration; switching to a legacy model omits animation fields; desktop Chinese and 390px English layouts. Browser-downloaded `.gif` bytes matched the fixture exactly, including both frames, timing and loop. Screenshots and the downloaded fixture are in that temporary folder. The local server and browser required sandbox escalation; the first sandboxed server bind and CLI registry lookup failed, then the permitted retries succeeded.
- OpenAPI regenerated with temporary database/media paths and workers disabled. No schema migration, production data change, paid model request, real relay capability test, or real generated-content quality test was performed.

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
