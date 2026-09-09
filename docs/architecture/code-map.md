# Code map

Base inventory checked on **2026-09-07**; media-preview, voice-design, and export-audio entries checked on **2026-09-08** against the working tree. For a bug, first search the [Bug history index](../bugs/README.md) and open matching details. This is a navigation map, not a claim that every listed test currently passes. Read [overview](overview.md) for runtime/state, [data flow](data-flow.md) for behavior, and [boundaries](boundaries.md) before moving responsibilities.

## Repository entry points

```text
SceneFlow/
├── AGENTS.md                       Shared agent instructions
├── CLAUDE.md                       Imports AGENTS.md
├── docs/                           This knowledge base
├── package.json                    Root install/dev/Docker commands
├── scripts/                        Python environment and dev-process launchers
├── docker-compose.yml              Frontend + single backend, data bind mount + media volume
├── backup.sh                       Consistent whole-directory database/media backup
├── data/                           SQLite data (gitignored, created on first use)
├── backend/
│   ├── docker-entrypoint.sh        Fix data bind-mount ownership, drop to the app user
│   ├── app/main.py                 Lifespan, routers, request IDs, error handlers
│   ├── app/api/v1/                 HTTP and WebSocket endpoints
│   ├── app/services/               Workflows, providers, queue, artifacts
│   ├── app/llms/                   Text/image model router and registry
│   ├── app/graph/graphs/           Chat history and token-budget assembly
│   ├── app/models/                 SQLModel tables
│   ├── app/schemas/                Typed requests and response serializers
│   ├── app/core/                   Config, DB, security, logging, realtime, cancellation
│   ├── migrations/versions/        Alembic history
│   ├── tests/                     Executable test_*.py self-checks
│   └── scripts/                   Isolated test runner and OpenAPI regeneration
└── frontend/
    ├── next.config.ts             Fallback BFF rewrite, compiler, proxy timeout
    ├── src/app/                   Next App Router pages and route-local components
    ├── src/actions/               HTTP actions and query keys
    ├── src/store/                 Auth/preferences and ephemeral client stores
    ├── src/lib/                   HTTP, i18n, money, reference budgets, media helpers
    ├── src/components/            Shared prompt/model controls and UI primitives
    ├── src/providers/             React Query and preferences providers
    └── src/types/                 Frontend wire/domain types
```

Development data at `data/app.db` and `backend/private_generated/` is not a fixture. Use a temporary `DATABASE_URL` and media path for checks that start the backend. Configuration/seed/persistence regressions live in `backend/tests/test_database.py`.

## Frontend routes

Route groups in parentheses do not appear in URLs. Paths below are relative to [frontend/src/app](../../frontend/src/app/).

