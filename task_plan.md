# Task Plan: Project Continuity + Chat Attachments

## Goal
Summarize the current SceneFlow project so future AI sessions can resume development quickly and safely, then improve intelligent chat attachments and composer UI.

## Current Phase
Complete

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
