# Feature: chat

The 智能问答 surface at `/chat`. This is the most intricate part of the frontend, and the easiest to break by "modernising" it toward a framework quickstart — read the two-bridge section before changing anything here.

## Two bridges, deliberately separate

```
composer  (assistant-ui: useExternalStoreRuntime + AssistantRuntimeProvider)
    │  onNew(message)
    ▼
use-chat-controller.ts  (AI SDK: useChat + DefaultChatTransport)
    │  POST /api/bff/chat/sessions/:id/messages/stream
    ▼
Next route  ──  backend NDJSON  ⟶  AI SDK UI stream
    │
    ▼
backend /api/chat/…  ─▶  graph/context_graph  ─▶  services/agent_service (LangChain create_agent)
```

**The AI SDK owns message and streaming state. assistant-ui owns the composer and attachments only.** That is why the runtime is `useExternalStoreRuntime` and *not* `useChatRuntime` — the latter would make assistant-ui the owner of state the AI SDK already holds, and the two would fight.

Consequences that look like bugs but are not:

- `AssistantRuntimeProvider` is mounted **around the composer** in `assistant-composer.tsx`, not at the app root. `app/layout.tsx` has no assistant runtime, and it should not get one.
- There is **no `<Thread>`**. Message rendering is custom in `chat-message-list.tsx`, using `TextMessagePartProvider` + `StreamdownTextPrimitive` from `@assistant-ui/react-streamdown`.
- There is **no `AssistantModal`** — chat is a full page, not a floating widget.
- The transport's base `api` carries a `_` placeholder that `prepareSendMessagesRequest` rewrites per send from `body.sessionId`, so a brand-new chat can send **before its session id exists**.

Reference material: https://www.assistant-ui.com/llms-full.txt · MCP docs server `npx -y @assistant-ui/mcp-docs-server` · vendored skills under `.agents/skills/` (pinned in `skills-lock.json`). The installed assistant-ui is newer than most training data — consult one of these before changing its APIs.

## The BFF route is where the halves meet

`src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` is the **only** real route under `app/api/bff/**`; everything else is the fallback proxy. It reads the backend's NDJSON and writes an AI SDK UI stream. Backend event types:

| Event | Becomes |
|---|---|
| `userMessage` | the persisted user message |
| `agent_step` | a transient `data-agent_step` part → the "执行流程" panel, consumed in `useChat`'s `onData` — **not** message content |
| `reasoning_delta` | a reasoning part |
| `content_delta` | assistant text |
| `assistantMessage` | the final persisted message |
| `error` | a stream error |

Adding an event type means touching three places: the backend emitter, this route, and the controller.

## Backend

- **Context assembly** — `app/graph/graphs/context_graph.py`: load history after `chat_sessions.context_summary_until` → estimate tokens → if over `SCENEFLOW_MAX_CONTEXT_TOKENS` (default 100000) **and** more than `RECENT_MESSAGES_TO_KEEP` (20) messages, summarise everything older into `context_summary` and keep the last 20 verbatim. The summary is injected as a system message explicitly framed as *prior context, not a new user request*.
- **The agent** — `app/services/agent_service.py` uses LangChain `create_agent` with three tools: `generate_image`, `generate_pdf`, `generate_word_document`. Generated artifacts are stored server-side and returned as signed 30-day links; paths are server-controlled, never client-supplied.
- **Persistence** — `chat_sessions` (with `context_summary`, `context_summary_until`) and `chat_messages`. The first question sets the session title.
- **Balance** — chat runs the standard gate: `require_model_balance` before, `record_usage` after. Covered by `tests/test_chat_balance.py`. See `feature-billing.md`.
- **Model selection** — a chat needs a usable default model; with none configured the request fails with a Chinese, user-facing `400` telling the user to add or activate a configuration.

## Scrolling is deliberate

`chat-message-list.tsx` follows the stream only while the user is pinned to the bottom, cancels following on manual scroll-up (showing a jump-to-bottom control), and force-scrolls when `autoScrollKey` changes — session switch or history load. The extra delayed scroll passes exist because Streamdown code blocks, Shiki highlighting, and ordered lists grow the content **asynchronously after mount**. A `ResizeObserver` re-scrolls only while still following, so a user who scrolled up is never yanked back.

Replacing this with a `scrollIntoView` on every message regresses all of it.

## Attachments

The composer accepts any file, capped at `MAX_ATTACHMENT_BYTES` (5 MB) each:

| Kind | Handling |
|---|---|
| Images | image part |
| Text and code files | read client-side with `readAsText` |
| PDF | backend, via `pypdf` |
| `.docx` / `.xlsx` / `.pptx` | backend, OpenXML parsed with the standard library |
| Legacy binary Office (`.doc`/`.xls`/`.ppt`) | explicit refusal asking the user to convert |
| Anything else unparseable | an explicit "cannot parse this file" note, **not** a failed send |

`app/utils/attachment_parser.py` owns the server side.

## Rules when extending

1. **Do not port this to `useChatRuntime` or `<Thread>`.** If a change seems to require it, the change is fighting the external-store split — raise it.
2. **Execution-trace events stay transient.** They describe the run, not the conversation; persisting them into message content would poison the context window.
3. **New tools go through `create_chat_tools`** and must return artifacts through the artifact service, so links stay signed and paths stay server-controlled.
4. **Respect the token budget.** Anything that adds to the prompt (a new system preamble, tool descriptions) eats into `MAX_CONTEXT_TOKENS` before compression triggers.
5. **Never log message content** — session and message IDs only. See `../conventions/logging.md`.

## Known gaps

- Compression is one-shot summarisation; a very long session accumulates summary-of-summary drift with no re-anchoring.
- No message editing, branching, or regeneration.
- Attachment parsing is synchronous inside the request.
- The agent's tool set is fixed at three; there is no per-user tool configuration.
