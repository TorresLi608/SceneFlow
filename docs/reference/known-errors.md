# Known Errors

This is the regression index for failures that reached a user or cost a meaningful debugging session. It is not a dump of every transient provider outage; it records the stable failure mode, its ownership, and the smallest check that prevents it returning.

## Workflow

1. Start with **Admin -> Error logs** or `GET /api/admin/error-logs`, using the response's `X-Request-Id`, project ID, route, or error code.
2. Confirm whether the incident matches an entry below before editing production code.
3. Fix the shared owner, not the endpoint that happened to surface it.
4. Add the smallest regression sample to the owning test file, then update this page if the failure mode is new.

The chat assistant receives a read-only `search_error_logs` tool only in a super-admin session. It must inspect those redacted records before proposing a production fix.

## Entries

### `BREAKDOWN_INVALID_JSON`

| Field | Value |
|---|---|
| Surface | `POST /api/projects/:projectId/episodes/:episodeId/breakdown` |
| Owner | `backend/app/llms/router.py::_json_breakdown_payload` |
| Symptom | `502 failed to break down script: response did not contain a JSON object` |
| Cause | Different models and OpenAI-compatible relays may return a JSON object, a bare shot array, Markdown-wrapped JSON, a truncated response, or JSON serialized once or twice as text. |
| Fix | Scan JSON values, accept the documented object or a bare array, and JSON-decode at most two enclosing text layers before recovery. |
| Regression | `backend/tests/test_agent_service.py`: bare array, single/double encoded quotes, quoted dialogue, and truncated array. |
| Privacy rule | Never put raw model output in the response, database error record, or normal application log. |

The parser intentionally does not try to repair arbitrary malformed JSON. A structurally invalid response is recorded as `BREAKDOWN_INVALID_JSON`; use the request ID to inspect the redacted failure and retry or change the provider configuration.
