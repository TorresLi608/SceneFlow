# Naming

## Backend (Python)

| Thing | Convention | Example |
|---|---|---|
| Module | `snake_case`, singular by role | `episode_service.py`, `artifact_service.py` |
| Function / variable | `snake_case` | `resolve_episode`, `cost_micros` |
| SQLModel class | `PascalCase`, singular | `Episode`, `CharacterState`, `UsageLog` |
| Table name | `snake_case`, plural | `episodes`, `scene_characters`, `generation_jobs` |
| Column | `snake_case` | `image_path`, `balance_micros`, `episode_number` |
| Constant | `UPPER_SNAKE` at module top | `MAX_CONCURRENT_SCENES`, `ARTIFACT_TTL_DAYS` |
| Private helper | leading underscore | `_update_scene`, `_resolve_config` |

**Service function names read as domain verbs**, not CRUD noise: `resolve_character`, `claim_project_status`, `require_model_balance`, `record_usage`. Prefer that over `get_*`/`handle_*` when the function encodes a rule.

## Identifiers

Two ID styles coexist, on purpose:

- **Business rows use prefixed random string IDs** from `new_id(prefix)` → `"<prefix>_<16 hex chars>"`. Prefixes in use: `att`, `char`, `chat`, `cvar`, `ep`, `job`, `msg`, `proj`, `scene`, `usage`. A new entity picks a short prefix and keeps it forever — IDs are stored in existing databases.
- **Account and configuration rows use integer autoincrement PKs**: `users`, `model_configs`, `invitation_codes`, `redemption_codes`, `usage` foreign keys to them. Do not "unify" these; existing data depends on both.

Timestamps: `created_at`, `updated_at`, `deleted_at` (soft delete), all ISO-8601 strings via `now()`.

## API surface

- **Fields are camelCase on the wire**, snake_case in Python. `CamelModel`'s alias generator does this — never hand-translate.
- **Paths are plural and nested by ownership**: `/api/projects/:id/episodes/:episodeId`, `/api/projects/:id/characters/:characterId/states`.
- **Path params are camelCase too**: `episodeId`, `characterId`, `stateId`, `sceneId`.
- Suffix money fields with the unit: `costMicros`, `amountMicros`, `balanceMicros`. Prices per million tokens spell it out: `inputPricePerMillion`.
- Booleans read as predicates: `isLocked`, `isDisabled`, `isDefault`, `replaceAll`.

## Frontend (TypeScript)

| Thing | Convention | Example |
|---|---|---|
| File | `kebab-case.ts(x)` | `project-store.ts`, `scene-card.tsx`, `use-chat-controller.ts` |
| Component | `PascalCase`, one main export per file | `SceneCard`, `WorkbenchEditor` |
| Hook | `useX` in a `use-x.ts` file | `useChatController`, `useI18n` |
| Action | `<verb><Noun>Action` in `src/actions/*-actions.ts` | `listEpisodesAction`, `updateProductionSettingsAction` |
| Store | `useXStore` in `src/store/x-store.ts` | `useProjectStore`, `usePreferencesStore` |
| Type | `PascalCase` in `src/types/*.ts` | `Episode`, `SceneUpdatePayload` |
| Request/response type | `<Verb><Noun>Input` / `<Noun><Shape>Response` | `CreateEpisodeInput`, `EpisodeListResponse` |

- **Route-local components live in `_components/`** next to the page. The underscore keeps them out of routing.
- **Route groups** carry no URL segment: `(workspace)` is layout grouping, not a path.
- **Query keys** are only ever built in `src/actions/query-keys.ts` — parameterised keys are functions there, never inline arrays at a call site.

## i18n keys

Dot-namespaced by surface, then by meaning: `common.save`, `auth.loginTitle`, `home.projectStatus.idle`, `chat.inputPlaceholder`. Add every key to **both** the `zh` and `en` dictionaries in the same commit. Interpolation uses i18next double braces: `"common.currentUser": "当前用户：{{username}}"`.

## Tests

- Backend: `tests/test_<area>.py`; test functions are full sentences describing the rule — `test_deleting_an_episode_takes_its_shots_with_it`, `test_locking_a_shot_is_an_edit_a_patch_can_undo`. Keep that style; it is the failure message.
- Frontend: `<subject>.test.mts` beside the code under test.
