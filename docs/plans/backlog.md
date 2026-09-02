# Backlog

> Verified gaps in the code as of 2026-08-12, not a commitment or a priority order. Each item says what is true today and why it matters. Promote to `current-sprint.md` when someone picks it up; delete when it stops being true.

## Correctness and reliability

- **`tests/run_all.py` is not isolated.** One process, `runpy` per file, state leaks between files, and the first failure aborts the rest. Currently fails in `test_characters_api.py` though every file passes alone. Until fixed, the full suite is not a usable gate. *(Also in the sprint file — highest value.)*
- **Renders are not restart-safe.** `asyncio.create_task(run_generation(...))` still runs storyboard, tone sheet, project generation, and export in the API process. A deploy or crash mid-run leaves the project holding its busy lock with no worker to resume. `generation_jobs` now *has* a consumer (`app/services/job_worker.py`) and the smaller paid calls have moved onto it; these have not.
- **Realtime is single-process.** `app/core/realtime.py` keeps an in-memory `dict[project_id, set[WebSocket]]`. A second uvicorn worker would silently deliver `SCENE_UPDATE` to only the clients on the same process. Needs a shared broker before horizontal scaling — and it is the reason the generation-jobs worker runs in-process rather than as its own service: a handler that broadcasts from another process would reach nobody.
- **No token revocation.** JWTs live 24h; disabling an account is the only revocation, and it works only because `current_user` re-reads the user on every request. Do not move role or state into token claims.

## Product gaps

- **Project jobs are invisible.** Cancel and retry endpoints have no UI.
- **No search over domain content.** Scripts, shots, characters, and chat messages are not searchable; only admin lists have filters. See `../design/feature-search.md`.
- **No sort controls** on any list; each has one fixed order.
- **Project list has no server-side paging** — it fetches everything and filters client-side.

## Security and operations

- **No rate limiting** on login, registration, or code redemption.
- **No spend controls** beyond the `402` at zero balance; a long run can outspend the remaining balance because the decrement floors at zero rather than blocking mid-run.
- **Secrets rotation is destructive to artifacts.** Signed URLs are keyed off `SCENEFLOW_JWT_SECRET`; rotating it invalidates every outstanding link (existing rows are cleaned up by `_migrate_scene_assets`). There is no key-versioning scheme.
- **No health signal beyond `/healthz`**, which does not check the database or the artifact directory.

## Developer experience

- **No frontend component testing.** Only pure `.ts` modules are testable (`node --test` with type stripping). Logic worth testing has to be extracted from components — `user-list.ts` is the model to follow, but most logic still lives inline.
- **`pnpm build` has hung in this project before** (Turbopack, no output for minutes). `tsc --noEmit` is the practical type gate; the build is not part of a reliable loop. The webpack path has completed when Turbopack did not — see `../conventions/testing.md`.
- **Two ID styles** (prefixed strings for business rows, integer PKs for accounts and configs) are load-bearing for existing data but undocumented outside `../conventions/naming.md`.

## From the author's own use (2026-09-02)

Field reports moved here out of `DISCLAIMER.md`, where they had been pasted by accident and committed. Spot-checked against the code on arrival: *registration email is already optional* (`auth.py` only demands a code when an email is supplied) and *`wan2.7-t2v` / `wan2.7-i2v` are already in the catalog* (`api/v1/settings.py`), so both of those are dropped. The rest stand, but are reports rather than verified reads — confirm before picking one up.

- **Doubao video capabilities may be auto-filled wrong.** Selecting a Doubao model fills reference-image / reference-video / reference-audio support from the table in `config_service.py`; the author reports the result does not match the provider. Check against the [Seedance 2.5](https://docs.volcengine.com/docs/82379/2607689?lang=zh) and [Seedance 2.0](https://docs.volcengine.com/docs/82379/2222480?lang=zh) prompt guides. The Wan side has equivalents: [Wan 3.0 video](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference) and [Wan 2.7 reference-to-video](https://help.aliyun.com/zh/model-studio/wan-video-to-video-api-reference).
- **The speaker picker may be removable.** Proposal: when a clip is generated, detect which shots carry dialogue and attach the line and its character automatically, instead of asking the user to set a speaker per shot. `_scene_payloads` already infers a speaker from the `角色：台词` form when the field is unset, so this would extend an existing fallback rather than add a mechanism.
- **Default `@素材` are invisible and cannot be removed.** Only manually mentioned assets become chips under the prompt box. Defaults still ship to the provider and still occupy the first image slots, so the numbering the user sees does not match the request. Deleting a chip also does not remove the matching `@label` from the text, and typing `@` after an existing mention can leave two `@` characters. *Partly addressed:* the batch that removed the shot's own frame from `defaultVideoReferences` fixed the worst symptom, not the general case.
- **Check whether the final-prompt preview maps `@素材` to positional references.** Reported as showing the raw label instead of `<图片N>`. `prompt_compiler.compile_prompt` does implement the Doubao `<图片N> 标签` form, and `/api/prompts/compile` passes the project's provider, so this may already be fixed or may be specific to one path — reproduce before changing anything.
- **The `@素材` picker needs keyboard support** — up/down to move, Enter to select.

## Explicitly not planned

Recorded so they are not re-litigated:

- Replacing `google-genai` with `langchain-google-genai` — the native SDK is kept for Gemini image generation; swap only if Gemini chat needs to be a native LangChain provider.
- Unifying the two ID styles.
