# Error handling

Verified on **2026-09-07**. The [error inventory](../reference/error-codes.md) lists common messages; [Bug history index](../bugs/README.md) is the first stop for a bug: match its summary, then read the linked root cause and regression record.

## HTTP envelope

`app/main.py` registers three handlers:

| Exception | HTTP result |
|---|---|
| `HTTPException` | Raised status, `{"error": exc.detail}` |
| `RequestValidationError` | 422, `{"error": "field: message; ..."}` |
| Unhandled `Exception` | 500, `{"error": "internal server error"}` |

The validation formatter removes `body`/`query`/`path` from field locations. Use short condition-based messages for new HTTP exceptions, and do not let a provider payload or secret leak into them. Legacy dict-body routes validate manually; only typed request models provide `extra="forbid"` and schema-derived constraints.

## Choosing a status

| Code | Current use |
|---|---|
| 400 | Invalid values/state, missing script/model/reference, unknown invitation code |
| 401 | Missing/invalid JWT, missing user, bad login credentials |
| 402 | Non-admin official-model call with no balance |
| 403 | Disabled user, wrong owner, super-admin-only action |
| 404 | Missing or inaccessible row/artifact |
| 409 | Busy project, duplicate account, used code, invalid job transition |
| 410 | Expired invitation/redemption code |
| 422 | Typed body/query validation failure |
| 429 | Email verification-code cooldown |
| 500 | Unhandled request error or local infrastructure failure |
| 502 | Request-scoped provider failure |

## Rules

1. Validate shape/ranges at the edge and shared domain rules in services. Do not relax typed request validation to hide a misspelled field.
2. Prove ownership for every project-scoped operation. A 404 instead of 403 is appropriate when confirming existence would leak data.
3. Wrap request-scoped provider failures as 502 with bounded detail. Truncation is not redaction; never return raw model output, keys, signed URLs, or user content just because it is short.
4. Keep partial success as state. A batch with some successful shots is not equivalent to a fully failed batch; do not discard finished media.
5. Distinguish reference identity failure from a missing file: an unavailable explicitly selected reference is a 400; render helpers may skip an unreadable already-resolved local image and log the degraded decision.
6. Preserve the original failure if diagnostic persistence fails. `record_http_error` is best-effort and must not replace a provider/validation response.

## Streaming and background work

A 202 only means the work started/enqueued. Generation jobs fail through `status`, `errorCode`, and `errorMessage`; frame/clip runs write per-shot errors and terminal project/episode state; export jobs have their own status/error. Do not interpret those as a new HTTP 502 from the original request.

Chat may already have returned HTTP 200 when a provider fails. The backend then emits an NDJSON `error`, and the BFF translates it to an AI SDK stream error. Neither this nor a later background failure automatically becomes an HTTP error-log row.

Cancellation is separate from failure. The frontend recognizes both axios cancellation and `JobCanceledError` with `job-actions.isCanceled`; registered project task cleanup is described in [data flow](../architecture/data-flow.md#9-stop-and-restart-behavior).

## Frontend surfacing

`src/lib/http/errors.ts::resolveRequestError(error, fallback)` reads `data.error`, tolerates a raw FastAPI `detail` array, then falls back to the error message/localized fallback. Pass a fallback from `useI18n()`.

The shared axios response interceptor logs out on 401. Chat streaming has its own transport/error path; preserve both boundaries. Admin mutations generally use the global toast; the workbench/episode surfaces also keep local message state. Follow the existing surface and avoid duplicate error displays.

## Diagnosis

Request middleware creates a `req_*` ID and attaches `X-Request-Id` to responses passing through it. HTTP exception handlers attempt to store 5xx diagnosis in `error_logs`: route template, method, status/code, sanitized message, and available user/project/episode IDs. The table is not a general application-event archive. Only super admins can query it through `/api/admin/error-logs` or the chat diagnostic tool.

Start a bug investigation with the [history index](../bugs/README.md), then matching details and current incident evidence. After a fix, update its detail and index row. See [logging](logging.md) for permitted content and [backlog](../plans/backlog.md) for known places that still violate those rules.
