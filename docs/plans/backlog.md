# Backlog

Reviewed on **2026-09-07** against application code at `afa10d8`. These are implementation gaps and separately identified field reports, not scheduled commitments. Source/test entry points are in the [code map](../architecture/code-map.md). Update or remove an item after it is implemented and verified.

## Generation and references: source-verified gaps

- **Remaining work is not durably executed.** Tone/storyboard, legacy generation, video batches, and exports still use API-process asyncio tasks. `release_orphaned_runs` now marks abandoned project/episode runs failed and clears media busy flags, so the old permanent-lock description is obsolete; it does not resume work. Export rows are not covered by that cleanup. Move execution only with a defined lock, cancel, billing, and recovery contract.
- **Request abort is not server cancellation.** Breakdown, prompt optimization, cover generation, and standalone image/video/voice calls still run in request handlers. AbortController alone cannot promise a provider stop; project `runs.cancel` and the database job cancel endpoints cover different paths.
- **Reference preview/validation/rendering still disagree in legacy video cases.** `prompts.preview_compiled_prompt` and `/generate-video` validation can count an automatic storyboard image, while `_generate_scene_video` treats saved frame slots separately and filters their media out. Consolidate identity/order/count handling before promising identical preview and provider numbering for all inputs.
- **Storyboard plan snapshots omit some intended inputs.** The current UI's saved per-shot references reach `run_storyboard`; request-wide `references` are not populated into the loop's per-shot source map. An anchor created during that run writes tone prefixes after the plan's prefix/reference snapshot was built. Existing comments/tests describing automatic tone/predecessor injection need review alongside any fix.
- **Deleting an asset does not clean every reference location.** `assets.delete_asset` and `reference_service.clear_generation_reference` clean direct shot image/video lists, but not all prefix lists or first/last-frame JSON. Removed assets can leave unavailable references. A replacement breakdown also retains the episode tone-sheet path even though its shot rows/grid may have changed.
- **Save-time reference-budget enforcement is incomplete.** `projects.update_project_scene` calls `models.active_image_config` / `active_video_config`, which are not ModelRouter methods, and catches lookup exceptions. The image branch also catches its own limit error. Render-time checks exist, but the save path cannot be treated as equivalent; use `test_prompt_prefixes.py` and the shared config/reference owners when fixing it. The related [video-reference save history](../bugs/2026-09-04-video-reference-save.md) records the earlier partial fix.
- **Paid-job retry does not bypass the attempt cap.** `retry_job` rejects `attempt >= max_attempts`, including a failed/lost paid job after its first attempt. A fresh enqueue is the current way to request another paid attempt; comments promising one-click `/retry` after `WORKER_LOST` are stale.
- **Generation-job history is not surfaced.** Per-operation controls can cancel their awaited job, but there is no project job-history/retry screen despite list/detail/cancel/retry endpoints.

## Reliability and developer experience

- **Single backend process is required.** Realtime and project cancellation are in memory; startup lock cleanup assumes no other process is rendering. A broker alone is insufficient without coordinated claims/recovery before multiple workers or an external consumer.
- **The old aggregate test runner is not isolated.** `tests/run_all.py` shares imports/globals via `runpy` and aborts on the first failure. `scripts/run_tests.sh` is the current isolated runner, but requires explicit test names. Do not preserve old claims that all files passed without a fresh run.
- **Legacy editor remains.** `/projects/:id/workbench`, `/parse`, the old image `/generate`, `project-store`, and the browser WebSocket path are still present. Remove only after checking callers and compatibility requirements.
- **Unsaved settings are flags, not retained drafts.** Only the model panel uses `unsaved-settings-store`; a page reload loses the flag and draft. `use-unsaved-settings-check.ts` is unused and always returns false. Avoid routing new behavior through it.
- **Frontend component interactions lack automated coverage.** Four Node suites cover pure modules; no DOM harness covers shot draft reconciliation, dialogs, mention editing, or stream scrolling. Add checks appropriate to a real regression, not a framework without a use case.
- **Production-build history is not a current green gate.** Turbopack has hung; use typecheck/lint for the normal loop and record completed build results when deployment validation is needed.

## Privacy, security, and operations

- **Prompt logging violates the documented boundary.** `projects.update_project_scene` currently logs prefix values and serialized prompt content at info level. The redacted `error_logs` table does not sanitize those ordinary log lines. Remove content logging when this code is next fixed; keep identity and decision fields.
- **SMTP fallback is not environment-gated.** With no SMTP host/user, `email_service` logs a verification code even in production. Email sending has a 60-second cooldown, but login/registration/verification attempts have no general rate limiting.
- **No provider billing reconciliation or spend reservation.** A local cancellation can leave a paid provider call unaccounted for; balance deduction floors at zero rather than reserving an estimated run cost. Paid queue calls are deliberately not retried automatically.
- **Token/key rotation has limited lifecycle support.** JWT rotation invalidates sessions and outstanding signed links; stored media paths remain usable and can be re-signed. There is no token revocation list or refresh-token flow. AES rotation needs a strategy for already-encrypted provider keys.
- **Diagnostics are request-focused.** HTTP 5xx records are best-effort; later stream/job/render/export failures are not all captured there. `/healthz` checks neither storage nor worker progress; there is no error-log retention policy.
- **Development launcher terminates port occupants.** `scripts/dev-backend.mjs` can kill an unrelated process using `PORT`; it does not verify that process belongs to SceneFlow. Inspect the owner or use direct uvicorn on a free port.

## Product scale

- No cross-entity/content search, server-side project paging, or user-facing server-side sort contract. Current lists/filtering are described in [search design](../design/feature-search.md).
- Error-log search queries on each text change; no debounce there yet.
- Chat has no editing/branching/regeneration, configurable tool registry, or durable production approval graph. Long summary-of-summary context can drift; attachment extraction is synchronous.

## Field reports to reproduce

The following originated in the author's 2026-09-02 notes. Their user-visible behavior has **not** been re-tested during this documentation refresh:

- **Doubao capability defaults may differ from the provider.** Compare current `config_service.py` tables and the admin catalog with [Seedance 2.5](https://docs.volcengine.com/docs/82379/2607689?lang=zh) / [Seedance 2.0](https://docs.volcengine.com/docs/82379/2222480?lang=zh) before changing limits. Wan reference pages: [Wan 3.0](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference), [Wan 2.7](https://help.aliyun.com/zh/model-studio/wan-video-to-video-api-reference).
- **Mention keyboard/removal behavior needs a fresh UI reproduction.** The current implementation uses `prompt-area` and explicit reference lists, so older reports about double `@`, invisible defaults, or missing arrow-key selection are not proof that the same bug remains. The source-verified preview/frame inconsistencies above are separate.

Email is already optional at registration; Wan 2.7 models already exist in the catalog; speaker inference from `角色：台词` is already implemented. Do not re-add these as unimplemented features.

## Deliberate non-goals

Do not unify existing string/integer ID styles, replace the native Gemini image SDK merely for uniformity, or invent a general framework for the one concrete sidebar. LangGraph remains an option for future checkpointed model decisions; deterministic media work belongs with durable jobs.