| URL | Page / local owner | What it does |
|---|---|---|
| `/` | [page.tsx](../../frontend/src/app/page.tsx) | Redirects to `/chat` |
| `/login`, `/register` | [login](../../frontend/src/app/login/page.tsx), [register](../../frontend/src/app/register/page.tsx) | Login, invitation registration, optional email verification |
| `/chat` | [(workspace)/chat](../../frontend/src/app/(workspace)/chat/page.tsx) | Session list, custom message list, assistant-ui composer |
| `/images`, `/videos`, `/audio` | [images](../../frontend/src/app/(workspace)/images/page.tsx), [videos](../../frontend/src/app/(workspace)/videos/page.tsx), [audio](../../frontend/src/app/(workspace)/audio/page.tsx) | Standalone image/video generation and account voice design |
| `/ai-script` | [(workspace)/ai-script](../../frontend/src/app/(workspace)/ai-script/page.tsx) | Series list, filters, create/edit project dialog |
| `/profile`, `/usage` | [profile](../../frontend/src/app/(workspace)/profile/page.tsx), [usage](../../frontend/src/app/(workspace)/usage/page.tsx) | Account, personal/official model choices, redemption, usage |
| `/admin` | [(workspace)/admin](../../frontend/src/app/(workspace)/admin/page.tsx) | Redirects to `/admin/models` |
| `/admin/{models,users,invitation-codes,redemption-codes,usage-logs,error-logs}` | [admin subtree](../../frontend/src/app/(workspace)/admin/) | Super-admin management; page-local managers under `_components/` |
| `/projects/:projectId` | [projects/[projectId]/page.tsx](../../frontend/src/app/projects/[projectId]/page.tsx) | Redirects to the project's `/info` |
| `/projects/:projectId/info` | [(workbench)/info](../../frontend/src/app/projects/[projectId]/(workbench)/info/page.tsx) | Synopsis, cover, production settings, four model picks and generation defaults |
| `/projects/:projectId/{characters,props,voices}` | [(workbench) subtree](../../frontend/src/app/projects/[projectId]/(workbench)/) | Series bible, setting sheets, voice profiles, account voice import |
| `/projects/:projectId/assets` | [(workbench)/assets](../../frontend/src/app/projects/[projectId]/(workbench)/assets/page.tsx) | Shared series asset management, search, source/episode filters, imports and image merging |
| `/projects/:projectId/episodes` | [(workbench)/episodes](../../frontend/src/app/projects/[projectId]/(workbench)/episodes/page.tsx) | Episode CRUD and navigation into the editor |
| `/projects/:projectId/episode/:episodeId` | [episode/[episodeId]](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/page.tsx) | Script breakdown, tone sheet, shot editing, references, image/video batches |
| `/projects/:projectId/videos` | [(workbench)/videos](../../frontend/src/app/projects/[projectId]/(workbench)/videos/page.tsx) | Select finished clips, order and merge them, inspect/download exports |
| `/projects/:projectId/workbench` | [workbench/page.tsx](../../frontend/src/app/projects/[projectId]/workbench/page.tsx) | Legacy single-screen editor; still reachable directly |

The [workspace shell](../../frontend/src/app/(workspace)/_components/workspace-shell.tsx) handles the general workspace session/navigation. The [project layout](../../frontend/src/app/projects/[projectId]/(workbench)/layout.tsx) supplies seven project sections. The episode editor and legacy editor sit outside that route group and supply their own full-screen layout. Layouts are not backend authorization boundaries.

### Episode editor: where to change what

All components in this table live beside the [episode page](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/page.tsx).

| Owner | Responsibility |
|---|---|
| [page.tsx](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/page.tsx) | Queries, 3-second busy polling, mutations, selection, run/cancel controls, re-split and unsaved-model-settings dialogs |
| [breakdown-panel.tsx](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/breakdown-panel.tsx) | Collapsible script/breakdown controls, detail level, bible selection |
| [shot-row.tsx](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/shot-row.tsx) | Shot drafts, save, image/video prompts, prefix lists, frame slots, shared media budgets |
| [mention-textarea.tsx](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/mention-textarea.tsx) | `prompt-area` adapter for typed mentions and reference chips |
| [reference-picker.tsx](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/reference-picker.tsx) | Available reference identities and media selection |
| [prompt-prefix-list.tsx](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/prompt-prefix-list.tsx) | Ordered preambles and server-provided tone presets |
| [asset-library-dialog.tsx](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/asset-library-dialog.tsx) | Re-export of shared [project-asset-manager.tsx](../../frontend/src/app/projects/[projectId]/_components/project-asset-manager.tsx); same catalogue and operations as the project assets page |
| [media-preview-dialog.tsx](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/media-preview-dialog.tsx) | Compatibility re-export of the shared image/video preview dialog; no audio support |

Shared support: [reference-budget.ts](../../frontend/src/lib/reference-budget.ts) counts distinct assets across sibling editors; [artifact-url.ts](../../frontend/src/lib/artifact-url.ts) handles artifact URLs; [prompt-field.tsx](../../frontend/src/components/prompt-field.tsx) supplies preset/language/optimize controls elsewhere in the workbench.

## Feature → action → backend → checks

