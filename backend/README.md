# SceneFlow Backend (Phase 4)

## Run

```bash
cd backend
go run .
```

## Optional env

- `PORT` (default `8080`)
- `SCENEFLOW_DB_PATH` (default `./sceneflow.db`)
- `SCENEFLOW_JWT_SECRET` (default `dev-jwt-secret-change-me`)
- `SCENEFLOW_AES_KEY` (default `dev-aes-key-change-me`, internally SHA-256 -> 32 bytes)

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

- Password is stored by bcrypt hash.
- Provider API keys are encrypted by AES-256-GCM before persisting.
- Parse flow tries active provider LLM first; if missing/failed, a local fallback parser is used.
- Generate flow streams per-scene progress events over WebSocket (`SCENE_UPDATE`).
