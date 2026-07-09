# Task Plan: Project Continuity + Chat Attachments

## Goal
Summarize the current SceneFlow project so future AI sessions can resume development quickly and safely, then improve intelligent chat attachments and composer UI.

## Current Phase
Complete

## Session 2026-07-09: Recent Updates + Development Rules Docs

### Goal
- Record the recent dependency cleanup and i18n migration.
- Make the open-source-first rule explicit for future human/AI development.
- Document that `@base-ui/react` + shadcn-style components are the preferred frontend component foundation.

### Phases

#### Phase 1: Inspect current planning docs
- [x] Read `planning-with-files` instructions.
- [x] Read `task_plan.md`, `findings.md`, `progress.md`, `AI_HANDOFF.md`, and `RUNNING.md`.
- **Status:** complete

#### Phase 2: Capture recent decisions
- [x] Document open-source-first, avoid-hand-rolled-generic-code guidance.
- [x] Document `react-i18next`/`i18next` replacing custom i18n interpolation.
- [x] Document `google-genai` vs `langchain-google-genai` decision.
- [x] Document `@base-ui/react` + shadcn-style UI direction.
- **Status:** complete

#### Phase 3: Verify docs
- [x] Run lightweight doc/status checks.
- [x] Update `progress.md` with completed actions.
- **Status:** complete

### Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use open-source libraries before hand-written generic infrastructure | Keeps code maintainable and easier for humans/AI to extend. |
| Keep `useI18n()` as a local facade over `react-i18next` | Low churn at call sites while replacing the hand-rolled interpolation engine. |
| Keep `google-genai` for Gemini native image generation | Direct SDK is simpler for current image workflow; LangChain wrapper only matters for native Gemini chat. |
| Keep `@base-ui/react` + shadcn-style components | Matches current frontend stack and avoids custom primitive behavior. |

## Phases

### Phase 1: Create persistent notes
- [x] Create `task_plan.md`
- [x] Create `findings.md`
- [x] Create `progress.md`
- **Status:** complete

### Phase 2: Inspect project structure
- [x] Identify stack, package manager, and workspace layout
- [x] Identify backend entry points and major modules
- [x] Identify frontend entry points and major modules
- [x] Identify useful scripts and test commands
- **Status:** complete

### Phase 3: Write handoff summary
- [x] Update `findings.md` with project map and development notes
- [x] Update `progress.md` with completed actions
- [x] Add current-session pointer to `AI_HANDOFF.md`
- [x] Mark this plan complete
- **Status:** complete

## Key Questions
1. What technology stack and package manager does this repo use?
   - Backend: Python/FastAPI/SQLite/LangChain/LangGraph. Frontend: Next.js 16/React 19/TypeScript/Tailwind/assistant-ui. Package docs mention npm; root also has a tiny pnpm lock.
2. Where are the main app entry points and core modules?
   - Answered in `findings.md` under Project Map.
3. What commands should future AI sessions run before changing code?
   - Backend compile check and frontend lint/build/type-check are documented in `AI_HANDOFF.md`; exact commands captured in `findings.md`.

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use the three planning files in the project root | Matches `planning-with-files`; keeps context beside code for future sessions. |
| Keep the summary concise | Future AI needs a map, not a second codebase. |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `zsh: no matches found: frontend/src/app/projects/[projectId]/page.tsx` | 1 | Quote bracketed Next.js route paths before reading them. |
| `zsh: no matches found: frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` | 2 | Same bracket-path issue; quote all Next dynamic route paths. |

## Notes
- Re-read this file before making project-level decisions.
- Update `findings.md` after project discoveries.
- Update `progress.md` after each phase or error.

## Session 2026-07-06: Chat Attachments + Composer UI

### Goal
- Make intelligent chat upload accept all files, including code files like `.py`.
- Parse images and text/code files when possible.
- For unsupported or unreadable binary formats, send an explicit "cannot parse this file" notice instead of blocking upload.
- Clean up the frontend composer to feel closer to ChatGPT: compact attachments, clear input row, less visual clutter.

### Phases

#### Phase 1: Inspect current assistant-ui integration
- [x] Read assistant-ui overview, primitives, and runtime skill docs.
- [x] Read current composer/runtime code and backend attachment flow.
- **Status:** complete

#### Phase 2: Implement all-file attachment adapter
- [x] Replace limited image/text adapter with wildcard adapter.
- [x] Keep images as image parts.
- [x] Read text/code files into text parts.
- [x] Send PDF/Office/other files to backend parser with explicit unparseable notices.
- **Status:** complete

#### Phase 3: Tighten composer UI
- [x] Make attachment chips compact and wrapping.
- [x] Keep input controls in a ChatGPT-like bottom row.
- [x] Remove oversized attachment bar behavior seen in screenshots.
- **Status:** complete

