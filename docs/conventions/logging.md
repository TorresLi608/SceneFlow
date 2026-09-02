# Logging

## Setup

`app/core/logging.py` installs one stream handler at startup from the `lifespan` hook. Each HTTP request has a server-generated `req_*` ID that is present in the log format and returned as `X-Request-Id`:

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
- Truncate provider text before logging it (`ERROR_DETAIL_CHARS` is 220 in `generation_service.py`) — provider errors can carry an entire response body.

## Levels

| Level | Use for | Example |
|---|---|---|
| `info` | A decision the system made that a reader would otherwise find inexplicable | skipping an unreadable reference portrait; a run's terminal summary |
| `warning` | A real failure that was contained — the request or run continues degraded | a shot's image or audio failed; portrait generation failed; parse/optimize failed |
| `error` | Something that needs attention and was not contained | reserve it; the codebase currently prefers `warning` + a `502` to the caller |
| `debug` | Local diagnosis only | must not be required to understand production behaviour |

A failure that is already returned to the user as a `4xx` does not also need a log line. Log what the **user cannot see**: background work, degraded paths, and swallowed exceptions.

## Never log

- **API keys, decrypted values, or JWTs.** Keys are AES-GCM encrypted at rest; a log line would undo that.
- **Passwords or password hashes.**
- **Signed artifact URLs** — they are bearer credentials for 30 days.
- **Full request bodies or script text.** Scripts are user content and can be long; log the project/episode ID instead.
- **Chat message content.** Log session and message IDs.

## Background work

Generation runs in a background task, so its log lines are the only trace a developer has. Keep the run's start, per-shot failures, and the terminal outcome (`done`/`partial`/`failed`) logged with the project and episode IDs — a `partial` result is otherwise hard to explain after the fact.

## Request failures

The HTTP exception handlers persist every `5xx` in SQLite's `error_logs` table. These are **diagnostic pointers**, not an application event archive: `requestId`, route template, method, status, stable error code, redacted message, and available user/project/episode IDs only. The table never stores request bodies, scripts, chat messages, provider output, keys, or signed URLs.

Super admins can inspect the records at **Admin -> Error logs** or `GET /api/admin/error-logs`. Search by request ID first; otherwise use route, project ID, or error code. The assistant receives the same read-only lookup in a super-admin chat. Match recurring cases against `../reference/known-errors.md` and add a regression sample before changing a shared parser or provider boundary.

## Frontend

There is no logging framework and no log sink. Do not add `console.log` to shipped paths; surface problems through the global toast and `resolveRequestError`. `console.error` is acceptable in an error boundary or a stream `onError` handler where the user already sees a message.
