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

## Explicitly not planned

Recorded so they are not re-litigated:

- Replacing `google-genai` with `langchain-google-genai` — the native SDK is kept for Gemini image generation; swap only if Gemini chat needs to be a native LangChain provider.
- Unifying the two ID styles.
