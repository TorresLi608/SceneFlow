# Error handling

## The envelope

Every error response from this backend is `{"error": "<message>"}`. Two exception handlers in `app/main.py` guarantee it:

- `HTTPException` → `{"error": exc.detail}` at the raised status.
- `RequestValidationError` → **422** with pydantic's error list flattened into one readable sentence. Without this handler, rejected bodies would come back as `{"detail": [...]}` while every other error is `{"error": "..."}`, leaving the client two shapes to parse. The flattener drops the `body`/`query`/`path` prefix from `loc` because it tells the user nothing.

Raise `HTTPException(status, "lowercase message")` from endpoints and services alike. Messages are short, lowercase, and describe the condition, not the fix: `"episode not found"`, `"project is busy, cannot delete an episode right now"`.

## Choosing a status

| Code | Use for | Example in this codebase |
|---|---|---|
| `400` | The request is well-formed but the values are wrong or the state does not allow it | `"no fields to update"`, `"no scenes available, parse script first"` |
| `401` | Missing, invalid, or unresolvable credentials | `"missing token"`, `"invalid token"` |
| `402` | Out of balance on an official model | `"当前余额不足，请先兑换额度后再使用官方模型。"` |
| `403` | Authenticated but not permitted, including cross-user access | `"project does not belong to current user"`, `"superAdmin required"` |
| `404` | The row does not exist, or is soft-deleted, or belongs to someone else and we do not want to confirm it exists | `"scene not found"` |
| `409` | A conflict with current state that the client can resolve by retrying differently | `"username already exists"`, `"character is locked, unlock it before regenerating the portrait"` |
| `410` | Existed, expired | `"invitation code expired"` |
| `422` | Body/query failed schema validation — raised by the framework, not by hand | unknown field, wrong type |
| `502` | A provider call failed; the message carries the provider's text | `"failed to parse script: …"` |

The full inventory is in `../reference/error-codes.md`.

## Rules

1. **Validate at the edge, decide in the service.** Range checks live on the Pydantic request model so they appear in the OpenAPI schema; cross-field consistency and defaults resolve in one service function (`project_service.production_settings` is the reference example).
2. **`extra="forbid"` is load-bearing.** A misspelled field must fail rather than no-op. Do not relax it per-model to make a client easier to write.
3. **Ownership checks are not optional.** Every project-scoped endpoint resolves the row for the current user; returning `404` rather than `403` is acceptable when confirming existence would leak.
4. **Provider failures become `502`, never `500`.** Wrap the call, keep the provider's message, truncate it (`ERROR_DETAIL_CHARS`) before it reaches a row or a log.
5. **Partial success is a state, not an error.** A generation run that renders some shots ends `partial` with per-shot errors recorded — do not collapse it to `failed`.
6. **Degrade where the user keeps more by continuing.** A missing reference portrait is skipped so the shot still renders; an unreadable stored artifact is dropped rather than 500-ing the whole response. Log it at `info`, do not swallow it silently.
7. **Never leak a secret in a message.** No API keys, no decrypted values, no full base URLs with credentials.

## Frontend surfacing

`src/lib/http/errors.ts` → `resolveRequestError(error, fallback)` is the single place that turns an axios failure into a string. It reads `data.error`, tolerates a raw FastAPI `detail` array (a proxy or a route without the handler can still produce one), falls back to `error.message`, then to the caller's localized fallback. **Always pass a localized fallback from `useI18n()`** — never a hardcoded English string.

A `401` anywhere triggers `useUserStore.getState().logout()` in the shared axios response interceptor. Do not add per-call 401 handling.

Surface errors through the global toast (`src/components/ui/toast.tsx`) rather than inline status text; inline messages were deliberately replaced by toasts across the admin surfaces.

## Backend logging on error

See `logging.md`. Short version: log the *decision* you made and enough identity to find the row (`scene=%s`, `character=%s`), never the payload.
