# SceneFlow documentation

Verified against application code on **2026-09-07**. For a bug, first read the [Bug history index](bugs/README.md), then matching issue details and the code map. For other changes, start with the code map and relevant contract/feature design. [AGENTS.md](../AGENTS.md) is the short agent entry point; this directory holds the maintained detail.

## Architecture and code navigation

| Document | Use it for |
|---|---|
| [Code map](architecture/code-map.md) | Pages, actions, backend owners, tables, regression entry points, and legacy paths |
| [Overview](architecture/overview.md) | Processes, versions, state ownership, and startup |
| [Boundaries](architecture/boundaries.md) | BFF routing, provider calls, database sessions, jobs, and concurrency |
| [Data flow](architecture/data-flow.md) | Script → shots → images → clips → export; references, cancellation, chat, billing |

## Conventions and feature designs

| Document | Use it for |
|---|---|
| [Conventions](conventions/README.md) | Shared invariants, migrations, and OpenAPI regeneration |
| [Naming](conventions/naming.md) | IDs, paths, JSON fields, and i18n keys |
| [Error handling](conventions/error-handling.md) | HTTP envelopes, validation, async failures, and client surfacing |
| [Testing](conventions/testing.md) | Isolated backend self-checks, Node tests, typecheck, and lint |
| [Logging](conventions/logging.md) | Request IDs, redacted error records, and privacy boundaries |
| [Authentication](design/feature-auth.md) | Invitation/email registration, JWTs, roles, provider secrets |
| [Chat](design/feature-chat.md) | AI SDK state, assistant-ui composer, stream bridge, attachments, agent tools |
| [Search and filtering](design/feature-search.md) | Local filters and paginated admin queries |
| [Billing](design/feature-billing.md) | Micros, price snapshots, official balance gates, redemption |

## Reference and status

| Document | Use it for |
|---|---|
| [Local setup](reference/local-setup.md) | Setup commands, ports, development launcher, Docker, troubleshooting |
| [Backend reference](../backend/README.md) | Environment variables, endpoint list, model/provider support |
| [OpenAPI](reference/api-spec.yaml) | Generated HTTP paths and typed request schemas; legacy dict bodies have less detail |
| [Error inventory](reference/error-codes.md) | Common status/message pairs and non-error outcomes |
| [Bug history index](bugs/README.md) | Searchable issue summaries, status, and links to per-bug diagnosis/fix/validation records |
| [Current state](plans/current-sprint.md) | Source-verified delivered capabilities; no implied sprint assignment |
| [Backlog](plans/backlog.md) | Remaining implementation gaps and reports needing reproduction |

## Keeping the map useful

- Application code and tests are the evidence. A test file's presence is not proof that its current assertions pass; report executed checks separately.
- Every bug fix updates its detail under `docs/bugs/` and the [history index](bugs/README.md) before handoff; do not put repair summaries at the repository root. The old `reference/known-errors.md` only redirects.
- Put behavior in one owning document and link to it. `CLAUDE.md` imports `AGENTS.md`; do not restore a second instruction copy.
- Regenerate [api-spec.yaml](reference/api-spec.yaml) with [regen_api_spec.py](../backend/scripts/regen_api_spec.py); do not edit generated schemas manually. WebSockets and NDJSON events are documented separately because OpenAPI does not describe them fully. Generated descriptions are copied from source docstrings, some of which still describe legacy behavior; use the current data-flow document for those runtime distinctions.
- Update [the code map](architecture/code-map.md) when a route, action, service, table, or test moves. Keep implemented behavior separate from proposed architecture and historical notes.
