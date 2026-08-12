# Feature: search and filtering

> **Naming note.** This file keeps the harness's template filename. SceneFlow has no unified search product — no index, no full-text engine, no cross-entity query. What exists is a set of list-filtering surfaces, documented here so new ones follow the same shape.

## Two strategies, chosen by list size

| Strategy | When | Examples |
|---|---|---|
| **Server-side**: `WHERE … LIKE` + `LIMIT/OFFSET` pagination | The list is unbounded and grows with usage | admin usage logs, invitation codes, redemption codes |
| **Client-side**: fetch once, filter in memory | The list is bounded and already loaded for other reasons | project list, admin user list, model config list |

Pick server-side the moment a table can grow without bound. Usage logs went to server-side pagination precisely because they accumulate per API call.

## Server-side surfaces

| Endpoint | Filters | Page size |
|---|---|---|
| `GET /api/admin/usage-logs` | `search` (username `LIKE`), `page`, `pageSize` | default 20, max 100 |
| `GET /api/admin/invitation-codes` | `status` ∈ `all\|unused\|used\|expired`, `search` (redeeming username), `page`, `pageSize` | default 10, max 100 |
| `GET /api/admin/redemption-codes` | `status`, `page`, `pageSize` | default 10, max 100 |
| `GET /api/usage/logs` (per-user) | `feature`, `days` (clamped 1–365), `source` | capped at 500 rows, no paging |

Established shape for a paginated endpoint:

- Query params are `Annotated[...]` with constraints so they land in the OpenAPI schema: `Query(max_length=64)`, `Query(ge=1)`, `Query(alias="pageSize", ge=1, le=100)`. **The alias is how camelCase reaches a snake_case parameter** — FastAPI query params do not go through `CamelModel`.
- Build a `conditions` list, then apply it to **both** the `func.count()` query and the page query so the total matches the filter.
- Return `{"items": [...], "pagination": {"total": n, "page": p, "pageSize": s}}`.
- Status filters that depend on time compute one `stamp = now()` and compare ISO strings — `expired` is "not used **and** `expires_at <= stamp`", so an unused-but-expired code never appears under `unused`.
- Joins to the user table use `aliased(User)` when the same table is needed twice (the redeeming user and the creating user).

## Client-side surfaces

- **Project list** (`ai-script/page.tsx`): free-text query over the title plus a status filter (`all` + the seven project statuses), with a "clear filters" affordance when either is active.
- **Admin users** (`admin/users/_components/user-list.ts`): combined username search, role filter, and status filter. The filtering logic lives in a **plain `.ts` module, not the component**, because that is what makes it testable — `user-list.test.mts` covers the combined case. Follow this split for any non-trivial client-side filter.

## Rules when adding a filter

1. **`LIKE '%term%'` is what this codebase uses.** It is not indexed and it is case-sensitive on SQLite for non-ASCII. Acceptable at current scale; if you need more, say so rather than quietly adding an index that changes write cost.
2. **Cap the input.** Every search param is `max_length=64`. Keep that.
3. **Filter and count with the same conditions.** A total that ignores the filter makes the pager lie.
4. **Never filter across users.** Admin endpoints depend on `current_super_admin_id`; per-user endpoints always add `user_id == current_user`. A filter is not an authorisation boundary.
5. **Soft-deleted rows stay out.** Every list adds `deleted_at IS NULL` (or the entity's equivalent) before anything else.
6. **Key the React Query cache by the filter**, using a parameterised key from `src/actions/query-keys.ts` — e.g. `adminUsageLogs(search, page)`. Never reuse one key across different filter values.
7. **Debounce text input** before it becomes a query key, so typing does not fire a request per keystroke.

## Known gaps

- No search over the domain content itself: scripts, shots, characters, and chat messages are not searchable.
- No sort controls — every list has one fixed order (usually `created_at DESC`).
- Client-side filters do not paginate, so they assume the full list fits in one response. The project list will need server-side paging before a user has many hundreds of series.
