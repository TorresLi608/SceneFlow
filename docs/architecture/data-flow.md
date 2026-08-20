# Data flow

Four flows carry almost all of the product: parse, render, chat, and metering. Each is traced end to end below with the files that own each hop.

## 1. Script → shots (parse)

```
workbench ─▶ parseProjectAction ─▶ POST /api/projects/:id/parse
   ─▶ episode_service.resolve_episode ─▶ models.parse_script (LLM)
   ─▶ replace the episode's scenes ─▶ serialized project (one episode's shots)
```

- Body: `{ script, model, episodeId?, replaceAll? }`. Omitting `episodeId` targets the **current** episode, which is the highest-numbered live one.
- **Re-splitting is destructive.** If the target episode already has shots carrying a generated image or voice track, the response comes back `applied: false` with `discardsGeneratedScenes: N` and the parsed shots under `pendingScenes`. The client confirms with the user, then repeats the call with `replaceAll: true`. Do not silently overwrite.
- Shot `order` restarts at 1 within each episode, so the response carries one episode's shots — never the series merged together.

## 2. Shots → selected images (generate)

```
POST /api/projects/:id/generate  { sceneIds? }
   ─▶ claim_project_status  (conditional UPDATE; second click loses)
   ─▶ resolve episode + cast + production settings
   ─▶ asyncio.create_task(run_generation(...))     ← returns 202 immediately
        └─ per shot, ≤3 concurrent (MAX_CONCURRENT_SCENES):
             character references + image provider
             store_artifact()       ─▶ private_generated/<relative path>
             broadcast SCENE_UPDATE ─▶ ws://…/ws/projects/:id
   ─▶ terminal status: done | partial | failed, written to both project and episode
```

- The workbench's one-click storyboard action stops after parsing and filling shots. Images and video are explicit single-shot or multi-select actions. Image requires an active image configuration. Locked shots are skipped, and all-locked is a `400` rather than a silent no-op.
- A shot's cast contributes two things: **appearance prompts**, which work on every provider, and **reference portraits**, which are passed image-to-image and are what actually holds a face steady across episodes. At most `MAX_REFERENCE_IMAGES` (4) portraits per request, because providers cap reference images and a crowd scene would blow past it.
- A portrait whose file is missing is skipped rather than failing the shot: losing consistency is a smaller harm than losing the render.
- The terminal status reflects what actually landed. `partial` is a real outcome, not an error state to normalise away.

## 3. Shots -> generated clips (drama / motion comic)

```
POST /api/projects/:id/generate-video
   -> active video config + its declared capabilities
   -> current episode's unlocked shots, <=2 concurrent
        storyboard image -> first-frame reference when supported/required
        merged project timbre track -> reference audio when supported
        video provider -> store_artifact(projects/<id>/<scene>.mp4)
        broadcast SCENE_UPDATE -> videoStatus / videoProgress / videoUrl
   -> terminal project + episode status: done | partial | failed
```

- This produces one clip per shot; final timeline composition/export remains a separate stage.
- The same capability validator serves the standalone video page and this batch path. Aspect ratio, FPS, quality, duration, prompt enhancement, and reference media are omitted when the selected model does not support them.
- A model that requires a reference image marks a shot without a storyboard image as failed, so the batch can finish `partial` without inventing a first frame from an unrelated portrait.

## 4. Chat streaming

Two bridges, deliberately separate. Do not collapse them.

```
composer (assistant-ui, useExternalStoreRuntime)
      │  onNew
      ▼
use-chat-controller.ts  (AI SDK useChat + DefaultChatTransport)
      │  POST /api/bff/chat/sessions/:id/messages/stream
      ▼
Next route  ──  reads backend NDJSON, writes an AI SDK UI stream
      │            userMessage | agent_step | reasoning_delta | content_delta | assistantMessage | error
      ▼
backend /api/chat/… ─▶ graph/context_graph  ─▶ history ─▶ token budget ─▶ summary compression ─▶ model
```

- The transport's base `api` carries a `_` placeholder that `prepareSendMessagesRequest` rewrites per send from `body.sessionId`, so a brand-new chat can send before its session id exists.
- Execution-trace events arrive as transient `data-agent_step` parts and are consumed in `onData`, not as message content.
- Context compression: when history exceeds `SCENEFLOW_MAX_CONTEXT_TOKENS` (default 100000), older messages are summarised into `chat_sessions.context_summary` and the recent detail is kept.
- assistant-ui renders from an **external store** because the AI SDK already owns message state. Full design, and the changes that would break it, in `../design/feature-chat.md`.

## 5. Metering and billing

```
before the provider call:  require_model_balance(session, user_id, config)
   └─ official config + non-superAdmin + balance ≤ 0  ─▶ 402
after the provider call:   record_usage(...)
   ├─ price the call from the config's pricing snapshot ─▶ cost_micros
   ├─ insert a usage_logs row (prices copied in, not referenced)
   └─ official config only: atomic SQL decrement of users.balance_micros (floored at 0)
```

Personal configs are metered but never charged — the user is paying the provider directly. Detail in `../design/feature-billing.md`.

## Artifact lifecycle

```
provider bytes ─▶ store_artifact() ─▶ private_generated/<path>   (0700 dir)
row stores the RELATIVE PATH
serializers.py mints a signed URL per response (HS256 over the JWT secret, 30-day TTL)
```

`_migrate_scene_assets` in `app/core/database.py` upgrades older rows in place and drops references whose token no longer decodes — those links were already dead.

## Realtime

`GET /ws/projects/:id`, authenticated by `sceneflow-auth.<JWT>` in `Sec-WebSocket-Protocol`. Project-scoped broadcast with heartbeat. Event types: `WS_CONNECTED`, `PROJECT_UPDATE`, `SCENE_UPDATE`. `app/core/realtime.py` keeps an in-process registry of sockets per project and drops dead ones on send — **this does not survive multiple backend processes**; a second worker would need a shared broker.
