# Conventions

Start here. These files describe how this codebase already works — they are descriptive, not aspirational. If you find code that contradicts a rule here, the code is either a bug or the rule is stale; say which rather than silently following the outlier.

| File | Covers |
|---|---|
| `naming.md` | Identifiers, IDs, files, API fields, i18n keys |
| `error-handling.md` | Status codes, the error envelope, validation, frontend surfacing |
| `testing.md` | How the two test setups work and how to add a test |
| `logging.md` | Logger setup, levels, and what must never be logged |
| `../reference/known-errors.md` | Recurring failure modes, owners, and regression checks |

## The non-negotiables

Violating any of these produces a bug that does not show up until production data or a long-running series exists.

1. **Requests are camelCase, storage is snake_case, and `CamelModel` bridges them.** Unknown fields are a 422 (`extra="forbid"`), not a silent drop.
2. **`null` in a PATCH means "leave alone".** Clearing a value is `""` or `false`. Never filter request fields with `is not None`. This holds for object-valued fields too: `videoFirstFrame` takes `GenerationReferenceRequest | Literal[""]`, and `""` is what clears the slot. When "cleared" and "nobody has chosen yet" have to behave differently, the serializer exposes a companion `…Explicit` flag (as `imageReferencesExplicit` and `videoFirstFrameExplicit` do) rather than overloading `null`.
3. **Media is stored as a relative path, never a URL.** Signed links expire in 30 days; serializers mint a fresh one per response.
4. **Money is `Decimal`/string end to end**, in micros. A price must never become a JS `number`.
5. **Timestamps are ISO-8601 strings.** Not `datetime`, not epoch.
6. **Every schema change needs a reviewed Alembic revision.** Change SQLModel first and run `alembic check`; never add runtime schema mutation to `app/core/database.py`.
7. **All user-facing strings live in `frontend/src/lib/i18n.ts`**, in both `zh` and `en`.
8. **Never log or return a secret** — API keys are AES-GCM encrypted at rest and stay that way in transit except through the explicit reveal endpoint.

## Working agreements

- **Check for an existing library before hand-rolling.** A standing instruction from the project owner: prefer mature open source or a dependency already in the tree; write custom code only when nothing fits or the library would clearly add complexity. LangChain/LangGraph on the backend, `@base-ui/react` + shadcn-style organisation and `@assistant-ui/react` on the frontend.
- **Wrap a replaced library rather than churning every call site.** `useI18n()` stayed as a thin facade when the hand-rolled interpolation engine was swapped for `i18next` + `react-i18next`, so no page component had to change. Reach for the same move when replacing infrastructure under a wide API.
- **pnpm, not npm.** `npm install` does not update `pnpm-lock.yaml`; a dependency added that way is invisible to everyone else.
- **Comments explain *why*.** This codebase's comments encode constraints that are expensive to rediscover (see `project-store.ts`, `generation_service.py`, `main.py`). Match that register, and do not strip them while refactoring.
- **Prefer fewer, sharper abstractions.** Reuse existing module boundaries rather than introducing one-off indirection. `AppSidebar` is concrete because there is one sidebar; do not build a framework for a single caller.
- **A base-ui `Select` needs `items` on the root, not just `label` on each item.** `Select.Value` resolves the trigger's text from the root's `items` prop; the `label` on `Select.Item` only feeds keyboard typeahead. Omit `items` and the trigger renders the raw value — a language picker showed `zh` after the user chose 中文, and the production-settings mode showed `comic`. Either pass `items={[{value, label}]}` or give `Select.Value` explicit children. The shared prompt-language list is `promptLanguageItems(t)` in `components/prompt-field.tsx`.

## Writing a migration

Three rules, each of which was learned from a bug that only a database with real data could show:

- **A migration must not read a model that is still moving.** `SQLModel.metadata` is *today's* schema; a revision is a fixed point in history. The baseline (`345000649eb5`) built its legacy rebuild from live metadata, so an unversioned database was upgraded straight to the current schema — and then every table added afterwards (`assets`, `email_verifications`) collided with the migration that creates it. Import nothing that can drift: write the columns out, or reflect what is actually there. Metadata is fine for *ordering* (foreign-key dependency), never for shape.
- **Guard for a table that is not there yet.** A database stamped at an earlier revision need not carry every table, and `inspect(...).get_columns("scenes")` raises rather than skipping. `6655a5517a16`, `d7b25e91c840`, and `e5c94a1f6d38` show the pattern; `c93e7a1b4d20` was fixed to match.
- **Foreign keys are off during migrations, on at runtime** (`migrations/env.py`). `render_as_batch` alters a SQLite table by recreating it — copy, drop, rename — and with enforcement on, that drop *cascades into the referrers*: altering `model_configs` nulled `chat_sessions.config_id` and deleted every `user_official_config_defaults` row. Set the pragma through the raw DBAPI cursor, never `exec_driver_sql`, which autobegins a transaction Alembic then does not own — every migration appears to run and nothing persists.

Name an index `idx_*`, matching the rest of the schema, and declare it in `__table_args__`. `Field(index=True)` lets SQLAlchemy generate an `ix_*` name that no migration uses, and `alembic check` then reports the same drop-and-add forever.

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
