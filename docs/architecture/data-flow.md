# Data flow

Verified on **2026-09-07**, with project voice design/editing and export audio rechecked on **2026-09-08**. The primary production path is **series settings/bible → episode script → shots → tone sheet → frames → clips → export**. Use the [code map](code-map.md) for files and [boundaries](boundaries.md) for ownership rules.

## 1. Model resolution and settings

```text
project.{text,image,video,audio}_config_id
  → config_service.project_model_config
  → usable project pick, otherwise active_model_config for the account
  → user official default / active personal config / system official fallback
```

`GET /api/projects/:id/models` returns the resolved models and capability summaries, never provider keys. `PATCH /api/projects/:id` writes `modelSettings`; **`0` clears a config pick**, while `null` leaves it alone. Image resolution/ratio and video quality/ratio/duration/prompt extension/audio defaults live on the project. Legacy `video_fps` remains in storage/API but has no current model-panel control.

The project info page edits a local model-settings draft and marks `unsaved-settings-store`. The episode page checks that flag before image/video generation and lets the user return to settings or continue with the saved backend configuration. The flag is not a persistent draft, and the unused `use-unsaved-settings-check.ts` hook is not part of this flow.

## 2. Series bible and media identity

`Project` is a series. `Episode` owns its script and ordered `Scene` rows; `Scene.project_id` also records series ownership. Order starts at 1 in each episode. An omitted episode ID resolves to the highest-numbered live episode; project serialization includes only that episode's shots plus summaries of the others.

- `Character` + `CharacterState` hold a cast member's appearance, image model, and voice binding. States are parallel looks unless `from_episode` pins one to a series point; `resolve_character` chooses the applicable state and overrides only fields it sets. `SceneCharacter` records the on-screen cast; the speaker can be off screen.
- `Prop` holds object settings and an optional character owner. `VoiceProfile` holds a project timbre and audition; `UserVoice` is the reusable account library. Project voice design saves a library entry; import copies its audition so a later library deletion does not remove the project's sample.
- State/prop images are **setting sheets** with labels. A drafted character sheet is one image in three zones: the turnaround, an expression set (at least four contrasting facial close-ups), and a profile card (name, age, role, key visual traits); a prop sheet is multi-angle (front, side, back, detail) with name, owner, description, and setting notes. `prompt_service.shot_prompt` forbids text in finished frames so reference captions do not leak into the episode. Built-in instruction templates are not user-overridable and there is no per-kind preset picker for character/prop drafts any more (`GET /api/prompts/presets` serves cover presets only; `DraftPromptRequest` has no `preset` field); the old `system_prompt` columns remain legacy storage.
- `media_service.merge_images` scales inputs to one width before tiling and compresses under 10 MB. Merged cast/prop sheets reduce reference count; the actual limit comes from the selected model, not a universal four-image rule.
- Voices are auditioned and FFmpeg-concatenated into `projects.voice_sheet_path`, a timbre reference. No current production stage synthesizes one TTS file per shot. Local Edge/system TTS remains for project auditions.

Project model IDs, character voice-profile bindings, and prop owner IDs include plain columns rather than FK-enforced links. Preserve the fallback/manual cleanup their services implement.

### Project voice design and editing

The project voices page uses `projects-actions.designVoiceProfileAction` → `POST /api/projects/:id/voices/design` → `voice_design` job → `job_handlers.design_voice`. Without a nonempty `voiceId`, success creates a project profile; with one, the API checks project ownership and the handler updates that existing profile. Its ID and order remain unchanged, preserving character bindings. Every successful design also creates a new saved `UserVoice` entry, including a redesign.

