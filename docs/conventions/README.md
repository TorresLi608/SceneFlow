# Conventions

Verified on **2026-09-07**. These files describe the contracts to preserve and identify current exceptions. If code contradicts a rule, establish whether the code or the rule is stale; record verified gaps in the [backlog](../plans/backlog.md). Use the [code map](../architecture/code-map.md) to locate owners.

| File | Covers |
|---|---|
| `naming.md` | Identifiers, IDs, files, API fields, i18n keys |
| `error-handling.md` | Status codes, the error envelope, validation, frontend surfacing |
| `testing.md` | How the two test setups work and how to add a test |
| `logging.md` | Logger setup, levels, and what must never be logged |
| [Bug history index](../bugs/README.md) | Required starting point for bug fixes; summaries, detail links, and the recording template |

## The non-negotiables

Violating any of these produces a bug that does not show up until production data or a long-running series exists.

1. **Requests/responses use camelCase; Python/storage use snake_case.** Typed bodies extend `CamelModel` and reject unknown fields with 422 (`extra="forbid"`). Legacy dict-body endpoints still validate manually; response serializers, not `CamelModel`, shape response dictionaries.
2. **Preserve explicit empty PATCH values.** Typed workbench PATCHes treat absent/`null` as leave-alone. Use `model_dump(exclude_unset=True)` and field-specific handling; `""`, `false`, `0`, and `[]` can be real edits. `value is not None` preserves false; truthiness filtering loses it. `videoFirstFrame: ""` clears the slot to stored JSON `null`; `…Explicit` flags distinguish deliberate removal from an untouched default.
3. **Generated media stores relative paths, never signed URLs.** Links expire in 30 days and remain stable within a UTC day. `Asset.path` can deliberately hold an imported external HTTP(S) URL. Shot rows use stable IDs as keys and `updatedAt` to synchronize drafts; never key on media URLs.
4. **Money is `Decimal`/string end to end**, in micros. A price must never become a JS `number`.
5. **Timestamps are ISO-8601 strings.** Not `datetime`, not epoch.
6. **Every schema change needs a reviewed Alembic revision.** Change SQLModel first and run `alembic check`; never add runtime schema mutation to `app/core/database.py`.
7. **All user-facing strings live in `frontend/src/lib/i18n.ts`**, in both `zh` and `en`.
8. **Never log secrets or user content.** Provider keys are AES-GCM encrypted at rest; list/detail serializers omit them, and only authorized secret-reveal POSTs return a decrypted value. Log request/entity IDs, not prompt bodies. Existing logging gaps are tracked in the backlog.

## Working agreements

- **Check for an existing library before hand-rolling.** A standing instruction from the project owner: prefer mature open source or a dependency already in the tree; write custom code only when nothing fits or the library would clearly add complexity. LangChain/LangGraph on the backend, `@base-ui/react` + shadcn-style organisation and `@assistant-ui/react` on the frontend.
- **Wrap a replaced library rather than churning every call site.** `useI18n()` stayed as a thin facade when the hand-rolled interpolation engine was swapped for `i18next` + `react-i18next`, so no page component had to change. Reach for the same move when replacing infrastructure under a wide API.
- **pnpm, not npm.** `npm install` does not update `pnpm-lock.yaml`; a dependency added that way is invisible to everyone else.
- **Comments explain *why*.** This codebase's comments encode constraints that are expensive to rediscover (see `project-store.ts`, `generation_service.py`, `main.py`). Match that register, and do not strip them while refactoring.
- **Prefer fewer, sharper abstractions.** Reuse existing module boundaries rather than introducing one-off indirection. `AppSidebar` is concrete because there is one sidebar; do not build a framework for a single caller.
- **A base-ui `Select` needs `items` on the root, not just `label` on each item.** `Select.Value` resolves the trigger's text from the root's `items` prop; the `label` on `Select.Item` only feeds keyboard typeahead. Omit `items` and the trigger renders the raw value — a language picker showed `zh` after the user chose 中文, and the production-settings mode showed `comic`. Either pass `items={[{value, label}]}` or give `Select.Value` explicit children. The shared prompt-language list is `promptLanguageItems(t)` in `components/prompt-field.tsx`.

## Recording bug fixes

Every bug-fix task starts with the [Bug history index](../bugs/README.md) and matching details, and ends by updating the issue record and its index row in the same handoff. Same root cause means updating the existing record; a new root cause gets its own detail under `docs/bugs/`. No root-level bug/fix summary files. Follow [AGENTS.md](../../AGENTS.md#bug-fix-workflow) and the index template; record actual validation, not intended results.

## Writing a migration

Three rules, each of which was learned from a bug that only a database with real data could show:

- **A migration must not read a model that is still moving.** `SQLModel.metadata` is *today's* schema; a revision is a fixed point in history. The baseline (`345000649eb5`) built its legacy rebuild from live metadata, so an unversioned database was upgraded straight to the current schema — and then every table added afterwards (`assets`, `email_verifications`) collided with the migration that creates it. Import nothing that can drift: write the columns out, or reflect what is actually there. Metadata is fine for *ordering* (foreign-key dependency), never for shape.
- **Guard for a table that is not there yet.** A database stamped at an earlier revision need not carry every table, and `inspect(...).get_columns("scenes")` raises rather than skipping. `6655a5517a16`, `d7b25e91c840`, and `e5c94a1f6d38` show the pattern; `c93e7a1b4d20` was fixed to match.
- **Foreign keys are off during migrations, on at runtime** (`migrations/env.py`). `render_as_batch` alters a SQLite table by recreating it — copy, drop, rename — and with enforcement on, that drop *cascades into the referrers*: altering `model_configs` nulled `chat_sessions.config_id` and deleted every `user_official_config_defaults` row. Set the pragma through the raw DBAPI cursor, never `exec_driver_sql`, which autobegins a transaction Alembic then does not own — every migration appears to run and nothing persists.

Name an index `idx_*`, matching the rest of the schema, and declare it in `__table_args__`. `Field(index=True)` lets SQLAlchemy generate an `ix_*` name that no migration uses, and `alembic check` then reports the same drop-and-add forever.

## Keeping generated docs current

`docs/reference/api-spec.yaml` is generated from `app.openapi()`, without starting the server or its worker. Regenerate after endpoint or request/response changes with the existing [script](../../backend/scripts/regen_api_spec.py). Set both database and media paths before importing the app; `main.py` creates/chmods the media directory at import time:

```bash
cd backend
spec_dir=$(mktemp -d)
PYTHONPATH=. DATABASE_URL= SCENEFLOW_DB_PATH="$spec_dir/spec.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$spec_dir/media" SCENEFLOW_WORKER_ENABLED=0 .venv/bin/python scripts/regen_api_spec.py
```

`PYTHONPATH=.` is required when running the file under `scripts/`. The temporary directory contains no application data. OpenAPI covers HTTP routes and typed schemas; legacy dict payloads and manually serialized responses are less specific, and WebSocket/NDJSON event contracts live in [data flow](../architecture/data-flow.md).
