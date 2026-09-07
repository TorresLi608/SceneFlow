# Error codes and outcomes

Verified on **2026-09-07**. HTTP errors use `{"error": "<message>"}`; see [error handling](../conventions/error-handling.md). This is a curated navigation aid for common failures, not an exhaustive generated list of every provider message. [OpenAPI](api-spec.yaml) records HTTP paths and typed input constraints.

## HTTP failures

| Status | Representative message / condition | Owner |
|---|---|---|
| 400 | `script is required`; `detailPrompt is required when detailLevel is custom`; `no shots to annotate, split the script into shots first` | `api/v1/episodes.py` |
| 400 | `sceneIds must belong to the selected episode`; `unlock selected shots before generating them`; `every selected shot is already rendered, nothing to retry` | `services/project_service.py::selected_scenes` |
| 400 | `generate the storyboard image before generating its video` | Project `/generate-video` endpoint, including text-to-video-capable models |
| 400 | `selected reference is unavailable`; `image prompts only accept image references` | `reference_service.py`, project/episode endpoints |
| 400 | `selected video model does not accept audio, turn withAudio off`; `merge the project's voices before rendering with audio` | Explicit video audio request |
| 400 | `invalid invitation code`; email/code missing counterpart; invalid username/password length | `api/v1/auth.py` |
| 400 | `baseUrl must not target a private network`; `stored API key cannot be decrypted`; unsupported model/capability options | `config_service.py`, settings/media validation |
| 400 | `no fields to update` | PATCH endpoints where no applicable field was sent |
| 401 | `missing token`; `invalid token`; `user not found`; `invalid credentials` | `api/deps.py`, auth |
| 402 | `当前余额不足，请先兑换额度后再使用官方模型。` | `usage_service.require_model_balance`, official config and non-super-admin |
| 403 | `user is disabled`; `superAdmin required`; `project does not belong to current user` | Auth/ownership dependencies and services |
| 404 | `project not found`; `episode not found`; `scene not found`; `config not found`; `export not found` | Owning endpoint/service |
| 409 | `username already exists`; invitation/redemption already used; project busy; illegal job transition; `job has reached its retry limit` | Auth, admin, project/job services |
| 410 | `invitation code expired`; `redemption code expired` | Registration/redemption |
| 422 | Unknown typed field, wrong type, range violation → `field: message; ...` | `CamelModel` / FastAPI / `validation_message` |
| 429 | `验证码发送过于频繁，请等待 60 秒后再试` | `verification_service.send_registration_code` |
| 500 | `internal server error`; `邮件发送失败，请稍后重试` | Unhandled exceptions / SMTP failure |
| 502 | `failed to parse script: …`; `failed to break down script: …`; `failed to optimize prompt: …`; request-scoped media failure | Provider boundary |

Body validation is not uniform across the whole API: typed workbench requests forbid extra fields, while older auth/settings/chat/standalone-media dict payloads validate manually. Check the endpoint before interpreting a missing 422 as success.

## Diagnostic codes

HTTP 5xx handlers call `error_log_service.error_code_for` and attempt to persist a redacted record. Search by request ID, project, route, or error code at `/api/admin/error-logs`.

| Code | Current classification |
|---|---|
| `BREAKDOWN_INVALID_JSON` | 502 breakdown failure whose detail includes `json object` |
| `BREAKDOWN_FAILED` | Other 502 breakdown failure |
| `PROVIDER_FAILURE` | Other HTTP 502 |
| `INTERNAL_ERROR` | Other HTTP 5xx / unhandled exception |

These are log classifications, not extra fields added to every HTTP error body. Middleware supplies `X-Request-Id` on responses passing through it. Start with the [Bug history index](../bugs/README.md) to find the JSON parser record. See [logging](../conventions/logging.md) for privacy rules.

## Background and stream failures

- A generation job settles as `failed` with `errorCode`/`errorMessage`; paid work whose worker lease expires uses `WORKER_LOST` and is not automatically retried. `JobFailedError` exposes the terminal row on the frontend.
- A canceled job settles as `canceled` and becomes `JobCanceledError`, not a failed provider request.
- Image/video run failures are stored on the shot and summarized by project/episode status; export failures are stored in `export_jobs`.
- Chat errors after the stream begins are NDJSON/UI-stream events. They do not change the already-sent HTTP status or automatically create HTTP error-log rows.

## Non-error outcomes

| Signal | Meaning |
|---|---|
| Breakdown `applied: false`, `discardsScenes`, `discardsGeneratedScenes`, existing `scenes` | Replacing existing shots needs confirmation, even without generated media. Repeat with `replaceAll: true` after consent. |
| Legacy parse `applied: false`, `discardsGeneratedScenes`, `pendingScenes` | The older parser has a different replacement-confirmation payload. |
| HTTP 202 with `{job}` | Work is queued, not complete; inspect the terminal job. |
| HTTP 202 with project/episode status or `{export}` | An in-process background task was started; this is not a generation-worker job. |
| Project/episode `partial` | Some eligible media succeeded; inspect individual shots for the remainder. |
| Project/episode `failed` | The run did not complete successfully; startup also uses this for abandoned runs while preserving earlier media. |
| Project cancel `{canceled: false}` | No registered task was found; normal idempotent stop result. |

## Verify after changing behavior

```bash
cd backend
rg -n 'raise HTTPException\(' app/api app/services
```

Update the matching [Bug history record and index](../bugs/README.md) for every fix. Check the owning tests and [regenerate OpenAPI](../conventions/README.md#keeping-generated-docs-current). Keep provider text bounded, but do not confuse truncation with redaction.
