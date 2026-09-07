# Feature: search and filtering

Verified on **2026-09-07**. SceneFlow has list filters, not a unified full-text or cross-entity search engine. The [code map](../architecture/code-map.md) locates the pages/actions that own each surface.

## Server-side lists

| Endpoint | Filters | Page size |
|---|---|---|
| `GET /api/admin/usage-logs` | Username `search`, `page`, `pageSize` | Default 20, max 100 |
| `GET /api/admin/error-logs` | `search` across route/message/request/code/project, exact `errorCode`, `projectId`, `requestId` | Default 20, max 100 |
| `GET /api/admin/invitation-codes` | `status`, redeeming username `search`, page | Default 10, max 100 |
| `GET /api/admin/redemption-codes` | `status`, page | Default 10, max 100 |
| `GET /api/usage/logs` | Per-user `feature`, `days` (1–365), `source` | Capped at 500, no paging |
| `GET /api/projects/:id/assets` | Media `kind` | No paging |

Admin list endpoints depend on `current_super_admin_id`; the shared `find_error_logs` service is also used by the super-admin chat tool. Conditions must be applied to both count and page queries.

Paginated responses have an entity-specific collection key (`usageLogs`, `errorLogs`, `invitationCodes`, `redemptionCodes`) plus `pagination: {total, page, pageSize}`. Do not assume a common `items` key. Query aliases are explicit (`Query(alias="pageSize")`), independent of `CamelModel`.

Search bounds are endpoint-specific: usage/invitation search is capped at 64 characters, error-log search at 128, with its exact ID/code filters separately bounded. ISO timestamp status comparisons use one `now()` value so unused/expired categories agree.

## Client-side lists

- The project list at `/ai-script` fetches the user's projects and filters title/status in memory.
- Admin user filtering combines username, role, and status in `admin/users/_components/user-list.ts`; its `.test.mts` exercises the pure function.
- Model pickers and the episode reference/asset selectors filter already-loaded options locally.

Use local filtering for small lists already loaded for editing. Move growing tables to server-side filtering/paging when the full response becomes unsuitable.

## Rules and limits

- SQL `LIKE '%term%'` is the current text-search mechanism. It is not full-text search; leading wildcards do not benefit from an ordinary prefix index.
- A filter is not authorization. Always constrain per-user/project reads and preserve super-admin dependencies.
- Domain lists exclude soft-deleted rows; historical usage/error records have audit semantics and need not disappear with a deleted domain row.
- Put filter-sensitive cache identities in `actions/query-keys.ts`, for example `adminUsageLogs(search, page)` and `adminErrorLogs(search, page)`.
- Current error-log search uses the typed text directly as a query key; debouncing is not implemented there. Add it if request volume/typing behavior warrants it, rather than documenting it as existing behavior.

## Known gaps

No search over script text, shots, characters, or chat messages; no user-facing server-side sort contract; no server-side project paging. Client filters assume the fetched list fits in memory. See [backlog](../plans/backlog.md).
