# Error codes

Every error response is `{"error": "<message>"}` — see `../conventions/error-handling.md` for the two handlers that guarantee it. This page is the inventory; the wire contract for each endpoint is in `api-spec.yaml`.

## By status

### 400 — well-formed request, unusable values or state

| Message | Raised by |
|---|---|
| `no fields to update` | every PATCH with an empty body (10 sites) |
| `script is required` | project parse |
| `prompt is required` | image / video generation |
| `no scenes available, parse script first` | generate, export |
| `sceneIds must match the episode's current scenes` | scene reorder |
| `toEpisode must not be earlier than fromEpisode` | character variant range |
| `targetDurationMs must be between 10000 and 600000` | production settings |
| `width and height do not match aspectRatio` | production settings |
| `unsupported aspect ratio` | production settings |
| `<field> must be an integer` / `<field> must be between 256 and 4096` | production settings dimensions |
| `level must be 1, 2, or 3` | script optimize |
| `validity must be 1, 7, or 30 days` | invitation / redemption code creation |
| `username length must be between 3 and 64` | register, admin user create |
| `invalid username or password length` | register, password change |
| `apiKey length must be between 8 and 512` | model config write |
| `custom provider requires baseUrl` | model config write |
| `baseUrl must not target a private network` | model config write — SSRF guard |
| `invalid purpose` | model config write |
| `audio purpose only supports provider edge/system/openai/qwen` | model config write |
| `video purpose only supports provider doubao/gemini/qwen` | model config write |
| `video purpose requires modelSeries` | model config write |
| `image generation currently only supports provider openai/gemini/qwen` | image router |
| `disabled config cannot be default` | model config activate |
| `stored API key cannot be decrypted` | any config read whose ciphertext no longer decodes |
| `model validation failed: …` / `failed to fetch model list: …` | provider validation, provider text truncated to 180 chars |
| `unknown character for this project: …` | scene casting |
| `最多只能上传 N 个附件` | chat attachments |
| `<stage>未配置可用的默认模型。…` / `…缺少 API Key。` / `…当前默认模型尚未通过校验。` | stage has no usable model configuration |

### 401 — credentials

| Message | Meaning |
|---|---|
| `missing token` | no `Authorization` header |
| `invalid token` | undecodable or expired JWT |
| `user not found` | token decoded, user is gone or soft-deleted |
| `invalid credentials` | login failure — deliberately does not say which half was wrong |

### 402 — payment required

| Message | Meaning |
|---|---|
| `当前余额不足，请先兑换额度后再使用官方模型。` | official configuration, non-superAdmin, `balance_micros <= 0` |

### 403 — authenticated, not permitted

`user is disabled` · `superAdmin required` · `project does not belong to current user` · `chat session does not belong to current user` · `job does not belong to current user`

### 404 — absent, soft-deleted, or not yours

`user not found` · `project not found` · `episode not found` · `scene not found` · `character not found` · `character variant not found` · `chat session not found` · `config not found` · `official config not found` · `job not found` · `redemption code not found`

### 409 — conflict with current state

| Message | Resolution the client can take |
|---|---|
| `username already exists` | pick another name |
| `project is busy and cannot start <stage> right now` | wait for the run to finish |
| `project is busy, cannot delete an episode right now` | wait — a run holds those rows open |
| `character is locked, unlock it before regenerating the portrait` | unlock the card |
| `invitation code already used` / `is no longer available` | request another code |
| `redemption code already redeemed` / `is no longer available` | request another code |
| `only queued or running jobs can be canceled` | nothing to cancel |
| `only failed or canceled jobs can be retried` | nothing to retry |
| `job has reached its retry limit` | investigate the failure |

### 410 — existed, expired

`invitation code expired` · `redemption code expired`

### 422 — schema validation

Raised by FastAPI, never by hand. Produced by an unknown field (`extra="forbid"`), a wrong type, or a range violation on the request model. The handler in `app/main.py` flattens pydantic's list into `field: message; field: message`.

### 502 — provider failure

`failed to parse script: …` · `failed to optimize script: …` · `failed to chat: …` · `failed to generate portrait: …` · `AI 图片生成失败：…` · `AI 视频生成失败：…`

Provider text is truncated (180–220 chars) before it reaches the client or a log line.

## Application-level outcomes that are *not* errors

These come back `200`/`202` and must not be normalised into failures:

| Signal | Meaning |
|---|---|
| `applied: false` + `discardsGeneratedScenes: N` + `pendingScenes` | Re-parsing would destroy generated media. The client confirms, then repeats with `replaceAll: true`. |
| project/episode status `partial` | Some shots rendered, some failed. Per-shot errors are on the rows. |
| project/episode status `failed` | Nothing rendered. |

## Language

Messages are mostly lowercase English. A handful are Chinese, and they are the ones written to be read by an end user rather than a developer: the balance message, the missing-model-configuration messages, the attachment cap, and the two `AI …失败` provider errors. Keep that split — a new developer-facing message goes in English, a new end-user-facing one gets a localized string on the client where possible.

## Verifying this page

```bash
cd backend
grep -rhoE 'HTTPException\([0-9]{3}, f?"[^"]*"' app/ | sort -u
```

Regenerate `api-spec.yaml` with the command in `../conventions/README.md`.
