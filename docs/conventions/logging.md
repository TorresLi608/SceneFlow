# Logging

Verified on **2026-09-07**. These are the logging rules to preserve; known source violations are recorded in the [backlog](../plans/backlog.md).

## Setup

`app/core/logging.py` installs one stream handler at startup from the `lifespan` hook. Request middleware creates a server-generated `req_*` ID, includes it in the log context, and returns `X-Request-Id` on responses that pass through it:

```
%(asctime)s %(levelname)s %(name)s request=%(request_id)s %(message)s
```

`force=True` replaces whatever uvicorn installed, so application records and access logs share one format instead of appearing twice. Level comes from `SCENEFLOW_LOG_LEVEL` (default `INFO`).

Get a logger per module, never the root logger:

```python
logger = logging.getLogger(__name__)
```

## Style

**Lazy `%s` formatting with `key=value` identity fields.** This is the established shape:

```python
logger.warning("scene image generation failed project=%s scene=%s: %s", project_id, scene_id, detail)
logger.info("skipping unreadable reference portrait character=%s", character.get("id"))
```

- Pass arguments to the logger; do not pre-format with f-strings. A suppressed record should cost nothing.
- Lead with what happened in plain words, then the identifiers needed to find the row.
- Include the IDs a reader would need to grep: `project=`, `scene=`, `character=`, `job=`.
- Bound provider diagnostics (`ERROR_DETAIL_CHARS` is 220 in `generation_service.py`) and remove sensitive/user content first. Truncation alone is not redaction.

## Levels

| Level | Use for | Example |
|---|---|---|
| `info` | A decision the system made that a reader would otherwise find inexplicable | skipping an unreadable reference portrait; a run's terminal summary |
| `warning` | A real failure that was contained — the request or run continues degraded | a shot's image or audio failed; portrait generation failed; parse/optimize failed |
| `error` | Unhandled/infrastructure failure | `logger.exception` in the unhandled request handler; SMTP failure |
| `debug` | Local diagnosis only | must not be required to understand production behaviour |

A failure that is already returned to the user as a `4xx` does not also need a log line. Log what the **user cannot see**: background work, degraded paths, and swallowed exceptions.

## Never log

- **API keys, decrypted values, or JWTs.** Keys are AES-GCM encrypted at rest; a log line would undo that.
- **Passwords or password hashes.**
- **Signed artifact URLs** — they are bearer credentials for 30 days.
- **Full request bodies or script text.** Scripts are user content and can be long; log the project/episode ID instead.
- **Chat message content.** Log session and message IDs.

## Background work

Generation can run in a request, an attached asyncio task, or the queue worker. Log identity and lifecycle decisions; also inspect persisted job/scene/export errors and status. Those rows and broadcasts are separate from HTTP error-log records. Cancellation cleanup and restart recovery should be distinguishable from provider failure.

## Request failures

The HTTP exception handlers attempt to persist `5xx` diagnosis in SQLite's `error_logs` table. This write is best-effort and must not replace the original response. These are **diagnostic pointers**, not an application event archive: `requestId`, route template, method, status, stable error code, redacted message, and available user/project/episode IDs only. The intended record contains no request body, script/chat content, provider output, key, or signed URL. `record_http_error` retains the operation before provider detail; preserve that boundary when introducing error messages. Errors emitted after a stream begins, and later job/render/export failures, do not automatically create rows here.

Super admins can inspect the records at **Admin -> Error logs** or `GET /api/admin/error-logs`. Search by request ID first; otherwise use route, project ID, or error code. The assistant receives the same read-only lookup in a super-admin chat. Read the [Bug history index](../bugs/README.md) first and open matching details before inspecting incident-specific logs or changing a shared parser/provider boundary. After the fix, update both the issue record and index with actual regression evidence.

## Frontend

There is no logging framework and no log sink. Do not add `console.log` to shipped paths; surface problems through `resolveRequestError` and the page's existing toast/local-message pattern. `console.error` is acceptable in an error boundary or a stream `onError` handler where the user already sees a message.