Actions below are in [frontend/src/actions](../../frontend/src/actions/); endpoint modules are in [backend/app/api/v1](../../backend/app/api/v1/), services in [backend/app/services](../../backend/app/services/). Test names are relative to [backend/tests](../../backend/tests/). Follow the shared owner before changing a single caller.

| Feature | Frontend owner | Backend owners | Existing regression entry points |
|---|---|---|---|
| Login / registration / account | `auth-actions.ts`, `user-actions.ts` | `auth.py`, `users.py`, `api/deps.py`, `core/security.py`, `verification_service.py`, `email_service.py` | `test_invitation_codes.py`, `test_email_verification.py`, `test_admin_users.py` |
| Model configuration / capabilities | `settings-actions.ts`, `admin-actions.ts` | `settings.py`, `admin.py`, `config_service.py` | `test_config_service.py`, `test_project_production.py`, `test_video_service.py` |
| Series / episode / shot CRUD | `projects-actions.ts` | `projects.py`, `episodes.py`, `project_service.py`, `episode_service.py` | `test_projects_api.py`, `test_episodes_api.py`, `test_project_guards.py` |
| Cover generation / upload | `projects-actions.ts` | `projects.py`, `reference_service.py`, `artifact_service.py` | `test_project_cover.py` |
| Script breakdown | `projects-actions.ts` → `breakdownEpisodeAction` | `episodes.py` → `breakdown_service.py` → `llms/router.py::breakdown_script` | `test_breakdown_api.py`, `test_agent_service.py` |
| Tone sheet / storyboard | `projects-actions.ts` → tone/storyboard actions | `episodes.py` → `storyboard_service.py` | `test_storyboard_api.py`, `test_prompt_prefixes.py`, `test_project_guards.py` |
| Character states / props | `projects-actions.ts` | `characters.py`, `props.py`, corresponding services, `reference_service.py`, `media_service.py`, `job_handlers.py` | `test_characters_api.py`, `test_props_api.py`, `test_media_service.py` |
| Project voice design/redesign / account library | [(workbench)/voices/page.tsx](../../frontend/src/app/projects/[projectId]/(workbench)/voices/page.tsx), `projects-actions.ts`, `voice-generation-actions.ts` | `voices.py`, `user_voices.py`, `voice_service.py`, `qwen_voice_service.py`, `tts_service.py`, `job_handlers.py::design_voice` | `test_voices_api.py`, `test_voice_design_api.py`, `test_qwen_voice_service.py`, `test_tts_service.py` |
| Asset management / explicit references | `project-asset-manager.tsx`, `use-project-resources.ts`, `project-resources.ts`, episode reference components | `assets.py`, `asset_catalog_service.py`, `projects.py`, `reference_service.py` | `test_storyboard_api.py` (cross-episode catalogue and aliases), `test_projects_api.py`; frontend `project-resources.test.mts` |
| Prompt presets / optimization / compilation | `prompt-actions.ts`, `reference-budget.ts` | `prompts.py`, `prompt_service.py`, `prompt_prefix_service.py`, `prompt_compiler.py` | `test_prompt_optimization.py`, `test_prompt_prefixes.py`, `test_prompt_compiler.py`; frontend `reference-budget.test.mts` |
| Per-shot video | `projects-actions.ts` → `generateVideoAction` | `projects.py` → `generation_service.py::run_video_generation` → `video_service.py` | `test_project_production.py`, `test_video_service.py`, `test_prompt_compiler.py` |
| Merge/export with source audio | `projects-actions.ts`, project videos page | `exports.py` → `export_service.py::run_export` → `media_service.py::concat_videos` / `_probe_video_audio_and_duration` | `test_exports_api.py` (including mixed audio/silent clips), `test_media_service.py` |
| Queued generation / cancel / retry | `job-actions.ts` (`runJob`, `awaitJob`) | `jobs.py`, `job_service.py`, `job_worker.py`, `job_handlers.py` | `test_job_service.py`; `tests/job_queue.py` drains handlers for API tests |
| Standalone images / videos | `image-generation-actions.ts`, `video-generation-actions.ts` | `images.py` → `llms/router.py`; `videos.py` → `video_service.py` | `test_images.py`, `test_video_service.py` |
| Chat / generated documents | `chat-actions.ts`, `use-chat-controller.ts`, composer and message list | `chat.py`, `chat_service.py`, `graph/graphs/context_graph.py`, `agent_service.py`, `artifact_service.py`, `utils/attachment_parser.py` | `test_agent_service.py`, `test_chat_balance.py`, `test_artifact_service.py` |
| Billing / redemption / admin logs | `usage-actions.ts`, `user-actions.ts`, `admin-actions.ts`, `ui/date-time-range-picker.tsx` | `usage.py`, `users.py`, `admin.py`, `usage_service.py`, `utils/time_range.py` | `test_usage_service.py`, `test_redemption_codes.py`, `test_admin_usage_logs.py`, `test_log_time_ranges.py`; frontend `money.test.mts`, `date-time-range.test.mts`, `user-list.test.mts` |
| Request diagnosis | `admin-actions.ts`, admin error-log page, `ui/date-time-range-picker.tsx` | `main.py`, `core/logging.py`, `error_log_service.py`, `utils/time_range.py`, `agent_service.py::search_error_logs` (admin-only tool) | `test_breakdown_api.py`, `test_log_time_ranges.py`; [Bug history index](../bugs/README.md) |

