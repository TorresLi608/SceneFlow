# Data flow

Four flows carry almost all of the product: parse, render, chat, and metering. Each is traced end to end below with the files that own each hop.

## 0. Which model a call uses

```
project.{text,image,video,audio}_config_id  ─▶  config_service.project_model_config
   └─ unset / disabled / deleted ─▶ active_model_config
        └─ user's official default ─▶ user's active config ─▶ system official
```

**Project-first, never project-only.** A series created before the model panel existed has every pick unset, and a pinned config that was later deleted resolves to nothing — both fall through to the account default rather than failing the render. `GET /api/projects/:id/models` returns what each purpose actually resolves to, plus the limits the UI must enforce (`imageMaxReferenceImages`, the video config's declared `videoCapabilities`); it never returns an API key.

The same row carries the generation defaults — image resolution and ratio, video quality/ratio/duration/fps/promptExtend — so a storyboard and the clips made from it agree, and the episode editor prefills instead of asking the same six questions per run. `PATCH /api/projects/:id` takes them under `modelSettings`; a config id of **`0` clears a pick**, because `null` already means "leave alone".

## 1. Script → shots (breakdown)

```
episode editor ─▶ breakdownEpisodeAction ─▶ POST /api/projects/:id/episodes/:episodeId/breakdown
   ─▶ breakdown_service assembles the bible context
   ─▶ models.breakdown_script (LLM, JSON response format)
   ─▶ replace the episode's shots, or annotate them in place
```

- Body: `{ target, script?, references, replaceAll?, model? }`.
- **`target` picks which half is produced.** `shots` fills narration, dialogue, speaker, frame prompt, and shot size. `video` fills camera move, transition, duration, and motion prompt. `both` fills everything.
- **`target: "video"` updates rows in place and never replaces them.** Re-deriving how the camera moves is no reason to throw away frames that have already been rendered and paid for. It requires existing shots and 400s without them.
- **`references` decides what the model defers to**, and the three cases are deliberately distinct: a selected character *with* a drawn sheet is named so the prompt says "参照《…》三面图" rather than re-describing a face the renderer already pins; a character with only written setting is reasoned about from that text; anyone the bible has never heard of (walk-ons, 甲乙丙丁) is invented from the script. Selecting nothing is a fourth, valid case — decide everything from the script.
- **Re-splitting is destructive.** If the target episode already has shots carrying a generated image or voice track, the response comes back `applied: false` with `discardsGeneratedScenes: N`. The client confirms with the user, then repeats with `replaceAll: true`.
- Shot `order` restarts at 1 within each episode, so the response carries one episode's shots — never the series merged together.
- `speaker` is matched back to a character by name and aliases, best-effort: an unmatched speaker is a walk-on working as intended, not an error.

`POST /api/projects/:id/parse` still exists and still produces the narration-plus-frame-prompt shape. It serves the legacy single-screen editor, which knows nothing about camera moves; the two schemas are not compatible, which is why `breakdown_script` sits beside `parse_script` rather than replacing it.

## 2. Shots → images (render)

```
POST /api/projects/:id/episodes/:episodeId/tone-sheet     ← anchor, on its own
POST /api/projects/:id/episodes/:episodeId/storyboard     ← frames, against the anchor
   { sceneIds?, references? }
   ─▶ claim_project_status  (conditional UPDATE; second click loses)
   ─▶ runs.register(project_id)  ─▶ asyncio.create_task(...)   ← returns 202 immediately
        └─ sequential, checking runs.is_cancelled between shots:
             tone sheet + selected reference images + previous shot's render
             store_artifact()       ─▶ private_generated/<relative path>
             broadcast SCENE_UPDATE ─▶ ws://…/ws/projects/:id
   ─▶ terminal status: done | partial | failed | idle(stopped)
```

- **The tone sheet is its own step.** It decides lighting, palette, and render style for every frame that follows, so approving it first is much cheaper than discovering after twenty full-resolution renders that the episode looks wrong. `/storyboard` still generates one when none exists, so a caller that skipped the step gets an anchored render rather than twenty unrelated frames.
- `references` contains project-owned asset ids, never signed URLs. Tone-sheet generation accepts character, character-state, prop, and existing tone images and merges the selection into one provider slot. Storyboard generation passes selected image assets separately after reserving one slot for the tone sheet.
- `sceneIds` selects a subset — one shot for a regenerate, several for a batch. Omitted means every unlocked shot. Locked shots are skipped, and all-locked is a `400` rather than a silent no-op.
- The model config's `imageMaxReferenceImages` is enforced by both the editor and endpoint. A zero-reference model uses text-to-image; the renderer no longer assumes every image model supports edits.
- A portrait whose file is missing is skipped rather than failing the shot: losing consistency is a smaller harm than losing the render.
- The terminal status reflects what actually landed. `partial` is a real outcome, not an error state to normalise away.

## 2b. Stopping a run

```
POST /api/projects/:id/cancel ─▶ app/core/runs.cancel(project_id)
   └─ sets the project's asyncio.Event; the run loop checks it between shots
```

Cooperative, not an interrupt. A frame the provider is already drawing has been paid for, so it finishes and is kept; what the user is actually stopping is the *next* one. A stopped run reports `partial` when something landed and `idle` when nothing did — never `failed`, which would claim the render broke when the user stopped it. The busy lock is released by the run as it unwinds, never by the cancel endpoint, so a second render cannot start while the first is still writing.

`app/core/runs.py` is an in-process registry with the same limitation as `app/core/realtime.py`: a second backend process would not see the flag. Both need a shared broker before the app can run multi-process, and that is one change, not two.

## 3. Shots -> generated clips (drama / motion comic)

```
POST /api/projects/:id/generate-video   { sceneIds?, references? }
   -> project's video config + its declared capabilities
   -> project's saved defaults under whatever the request sent
   -> selected shots, <=2 concurrent, cancellable between shots
        storyboard image -> first-frame reference when supported/required
        video_prompt (falling back to visual_prompt) + camera move + transition
        per-shot duration_ms, clamped to the model's min/max
        selected project images / prior clips / voice samples -> references when supported
        video provider -> store_artifact(projects/<id>/<scene>.mp4)
        broadcast SCENE_UPDATE -> videoStatus / videoProgress / videoUrl
   -> terminal project + episode status
```

- The storyboard image is the automatic first-frame reference only when the selected model accepts images. Additional image, existing clip, and voice references are user-selected, resolved back to stored paths under the same project, and capped by `videoCapabilities`. Required reference kinds disable generation until satisfied; text-to-video models do not require a frame first.
- The motion prompt is tried before the frame prompt: `visual_prompt` describes a still, and a clip generated from it tends to hold still.
- Duration comes from the shot, not the batch. A six-second beat and a two-second reaction rendered at one fixed length is the pacing problem the breakdown's estimate exists to fix; a shot with no estimate falls back to the project default.
- The same capability validator serves the standalone video page and this batch path. Aspect ratio, FPS, quality, duration, prompt enhancement, and reference media are omitted when the selected model does not support them.


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

**The link is stable for a given file within a day.** `_sign` floors `iat` to the start of the UTC day rather than reading the clock, so the same artifact yields the same URL across responses. That is load-bearing, not cosmetic: the episode editor polls every three seconds while a render runs, and a per-response token meant re-downloading every storyboard frame on every tick — and any list row keyed on its asset URL was torn down and rebuilt along with it, discarding whatever the user was typing. **Key list rows on `updatedAt`, never on an asset URL.**

`_migrate_scene_assets` in the baseline revision upgrades older rows in place and drops references whose token no longer decodes — those links were already dead.

## Realtime

`GET /ws/projects/:id`, authenticated by `sceneflow-auth.<JWT>` in `Sec-WebSocket-Protocol`. Project-scoped broadcast with heartbeat. Event types: `WS_CONNECTED`, `PROJECT_UPDATE`, `SCENE_UPDATE`. `app/core/realtime.py` keeps an in-process registry of sockets per project and drops dead ones on send — **this does not survive multiple backend processes**; a second worker would need a shared broker.
