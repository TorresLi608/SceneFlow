# Conventions

Start here. These files describe how this codebase already works — they are descriptive, not aspirational. If you find code that contradicts a rule here, the code is either a bug or the rule is stale; say which rather than silently following the outlier.

| File | Covers |
|---|---|
| `naming.md` | Identifiers, IDs, files, API fields, i18n keys |
| `error-handling.md` | Status codes, the error envelope, validation, frontend surfacing |
| `testing.md` | How the two test setups work and how to add a test |
| `logging.md` | Logger setup, levels, and what must never be logged |

## The non-negotiables

Violating any of these produces a bug that does not show up until production data or a long-running series exists.

1. **Requests are camelCase, storage is snake_case, and `CamelModel` bridges them.** Unknown fields are a 422 (`extra="forbid"`), not a silent drop.
2. **`null` in a PATCH means "leave alone".** Clearing a value is `""` or `false`. Never filter request fields with `is not None`.
3. **Media is stored as a relative path, never a URL.** Signed links expire in 30 days; serializers mint a fresh one per response.
4. **Money is `Decimal`/string end to end**, in micros. A price must never become a JS `number`.
5. **Timestamps are ISO-8601 strings.** Not `datetime`, not epoch.
6. **A new column on an existing table needs `_add_missing_columns()`** in `app/core/database.py`, or existing databases drift.
7. **All user-facing strings live in `frontend/src/lib/i18n.ts`**, in both `zh` and `en`.
8. **Never log or return a secret** — API keys are AES-GCM encrypted at rest and stay that way in transit except through the explicit reveal endpoint.

## Working agreements

- **Check for an existing library before hand-rolling.** A standing instruction from the project owner: prefer mature open source or a dependency already in the tree; write custom code only when nothing fits or the library would clearly add complexity. LangChain/LangGraph on the backend, `@base-ui/react` + shadcn-style organisation and `@assistant-ui/react` on the frontend.
- **Wrap a replaced library rather than churning every call site.** `useI18n()` stayed as a thin facade when the hand-rolled interpolation engine was swapped for `i18next` + `react-i18next`, so no page component had to change. Reach for the same move when replacing infrastructure under a wide API.
- **pnpm, not npm.** `npm install` does not update `pnpm-lock.yaml`; a dependency added that way is invisible to everyone else.
- **Comments explain *why*.** This codebase's comments encode constraints that are expensive to rediscover (see `project-store.ts`, `generation_service.py`, `main.py`). Match that register, and do not strip them while refactoring.
- **Prefer fewer, sharper abstractions.** Reuse existing module boundaries rather than introducing one-off indirection. `AppSidebar` is concrete because there is one sidebar; do not build a framework for a single caller.

## Keeping generated docs current

`docs/reference/api-spec.yaml` is generated from the running app. Regenerate it after changing any endpoint or request/response model:

```bash
cd backend && SCENEFLOW_DB_PATH=/tmp/sf_spec.db .venv/bin/python -c "
import yaml
from app.main import app
spec = app.openapi()
header = ('# SceneFlow backend OpenAPI spec.\n'
          '# GENERATED FILE - do not hand-edit. Regenerate with the command in docs/reference/error-codes.md.\n')
with open('../docs/reference/api-spec.yaml', 'w', encoding='utf-8') as handle:
    handle.write(header)
    yaml.safe_dump(spec, handle, allow_unicode=True, sort_keys=False, width=100)
"; rm -f /tmp/sf_spec.db
```