### Cross-cutting owners

The standalone image/video/voice panels each wrap an internal editor with a reset key. This restores the form and preview without removing stored history; audio does not auto-select a saved voice after reset. See [the reset record](../bugs/2026-09-07-generation-editor-reset.md). The standalone video's `selectedFps` follows the capability list, including omission when the list is empty.

| Path | Responsibility |
|---|---|
| [backend/app/main.py](../../backend/app/main.py) | Mounts routers; migrates/seeds DB, clears orphaned runs, starts/stops worker; error envelopes and request IDs |
| [backend/app/schemas/requests.py](../../backend/app/schemas/requests.py) | Typed workbench payloads, aliases, validation; legacy dict-body endpoints remain in API modules |
| [backend/app/schemas/serializers.py](../../backend/app/schemas/serializers.py) | Domain wire shape, explicit-reference/frame flags, signed asset links |
| [backend/app/core/database.py](../../backend/app/core/database.py) | Per-path engines, SQLite pragmas, transaction context, Alembic startup |
| [backend/app/core/runs.py](../../backend/app/core/runs.py) | In-memory project cancellation flags and attached asyncio tasks |
| [backend/app/core/realtime.py](../../backend/app/core/realtime.py) | In-process project broadcasts; [websocket.py](../../backend/app/api/v1/websocket.py) authenticates subscriptions |
| [frontend/next.config.ts](../../frontend/next.config.ts) | Fallback `/api/bff/*` rewrite, 15-minute proxy timeout, React Compiler |
| [chat stream route.ts](../../frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts) | Sole real BFF route: backend NDJSON → AI SDK UI stream |
| [frontend/src/lib/http/client.ts](../../frontend/src/lib/http/client.ts) | Axios auth injection, 90-second default timeout, 15-minute generation timeout, logout on 401 |
| [frontend/src/actions/query-keys.ts](../../frontend/src/actions/query-keys.ts) | Shared React Query identities; busy polling must update the same project key |
| [frontend/src/components/media-preview-dialog.tsx](../../frontend/src/components/media-preview-dialog.tsx) | Shared image/video preview and open-in-new-tab link. Episode tone/shot/reference/asset previews and project videos use the route-local re-export; workbench `ReferenceImage` and `SheetPreview` import it directly |
| [reference-image.tsx](../../frontend/src/app/projects/[projectId]/(workbench)/_components/reference-image.tsx), [project-cover-field.tsx](../../frontend/src/app/projects/[projectId]/(workbench)/_components/project-cover-field.tsx) | `ReferenceImage` handles cover/state/prop image upload, generation, and preview; `SheetPreview` previews character and merged cast/prop sheets |
| [frontend/src/lib/model-providers.ts](../../frontend/src/lib/model-providers.ts) | Frontend provider presets, connection defaults, and Qwen audio target-model hint; runtime target-model fallback belongs to `qwen_voice_service.py` |
| [frontend/src/components/ui/date-time-range-picker.tsx](../../frontend/src/components/ui/date-time-range-picker.tsx), [date-time-range.ts](../../frontend/src/lib/date-time-range.ts) | Shared log-range picker, local day defaults, second-precision display/parsing, UTC request parameters |
| [frontend/src/store](../../frontend/src/store/) | Persisted user/preferences; ephemeral legacy project copy and unsaved model-settings flags |
| [frontend/src/lib/i18n.ts](../../frontend/src/lib/i18n.ts) | Both `zh` and `en` dictionaries and `useI18n()` |

