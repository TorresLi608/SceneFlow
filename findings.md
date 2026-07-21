# Findings & Decisions

## Session 2026-07-21: Admin User Role Selection

- User creation now accepts only `user` or `superAdmin`; omitted role defaults to `user`.
- The management form exposes a role select defaulting to ordinary user and resets to that default after success.
- Regression checks cover the default role, super-admin creation, and rejection of unknown roles.

## Session 2026-07-21: Admin All Usage Records

- Added a super-admin-only paginated usage-log endpoint joining `usage_logs` with `users`.
- Username search uses a parameterized SQLite `LIKE '%term%'` match.
- Reused the existing usage serializer, table, money formatter, pagination, and permission patterns.
- Added `/admin/usage-logs` with username search, clear filter, model/source/token/cost columns, and pagination.
- Backend self-check covers fuzzy username matching and page boundaries.

## Session 2026-07-21: Balance Enforcement and Usage Audit

### Requirements

- Audit today's frontend/backend changes and self-test the business flow.
- Ordinary users using official model configurations must be blocked when balance is insufficient and receive a clear message.
- Personal model configurations remain usable without balance, but usage and estimated cost must still be recorded.
- Usage logs need an all/official/personal source filter, defaulting to all.
- Redeeming a code must refresh globally consumed balance data without introducing a state machine unless the existing store genuinely needs one.
- New users default to level 1.
- List status filters must have an obvious clear/reset path.
- Fix unreasonable design discovered in scope and record changes for future handoff.
- Reorganize the backend so tests and service modules have clear homes, following common FastAPI/open-source conventions without a cosmetic full rewrite.

### Initial Decisions

| Decision | Rationale |
|----------|-----------|
| Reuse the existing Zustand user store and React Query `me` cache | Balance is server-owned account data; a new state machine would duplicate existing state and add synchronization risk. |
| Enforce official-model balance on the backend before provider calls | The backend is the trust boundary and prevents bypass from any client. |
| Keep personal-model cost as usage accounting only | Matches the requirement: record estimated cost without deducting or blocking personal configuration usage. |
| Add the smallest focused regression checks | Money and authorization paths require executable coverage; avoid a new test framework. |
| Treat personal usage as token/quantity accounting, not currency estimation | Personal configs define no pricing. Inventing a monetary price would be misleading; source, tokens, quantity, and duration remain visible and filterable. |
| Reorganize tests and services only | These are real existing categories; moving every root module into invented layers would create churn without improving the current product. |

### Research Findings

- Existing planning files predate this session; this session is appended instead of overwriting them.
- `findings.md` was missing from the current workspace even though older logs referenced it, so it was recreated for this audit.
- Current `record_usage` deducts official cost only after the provider call and clamps balance at zero; there is no preflight guard, so a zero-balance ordinary user can currently call an official model.
- Personal configurations already record source, provider, model, duration, tokens, cache tokens, quantity, and unit metadata. Their monetary `costMicros` is zero because personal configurations have no pricing fields; they are counted but not billed.
- Official execution is resolved through two paths: shared helpers in `config_service.py` for image/video/project flows, and separate chat-session resolution in `chat_service.py`. A fix must cover both paths.
- Actual provider cost is only known after completion. The requested no-balance rule therefore maps to a preflight `balance_micros > 0`; final official cost remains deducted after usage is known.
- `MAX(0, balance-cost)` prevents negative stored balances but does not reserve credit across concurrent calls. Reservation is deferred unless concurrent overspend becomes a measured problem.
- Frontend redemption already updates both the global Zustand user and React Query `me` cache immediately. Adding a state machine would duplicate working state ownership, so no state-machine change is needed.
- The app's custom HTTPException handler returns `response.data.error`, so the current insufficient-balance message is already readable. `resolveRequestError` now also accepts FastAPI's default `detail` shape for robustness in tests or deployments without the custom handler.
- Usage API currently filters only by feature and days. Source is already stored as `official` or `user`, so adding a SQL condition and one query parameter is sufficient.
- Admin user creation currently relies on the backend default and does not show/send a level. The form should expose level with state initialized/reset to 1.
- User, invitation, redemption, and usage filter UIs include an `all` option but no one-click reset. Add a reset button only when filters differ from defaults (or search is non-empty).
- The balance guard should be a small shared `require_model_balance(conn, user_id, config)` policy in `usage_service.py`, invoked immediately before actual provider work. It no-ops for personal configs and super admins, and raises HTTP 402 for ordinary users with `balance_micros <= 0` on official configs.
- Chat must run the guard inside `begin_chat_turn` before persisting the user's message; otherwise rejected requests would leave orphan user messages.
- Project parsing may mutate project status during preparation, so the exact guard placement must be before status changes or must restore state on rejection.
- Direct image/video, project parse/optimize/background image generation, chat text, and agent image tools are the provider-call boundaries requiring coverage.
- The backend root currently mixes 10 `test_*.py` files, eight `*_service.py` modules, infrastructure, API routers, and utilities.
- A focused structure is sufficient: move tests to `backend/tests/` and actual service modules to `backend/services/`; keep core runtime/infrastructure stable to avoid a high-risk package rewrite.
- No plugin subsystem exists in this backend, so creating a `plugins/` directory would be speculative and is intentionally skipped.
- Backend files were reorganized into `services/`, `lib/`, and `tests/`; a stdlib `tests/run_all.py` preserves the existing executable-assert test style without adding pytest.
- Post-move import scan found no stale flat service/lib imports. The full backend runner, Python compile check, frontend lint, and TypeScript check all pass after the reorganization.
- UI review confirmed reset controls appear only when active, creation level visibly defaults to 1, and usage source defaults to all.
- Broader filter audit found two remaining list pages without reset: model management and AI project list. The AI project page also had a nonfunctional “advanced filters” button; replace it with a real reset action instead of preserving dead UI.
- Final balance-call scan confirms the shared guard covers direct images/videos, project parse/optimize/generation, chat turns, agent image tools, and per-scene background generation.
- Added a chat-level regression check proving official zero-balance rejection occurs before saving the user message, while a personal configuration at zero balance still saves and proceeds.
- Added explicit checks for the insufficient-balance message and new-user default level 1.
- Final verification passes for all backend self-checks, backend app import, Python compilation, frontend lint, TypeScript, whitespace, and stale-import scan.
- A new state machine was not added: redemption already updates Zustand and React Query synchronously, which is the smaller correct global-state design.
- Personal model usage remains unbilled but fully logged by source/tokens/quantity/duration. Monetary estimation remains zero until personal configs have an explicit pricing model.
- Production build was not repeated because the repository log already records the environment's Google Fonts network failure; lint/type-check and app import cover the code changes without retrying a known external failure.

### Resources

- `backend/usage_service.py`
- `backend/routers/users.py`
- `frontend/src/store/user-store.ts`
- `frontend/src/app/(workspace)/usage/page.tsx`

### Issues Encountered

| Issue | Resolution |
|-------|------------|
| First findings update patch used section order different from the newly created file | Re-read the file and applied a targeted patch against its actual structure. |
| Architecture findings patch again assumed a different section position | Re-read the current file and patched each actual section independently. |
| Base UI Select `items` does not accept primitive arrays | Use explicit `{ value, label }` option objects. |
