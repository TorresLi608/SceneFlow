# SceneFlow Backend

## Run

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8080
```

## Optional env

- `PORT` (default `8080`)
- `SCENEFLOW_DB_PATH` (default `./sceneflow.db`)
- `SCENEFLOW_JWT_SECRET` (default `dev-jwt-secret-change-me`)
- `SCENEFLOW_AES_KEY` (default `dev-aes-key-change-me`, internally SHA-256 -> 32 bytes)
- `SCENEFLOW_PUBLIC_BASE_URL` (default `http://127.0.0.1:8080`)
- `SCENEFLOW_GENERATED_DIR` (default `./generated`)

## Super admin

- Startup seeds `superAdmin` / `superAdmin@123` with role `superAdmin`.
- Disabled users cannot log in or use existing tokens.

## Model routing

- `model.py` owns LLM provider switching.
- Chat models use LangChain adapters. OpenAI-compatible providers share `ChatOpenAI(base_url=...)`; Anthropic uses `ChatAnthropic`.
- Chat context assembly uses LangGraph: SQLite history -> 1M-token budget check -> old-context summary compression -> model messages.
- Supported script/chat providers: `qwen`, `doubao`, `deepseek`, `openai`, `gemini`, `anthropic`, and `custom`.
- Image generation currently supports OpenAI Images.

## APIs

### Auth
- `POST /api/auth/register`
- `POST /api/auth/login`

### User (JWT required)
- `GET /api/users/me`
- `PATCH /api/users/me`
- `DELETE /api/users/me`

### UserConfig (JWT required)
- `POST /api/settings/keys`
- `GET /api/settings/keys`
- `GET /api/settings/keys/:id`
- `PATCH /api/settings/keys/:id`
- `DELETE /api/settings/keys/:id`
- `POST /api/settings/official/:id/activate`

### Admin (superAdmin required)
- `GET /api/admin/users`
- `PATCH /api/admin/users/:id`
- `DELETE /api/admin/users/:id`
- `GET /api/admin/default-models`
- `POST /api/admin/default-models`
- `PATCH /api/admin/default-models/:id`
- `DELETE /api/admin/default-models/:id`

Official script configs support OpenAI-compatible relays by setting `provider: "custom"`,
`modelSeries`, and `baseUrl` such as `https://www.juaiapi.com/v1`.

### Project Parse (JWT required)
- `POST /api/projects/:id/parse`
  - request body: `{ "script": "...", "model": "gpt-4o" }`
  - parses script to scenes and persists to DB

### Project Generate (JWT required)
- `POST /api/projects/:id/generate`
  - request body: `{ "model": "gpt-4o" }` (optional)
  - starts goroutine-based concurrent image/audio generation simulation

### WebSocket
- `GET /ws/projects/:id?token=<JWT>`
  - heartbeat enabled
  - project-scoped broadcast stream
  - event types include `WS_CONNECTED`, `PROJECT_UPDATE`, `SCENE_UPDATE`

## Notes

- Passwords are stored by bcrypt hash.
- Provider API keys are encrypted by AES-256-GCM before persisting.
- Existing SQLite data is kept compatible with the old GORM table names and columns.
- Generate flow streams per-scene progress events over WebSocket (`SCENE_UPDATE`).