## Data model map

All tables originate in [backend/app/models](../../backend/app/models/); Alembic revisions live in [migrations/versions](../../backend/migrations/versions/). Model filenames below link to their declarations.

| Model file | Tables | Ownership / purpose |
|---|---|---|
| [project.py](../../backend/app/models/project.py) | `projects`, `episodes`, `scenes`, `generation_jobs` | Series → installments → shots; project-scoped queue with optional episode/shot target |
| [character.py](../../backend/app/models/character.py) | `characters`, `character_states`, `scene_characters` | Series bible, parallel/ranged looks, shot cast |
| [prop.py](../../backend/app/models/prop.py) | `props` | Series objects, optional character owner, setting sheet |
| [voice.py](../../backend/app/models/voice.py) | `voice_profiles` | Project timbres and audition clips, bound to characters |
| [user_voice.py](../../backend/app/models/user_voice.py) | `user_voices` | Account-level Qwen designs; draft versus saved library entries |
| [asset.py](../../backend/app/models/asset.py) | `assets` | Project-owned named image/video/audio imports and merged images |
| [export.py](../../backend/app/models/export.py) | `export_jobs` | Ordered clip selection and output file; separate from `generation_jobs` |
| [config.py](../../backend/app/models/config.py) | `model_configs`, `user_official_config_defaults` | Personal/official providers, capability declarations, pricing, account defaults |
| [user.py](../../backend/app/models/user.py) | `users`, `email_verifications`, `invitation_codes`, `redemption_codes` | Credentials, roles, balance, registration, top-up |
| [chat.py](../../backend/app/models/chat.py) | `chat_sessions`, `chat_messages` | Conversation history and compressed context |
| [usage.py](../../backend/app/models/usage.py) | `usage_logs` | Metering and historical price snapshots |
| [error_log.py](../../backend/app/models/error_log.py) | `error_logs` | Redacted HTTP 5xx diagnosis keyed by request ID |

## Active and legacy paths

| Path | Current status |
|---|---|
| Episode editor → `/breakdown`, `/tone-sheet`, `/storyboard`, `/generate-video` | Primary production flow; React Query polling and local shot drafts |
| Legacy `workbench-editor.tsx` → `/parse`, `/generate`, project WebSocket | Still callable; `project-store.ts` and legacy `scene-card.tsx` belong here |
| `generation_jobs` worker | Four registered job types: `reference_image`, `prompt_draft`, `voice_design`, `preview` |
| Tone/storyboard/video/export tasks | Still in the API process; persisted rows do not imply restartable execution |
| `context_graph.py` | Plain context-assembly functions; LangChain `create_agent` has no configured durable checkpointer or production approval workflow |
| `use-unsaved-settings-check.ts` | Unused placeholder hook returning `false`; active pages use `unsaved-settings-store.ts` instead |
| Scene audio columns and `video_fps` | Compatibility storage; no per-shot TTS production stage or current FPS control in the model-settings UI |

For commands use [testing](../conventions/testing.md) and [local setup](../reference/local-setup.md). For unresolved behavior use [backlog](../plans/backlog.md); do not infer implementation from an old comment or a planned phase.