The create form uses one sample line for both the audition and merged-track reference. The API still accepts separate `previewText` and `sampleText`, with defaults when omitted; `note` defaults to the design description. Field limits and fallback order are in the [voice endpoint contract](../../backend/README.md#voices--appapiv1voicespy).

| Edit action | Execution |
|---|---|
| Save | PATCH the profile's name, note, and sample text; keep the existing audio |
| Save and generate, Edge/system profile | PATCH first, then queue `/voices/:voiceId/preview` with local TTS |
| Save and generate, other profile | Use the edited note as `voicePrompt` and pass `voiceId` to `/voices/design`, resolving the project's current audio configuration |

Closing the editing dialog aborts the awaited generation job through `job-actions`; a completed PATCH is not rolled back. Redesigning a profile does not rebuild `projects.voice_sheet_path`: merge again to use the new audio in that reference track. The ordinary preview endpoint still uses local TTS; it does not recreate a Qwen timbre. Provider task/target-model selection is documented in [backend provider notes](../../backend/README.md#providers-and-model-configuration).

## 3. Script → shots

```text
episode page / breakdown-panel
  → projects-actions.breakdownEpisodeAction
  → POST /api/projects/:id/episodes/:episodeId/breakdown
  → breakdown_service builds selected bible context
  → llms/router.ModelRouter.breakdown_script parses the LLM response
  → episodes._replace_shots OR episodes._apply_video_shots
```

Body: `{target, detailLevel?, detailPrompt?, script?, references, replaceAll?, model?}`. `detailLevel` is `concise`, `standard`, `detailed`, or `custom`; custom requires `detailPrompt`.

| Target | Writes | Lifetime |
|---|---|---|
| `shots` | Narration, dialogue, speaker, frame prompt, shot size | Replaces the episode's shot rows |
| `video` | Camera move, transition, duration, motion prompt | Updates existing rows in place; existing images/references/prefixes survive |
| `both` | Both halves | Replaces the episode's shot rows |

Re-splitting **any existing shots** with `shots`/`both` first returns `applied: false`, `discardsScenes`, `discardsGeneratedScenes`, and the existing scenes. The user confirms before a second request sets `replaceAll: true`. A full replacement creates new rows and discards their old references/prefixes too; separate prompt columns only protect prefixes during in-place updates. `video` requires existing shots and never triggers this replacement flow.

Selected characters with drawn sheets are named as references; selected text-only settings are reasoned about from their descriptions; unknown characters are inferred from the script. An empty selection is valid. Speaker names/aliases resolve best-effort. Both prompts are normalized to `分镜X：` using `with_shot_label`, and the breakdown instructions request explicit continuity from the previous shot.

The endpoint claims the project's `parsing` status, performs the request-scoped model call, meters it, and releases the claim in `finally`. Its frontend AbortController stops waiting; this endpoint is not registered in `runs.py` and is not a queued job.

Legacy `/api/projects/:id/parse` serves `workbench-editor.tsx` with the older narration/frame schema and a different `pendingScenes` confirmation response. Do not substitute one schema for the other.

## 4. References, prefix prompts, and asset library

```text
shot-row / prompt-prefix-list / mention-textarea (prompt-area)
  → save {kind, id} selections and ordered prefix items
  → prompt_prefix_service.combined_references (prefix-first, deduplicated)
  → reference_service.resolve_generation_references (project ownership + media paths)
  → prompt_compiler.compile_prompt
  → provider-specific text + image/video/audio payloads
```

Reference kinds are `character`, `characterState`, `prop`, `tone`, `sceneImage`, `sceneVideo`, `voice`, and `asset`. The frontend sends identities, not trusted file paths. `assets.py` owns project imports, metadata, deletion, and image merging; `Asset.path` may be a local stored path or an explicitly imported HTTP(S) URL.

The project `/assets` page and episode “资产管理” dialog share `project-asset-manager.tsx`. `GET /api/projects/:id/assets/catalog` reads live project imports, character/state/prop images, voices, and every live episode's tone/shot images and shot videos. It returns stable `{kind, id}` identities plus `episodeId`, `episodeNumber`, `episodeTitle`, `sceneOrder`, bilingual labels/aliases, media type, description and signed URL; no duplicate Asset rows or migration is needed. Generated assets can be previewed, used as references, merged (images), or removed with the existing generated-reference endpoint; custom imports retain rename/update/delete. Removal affects the series, with explicit confirmation in both surfaces.

The manager and reference pickers search names, descriptions, episode titles and label aliases locally; management also filters media, source kind and episode/shared scope. Cards initially render 36 results with “load more”. Metadata is still fetched in full; this is not server pagination. Generated shot labels include episode, shot order and image/video kind. The resolver/compiler accept both these labels and old `@分镜 N` / episode-title labels; ambiguous old duplicate labels cannot reconstruct intent and retain first-reference precedence. Current-shot video self-reference remains excluded. First-frame defaults remain off.

Each prompt has up to eight `{id, name, prompt, references, source}` prefixes stored separately in `image_prompt_prefixes_json` / `video_prompt_prefixes_json`. They share the same per-media budget as that prompt's references. One asset mentioned in multiple prefix/body editors occupies one slot; `frontend/src/lib/reference-budget.ts` calculates the remaining budget.

`POST /api/prompts/compile` accepts raw prefixes and body text, combines them server-side, and rewrites `@labels` into `图N` / `视频N` / `音频N`; Doubao uses `<图片N> label` / `<视频N> label` / `<音频N> label`. Dialogue is appended with a resolved speaker when available. `prompt_service.py` owns built-in setting/shot/tone instructions; `prompts.py` also serves presets and request-scoped optimization.

The intended contract is that preview numbering follows the media actually sent. Legacy video default-image counting and frame filtering are still split across preview, validation, and rendering; do not assume all paths are aligned. Asset/reference deletion currently cleans direct shot lists but not every prefix/frame reference. These are tracked in the [backlog](../plans/backlog.md).

## 5. Shots → tone sheet → storyboard frames

```text
POST .../episodes/:episodeId/tone-sheet  → run_tone_sheet
POST .../episodes/:episodeId/storyboard → run_storyboard
  → claim_project_status → runs.register + attach_task → 202
  → anchor (reuse unless regenerate, or generate if absent)
  → sequential _generate_shot calls using saved per-shot references/prefixes
  → store_artifact → scene/episode/project state + broadcasts
  → episode editor observes query polling
```

- The anchor is a thumbnail grid establishing the episode's look; each cell is asked to carry its number plus a caption of at most ten characters summarising the shot (`1 黄昏街道 | 青年走路`). It has its own endpoint so users can inspect it before paying for full frames. A storyboard run still ensures one exists, and an anchor failure aborts that run.
- The explicit tone action sends `toneReferences`; selected images are merged into one context sheet. Legacy tone context may use cast/prop sheets and a previous episode's tone sheet.
- Frame generation from the current editor omits request-wide `references`; `episodes.py` loads each shot's saved prefixes and reference identities. The current `run_storyboard` loop sends **only that per-shot list**. It does not secretly append the tone image or predecessor image, despite older comments describing that behavior. The loop remains sequential.
- A reference-free shot uses `generate_image`; a shot with image references uses `edit_image`. The selected model's `imageMaxReferenceImages` caps references.
- `sceneIds` chooses a subset. Without it, locked shots are skipped; an explicit locked selection is rejected. `pendingOnly: true` excludes successful frames, so retrying a partial batch need not buy them again. Empty eligible selections are `400`.
- A successful newly generated tone sheet writes/replaces a `source: "tone"` prefix in **every** shot's image and video prefix lists, using the shot's grid cell and stable prefix ID. The two lists get different wording from `prompt_prefix_service.tone_prefix_prompt(media=…)`: the still text points the shot at its own cell and the cells beside it; the video text demotes the sheet to a light/palette/render reference, names the cell for its mood only, and states that the grid is not a shot list, not the first frame, and must not be played through or cut into per-cell segments — one continuous take. The write is best-effort; `GET /api/prompts/prefix-presets?kind=image|video` reproduces the same per-list text once an anchor exists (`kind` defaults to `image`). The same endpoint serves three hand-inserted presets that need no anchor, each stamped with its `source`: `script` (the episode's `source_text`), `shot` (this shot's narration line), and `shots` (every shot's frame or motion prompt in order, tagged with shot type and, for motion, camera move; bound to the tone sheet by `@label` when one exists; closed with a one-shot-only instruction). Preset text is cut to the prefix `prompt` limit with a truncation note, the all-shots list shot by shot. Refresh the shot data after this step: the running plan was assembled before the new prefixes were written.
- Normal completion records `done`, `partial`, or `failed` from the saved outcomes. Cancellation has its own cleanup below. Standalone tone-sheet waiting is capped at five minutes.

Request-wide storyboard references and automatically written prefixes still have plan-snapshot limitations; see the backlog rather than relying on an obsolete automatic-anchor description.

## 6. Shots → video clips

```text
projects-actions.generateVideoAction
  → POST /api/projects/:id/generate-video {episodeId?, sceneIds?, pendingOnly?, references?, ...}
  → project model/defaults + selected_scenes + _scene_payloads
  → generation_service.run_video_generation (at most 2 concurrent shots)
  → video_service.generate_video (provider-specific request/poll/download)
  → store clip path → scene/episode/project status
```

The **project batch endpoint requires a storyboard image for every selected shot**, including when its model also supports text-to-video. Standalone `/api/videos/generate` follows model capabilities directly and is a different path.

The standalone video form must omit FPS when `videoCapabilities.fps` is empty, rather than inventing a default of 24. An explicitly submitted unsupported value still fails backend validation. See the [FPS fix record](../bugs/2026-09-07-video-unsupported-fps.md).

Standalone image/video/audio panels offer Reset: a new editor key restores initial local state and native inputs, while image/video localStorage history and backend saved voices remain intact. Audio starts with no selected saved voice. See the [reset record](../bugs/2026-09-07-generation-editor-reset.md) for behavior and verification limits.

First/last frame choices resolve from saved `video_first_frame_json` / `video_last_frame_json`. The renderer passes them separately as `first_frame` / `last_frame`, removes matching media from additional images, and uses `adaptive` ratio when available. The editor leaves an unselected first frame empty, including after storyboard generation; only a saved or manual choice fills it. Saving `""` explicitly turns a slot off. Existing saved choices are retained. Untouched legacy rows can still use `defaultVideoReferencePaths`, including the shot's own image, as additional references. See the [first-frame default fix](../bugs/2026-09-09-video-first-frame-default.md).

Motion text is preferred over frame text, then narration/dialogue. Prefix text precedes it; camera move, transition, dialogue/speaker, and previous-shot continuity instructions are appended before the provider call. Duration comes from `duration_ms` (clamped to capabilities), falling back to the project's default when undecided.

Saved defaults unsupported by a changed model are omitted; explicit unsupported request options are rejected. An omitted `withAudio` follows `project.video_audio_enabled` and may be downgraded when unsupported. An explicit unsupported `true` is `400`. Native output-audio models use their switch; `reference_voice` models require the project's merged voice sheet when requested. Frames and additional references have known legacy budget/preview differences; use the current capability validators and consult the backlog.

## 7. Clips → export

Each episode card and the episode editor expose **Compose episode video**. `POST /api/projects/:id/episodes/:episodeId/video {sceneIds}` accepts 1–60 unique, successfully generated shots from that episode in **click-selection order**. It creates an `ExportJob` with `target_episode_id` and ordered `source_scene_ids`. Only a successful merge publishes the unique output path to `Episode.video_path`, in the same transaction as the completed job; a failed recomposition leaves the previous episode video usable. A pending composition for the same episode returns 409. Old successful composition artifacts remain available in export history/API rather than being overwritten.

Video management lists only composed `Episode.videoUrl` values from episode summaries, without fetching every episode's shots. `POST /api/projects/:id/exports {episodeIds, rangeLabel?}` joins 1–60 unique composed episodes in selection order and stores `source_episode_ids`. For existing clients, the same endpoint still accepts `sceneIds`; submitting neither or both is 422. New fields are added by Alembic `b7e2a91c6d04`, leaving existing export history intact. Both stages use `run_export` / `concat_videos`: FFmpeg normalizes to the project's width, height and FPS and runs through `asyncio.to_thread` so progress polling stays responsive.

`media_service.concat_videos` probes each input with ffprobe. If any clip has audio, it normalizes audio to stereo 44.1 kHz, pads/trims to the probed duration, supplies silence for silent clips, and exports AAC alongside video. All-silent inputs keep a video-only output. Probe failures currently count as no audio; unknown-duration silent clips in a mixed sequence receive a 5-second fallback. These limits and the mixed-clip regression are recorded in the [export-audio issue](../bugs/2026-09-08-export-video-audio-missing.md).

Exports take **no project render lock** because they read finished media and write their own row. Composition dialogs and the videos section poll export status. Composition jobs are identified by `targetEpisodeId` and excluded from the final-export history UI. Running jobs cannot be deleted; deleting a completed job whose file is the active episode video also clears that episode link. `export_jobs` is separate from `generation_jobs`; it has no worker lease/resume mechanism, and project cancel does not cancel it. The API supports history/detail/deletion, not a generation-job-style retry/cancel workflow.

## 8. Queued generation

```text
character-state / prop prompt or image; project voice design or preview
  → enqueue_job → 202 {job}
  → job_worker claims one of 3 lanes → job_handlers dispatch
  → resolve target/config → provider or TTS → persist result → finish_job
  → job-actions.runJob / awaitJob polls GET /api/jobs/:id
```

Registered types: `reference_image`, `prompt_draft`, `voice_design`, `preview`. The frontend polling backs off from 400 ms to 3 seconds and returns the handler result to the original caller. `AbortSignal` calls `POST /api/jobs/:id/cancel`; it does not merely abort polling. Enqueue deduplicates unfinished work by target.

Worker leases last 60 seconds and renew every 20 seconds. Cancellation changes the row; a renewal that no longer matches stops the active task. Paid calls use `max_attempts=1`; lease expiry records `WORKER_LOST` instead of retrying a possibly billed call. Manual `/retry` also requires `attempt < maxAttempts`: after a paid job spends its single attempt it returns `409 job has reached its retry limit`. Another paid attempt currently requires an explicit fresh enqueue, not retrying that exhausted row. Balance is checked both before enqueue and inside the handler. Resolved configurations, including decrypted keys, never belong in durable `input_json`.

## 9. Stop and restart behavior

| Execution path | Stop behavior |
|---|---|
| Registered project render | `/projects/:id/cancel` sets the event and cancels the attached asyncio task |
| Generation job | `/jobs/:id/cancel` writes database state; heartbeat cancels local execution |
| Request-scoped call (breakdown, optimize, cover, standalone media) | Browser abort ends the client's wait; Starlette does not automatically stop work on disconnect |
| Export task | No dedicated cancellation path |

Attached project tasks catch `CancelledError`, clear their unfinished `generating` flags, restore project `idle` / episode `storyboard`, and keep previously persisted media. Event-only cancellation between units can instead produce `partial` when work landed. The cancel endpoint never releases the busy lock itself. Canceling the local task does not guarantee cancellation or a refund at the provider.

On startup, `release_orphaned_runs` marks abandoned project/episode runs failed, resets active media markers, and retains successful files. The job worker settles expired leases; `recover_interrupted_exports` marks queued/running export jobs failed separately, allowing episode composition to be started again; it preserves previously composed videos. Nothing resumes an interrupted provider call automatically. All in-memory cancellation/realtime and startup recovery currently require one backend process.

## 10. Chat streaming

```text
assistant-ui composer (useExternalStoreRuntime)
  → use-chat-controller (AI SDK useChat + DefaultChatTransport)
  → sole real Next BFF stream route
  → backend chat.py → context_graph history/budget/summary → LangChain create_agent
  → backend NDJSON → BFF AI SDK UI stream → custom message list
```

AI SDK owns messages and streaming; assistant-ui owns composer/attachment behavior. `agent_step` events are transient `data-agent_step` parts, not persistent message content. The agent has image/PDF/Word tools and adds read-only `search_error_logs` for super admins. Context compression starts above the token budget (default 100,000) when more than 20 recent messages exist. See [chat design](../design/feature-chat.md) before changing either bridge.

## 11. Billing, artifacts, and diagnosis

Before a provider call, `require_model_balance` gates official configs for non-super-admin users at zero balance. After success, `record_usage` stores a price snapshot and atomically deducts official usage, floored at zero. Personal configs are metered without balance deduction. Micros cross the wire as strings; see [billing](../design/feature-billing.md).

Generated bytes → `store_artifact()` → a relative path under `private_generated/`. Serializers mint signed 30-day links using a UTC-day issue time so polling does not change the URL. The browser can load these links directly. Stable row IDs and `updatedAt` synchronization keep editor drafts independent of signed URLs.

`main.py` assigns a server request ID, returns `X-Request-Id`, and records handled HTTP 5xx as redacted `error_logs`. Once a stream or a background job has begun, failures travel through stream events or job/scene/export state instead; the HTTP error log is not an archive of every generation failure. Super admins can inspect it through `/admin/error-logs` or the chat diagnostic tool. See [logging](../conventions/logging.md) and [Bug history index](../bugs/README.md).

## Realtime events

The backend broadcasts project-scoped `WS_CONNECTED`, `PROJECT_UPDATE`/`PROJECT_DELETED`, `SCENE_UPDATE`/`SCENE_DELETED`, `REFERENCE_DELETED`, `VIDEO_UPDATE`, `EPISODE_UPDATE`/`EPISODE_DELETED`, `CHARACTER_UPDATE`/`CHARACTER_DELETED`, `PROP_UPDATE`/`PROP_DELETED`, `VOICE_UPDATE`/`VOICE_DELETED`, and `JOB_UPDATE` events. `realtime.py` keeps sockets in memory. The legacy workbench is the current browser WebSocket consumer; the active episode editor uses query polling. New event types require consumer handling as well as an emitter.