#### Phase 4: Verify and document
- [x] Run backend compile/service checks if backend touched.
- [x] Run frontend type-check and lint.
- [x] Update `AI_HANDOFF.md`, `findings.md`, and `progress.md`.
- **Status:** complete

### Verification
- `backend/.venv/bin/python -m compileall -q backend`
- `backend/.venv/bin/python backend/chat_service.py`
- `cd frontend && npx tsc --noEmit`
- `cd frontend && npm run lint`
- `cd backend && .venv/bin/python -c "...attachment smoke test..."`

## Session 2026-07-06: Chat Streaming, AI SDK, and Scroll UX

### Goal
- Make the intelligent chat message list behave correctly during streaming output.
- Show a visible scrollbar and a ChatGPT-like "scroll to bottom" arrow when the user scrolls away from the latest response.
- Let Vercel AI SDK handle frontend chat sending, stream parsing, and in-progress message state where it fits.
- Keep Assistant UI responsible for rendering and composer primitives.

### Phases

#### Phase 1: Message list scrollbar
- [x] Add a dedicated `chat-message-list-scrollbar` class to the message list scroller.
- [x] Add scoped scrollbar CSS in `frontend/src/app/globals.css`.
- **Status:** complete

#### Phase 2: Streamdown package clarification
- [x] Identify `streamdown` as the AI-streaming Markdown renderer.
- [x] Identify `@streamdown/code` as Shiki syntax highlighting for code blocks.
- [x] Identify `@streamdown/cjk` as CJK-friendly Markdown/text handling.
- **Status:** complete

#### Phase 3: AI SDK frontend integration
- [x] Add `@ai-sdk/react` and `ai` dependencies.
- [x] Convert BFF chat stream response from backend NDJSON into AI SDK UI stream chunks.
- [x] Replace the frontend hand-written NDJSON reader with `useChat` and `DefaultChatTransport`.
- [x] Preserve existing `agent_step` execution flow UI through transient `data-agent_step` chunks.
- [x] Keep backend Python/LangChain/LangGraph model calls unchanged.
- **Status:** complete

#### Phase 4: Auto-scroll and bottom arrow
- [x] Pass `isStreaming` from `use-chat-controller.ts` through `chat-panel.tsx` to `chat-message-list.tsx`.
- [x] Auto-scroll only while the user remains near the bottom.
- [x] Show a floating down-arrow button when the user scrolls away from the bottom.
- [x] Clicking the arrow scrolls to the bottom and resumes auto-follow.
- [x] Gate `ResizeObserver` follow-up scrolling so async content growth can settle without fighting manual upward scroll.
- [x] Cancel pending auto-scroll immediately when the user scrolls upward.
- **Status:** complete

### Verification
- `cd frontend && npm run lint`
- `cd frontend && npx tsc --noEmit`

### Notes
- `cd frontend && npm run build` was attempted after AI SDK integration but stayed in Next/Turbopack "Creating an optimized production build ..." for more than two minutes with no new output, then was interrupted to avoid leaving a hanging process.
- `npm install @ai-sdk/react ai` reported 12 npm audit findings; they were not fixed in this task to avoid widening scope.
- The AI SDK migration is intentionally frontend/BFF-scoped. Full backend migration to a Node/Vercel AI SDK runtime was skipped because the backend already owns Python LangChain/LangGraph orchestration and persistence.

### Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `zsh: no matches found: frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` | 1 | Quote bracketed Next.js dynamic route paths. |
| ESLint parsing error in BFF stream route after adding `createUIMessageStreamResponse` | 1 | Fixed a missing closing parenthesis around `createUIMessageStream(...)`. |
| React lint error: `setState` synchronously inside an effect | 1 | Moved initial scroll-state update into `requestAnimationFrame`. |
| Streaming output caused scroll jitter, worse when user scrolled upward | 1 | Gated `ResizeObserver`, canceled pending auto-scroll on upward wheel, and only auto-follow when still near bottom. |

## Session 2026-07-06: Chat Scroll Documentation Sync

### Goal
- Check whether the latest chat initial-scroll fix is reflected in project docs, and update only stale documentation.

### Phases

#### Phase 1: Inspect docs
- [x] Read existing planning files.
- [x] Search project docs for chat scroll behavior.
- **Status:** complete

#### Phase 2: Sync stale docs
- [x] Update any stale docs found.
- [x] Keep documentation scoped to current behavior.
- **Status:** complete

#### Phase 3: Verify
- [x] Run lightweight documentation/diff checks.
- [x] Update `findings.md` and `progress.md`.
- **Status:** complete

### Verification
- `rg` scan for stale chat-scroll/ResizeObserver phrases in markdown
- `git diff --check`

### Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `zsh: command not found: ResizeObserver` while searching docs | 1 | Re-ran the `rg` search with the pattern in single quotes so backticks were not treated as shell command substitution. |
