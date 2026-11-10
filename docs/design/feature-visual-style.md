# Feature: project visual style

Implemented on **2026-11-10**. AI 生剧 projects now carry a structured `productionSettings.visualStyle`: `cinematic`, `anime`, `realistic`, or `3d`. The creation/edit dialog and project information page share [VisualStyleField](../../frontend/src/components/visual-style-field.tsx); the legacy production-settings form exposes the same choices. The control uses Base UI ToggleGroup, keeps one selection, and supplies Chinese/English labels and an accessible group description.

## Persistence and defaults

- New projects default to `cinematic`, including API creation without an explicit settings block. Creation passes the selected style in `productionSettings`.
- Project information edits can atomically save title/description/bible and a partial `productionSettings` block through `PATCH /api/projects/{id}`. This and the existing `PATCH /{id}/production-settings` share `_production_settings_updates`, preserving unsent fields and cross-field validation. Realtime responses include the complete updated settings block.
- `stylePrompt` remains the custom supplement and is shown as “风格补充说明”. The selected visual preset takes priority when another prompt or reference suggests a conflicting visual treatment.
- Alembic revision [a8d5c2e7f901](../../backend/migrations/versions/a8d5c2e7f901_project_visual_style.py) adds `projects.visual_style`. Existing rows receive an empty style and retain their custom style text. Empty legacy styles show no selected tile until the user chooses one. No inference or migration rewrites old custom prompts. An absent/null typed PATCH leaves the style alone; an explicit empty string restores custom-only behavior through the API.
- The new column is migrated during normal backend startup. A backend already running before the change needs a restart to load the new code and apply the migration. No runtime `ALTER TABLE` or compatibility `create_all` was added.

## How the configured style reaches generation

[prompt_service.py](../../backend/app/services/prompt_service.py) owns the pure preset descriptions and `visual_style_prompt` resolver. It combines the enum and custom text without database or provider access. Generation owners resolve the saved project settings before awaiting a model:

| Flow | Owner / hand-off |
|---|---|
| Cover generation | Creation/edit dialog sends its draft selection before a project exists. `ProjectCoverField` sends saved project settings. `GenerateCoverRequest` validates `visualStyle`; the endpoint resolves it into `cover_prompt`. |
| Script polish / legacy parsing | `projects.py` adds project style to the text sent to the model; the original source text remains separately stored. |
| Episode breakdown | `episodes.py::breakdown_episode` includes style in the model's user prompt, while retaining existing replacement confirmation and in-place video breakdown behavior. |
| Character / prop prompt drafts | `job_handlers.draft_reference_prompt` loads current saved style and includes it in drafting context. |
| Character / prop reference images | `job_handlers.draw_reference_image` adds current saved style to the reviewed prompt for the model call. The editable `finalPrompt` retains the reviewed text, so regeneration does not accumulate old style directives. |
| Episode tone sheet / storyboard frames | `episodes.py::_plan` snapshots the resolved style into `StoryboardPlan.style_prompt`; both tone and per-shot templates already consume this value. |
| Legacy shot image generation | `_scene_payloads` carries resolved style into `generation_service.build_image_prompt`. The old hardcoded “cinematic anime” phrase is removed so it cannot conflict with a selected realistic/3D style. |
| Shot video generation | The same scene payload supplies style to `_generate_scene_video`, alongside the motion, camera, transition, continuity and compiled reference instructions. Frame/motion fields and reference ordering remain separate. |
| Compiled prompt preview | `prompts.py::preview_compiled_prompt` includes saved style so the preview retains the project constraint. |

Changing style affects future generation. Already generated media, uploads, exports and approved references are retained; the change does not automatically regenerate or delete them. Reference identities and budgets remain unchanged. Audio-only voice design/audition and standalone media menus do not inherit an unrelated project's visual style. Actual image/video appearance still depends on the selected provider following the supplied instructions; no paid provider output-quality verification was performed.

## Validation

[test_project_visual_style.py](../../backend/tests/test_project_visual_style.py) uses temporary databases, media directories and offline providers. It checks new-project defaults, all four styles through save/list/render payloads, cover model arguments, invalid values, null/empty PATCH behavior, tone/storyboard/video model hand-offs, and queued prompt/image jobs. Existing character/prop tests check that editable prompts remain unchanged.

The migration was exercised against a disposable database at the prior head with an existing project and custom style, then upgraded to the new head. `alembic check` reported no new upgrade operations; the legacy project title, custom style and empty enum survived. OpenAPI was regenerated through the isolated documented command.

A browser fixture at `/private/tmp/sceneflow-visual-style-ui-check/` bundles the actual creation/edit dialog and project information page with React Compiler and application styles, using simulated axios responses. Verified default selection, active-choice clicks retaining selection, create with anime, edit with realistic, information save with 3D plus custom notes, and cover requests carrying the corresponding style. Chinese and English layouts were observed at the normal browser viewport; mobile and real provider rendering were not tested. Screenshots are `info-saved.jpg` and `info-en.jpg` in that fixture folder. The first sandboxed server bind failed; the approved retry started the local-only fixture.

Executed checks on **2026-11-10**:

```bash
cd backend
check_dir=$(mktemp -d /tmp/sceneflow-style-final.XXXXXX)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_project_visual_style test_projects_api test_project_production test_project_cover test_storyboard_api test_breakdown_api test_props_api test_characters_api test_video_service test_prompt_optimization test_prompt_prefixes test_prompt_compiler test_database test_skills
```

The run passed 13 modules; `test_prompt_prefixes` still expected a compiled preview without the new style. Its expected prompt was updated to include the cinematic constraint while retaining the existing prefix/reference-order assertions. A fresh isolated `sh scripts/run_tests.sh test_prompt_prefixes` passed, completing the 14 selected modules. Earlier project/character/prop assertion failures were resolved by explicitly testing legacy custom-only style and retaining reviewed editable prompts separately from injected generation style. In `frontend`, `pnpm exec tsc --noEmit` and `pnpm lint` both exited 0. `git diff --check` and the new documentation-link check passed. Migration upgrade/check and `scripts/regen_api_spec.py` ran with temporary `DATABASE_URL` and media paths; no real local database/media reset or paid generation was performed.
