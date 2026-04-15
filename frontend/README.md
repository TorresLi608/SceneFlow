# SceneFlow Frontend (Phase 4)

## Install

```bash
cd frontend
npm install
```

## Run

```bash
npm run dev
```

## Environment

Copy `.env.example` to `.env.local` and adjust if needed:

```bash
NEXT_PUBLIC_BFF_BASE_URL=
BACKEND_API_BASE_URL=http://127.0.0.1:8080
```

## Implemented in Phase 2-4

- Next.js 16 + TypeScript + Tailwind + shadcn/ui setup
- React Query provider and request cache/state management
- Zustand persistent `userStore`
- Zustand session `projectStore` for projects and scenes
- Login/Register pages
- Settings dialog for Provider API Key save
- Global model selector (`gpt-4o` / `deepseek-v3`)
- Unified axios layer (`src/lib/http/*`) with auth interceptor
- BFF route layer (`src/app/api/bff/*`) + BFF service layer (`src/bff/*`)
- Action layer (`src/actions/*`) for page/component data operations
- Workbench layout with left sidebar menu and multi-project list
- Real script parsing (`/api/projects/:id/parse`) via BFF + action layer
- Project list/config list/scene list skeleton + entry animations
