# Feature: authentication and access control

Covers registration, login, session tokens, roles, account state, and how credentials reach the WebSocket and the provider layer.

## Model

| Concern | Mechanism | Where |
|---|---|---|
| Password storage | bcrypt hash | `app/core/security.py`, `app/api/v1/auth.py` |
| Session token | JWT HS256, payload `{userId, iat, exp}`, **24h expiry** | `token_for` / `user_id_from_token` |
| Token transport (HTTP) | `Authorization: Bearer <jwt>` | axios request interceptor |
| Token transport (WS) | `sceneflow-auth.<jwt>` in `Sec-WebSocket-Protocol` | browsers cannot set headers on a WS handshake |
| Provider API keys | AES-256-GCM, key = SHA-256 of `SCENEFLOW_AES_KEY` | `encrypt` / `decrypt` |
| Roles | `user`, `superAdmin` | `users.role` |
| Account state | `is_disabled`, soft delete via `deleted_at` | checked on every request |

## Request path

`current_user` in `app/api/deps.py` is the single gate:

1. Prefix-strip the `Authorization` header — **strip, do not `replace`**, so a token whose body happens to contain `Bearer` survives intact.
2. Empty → `401 missing token`; undecodable → `401 invalid token`.
3. Load the user where `deleted_at IS NULL` → missing → `401 user not found`.
4. `is_disabled` → `403 user is disabled`. **A disabled user's existing token stops working immediately** — disabling is not deferred to token expiry.

`current_user_id` and `current_super_admin_id` build on it; the super-admin check reuses the already-loaded row rather than querying twice. Endpoints depend on one of these three — never parse the header themselves.

## Registration

- Username 3–64 chars, password length validated (`400 invalid username or password length`). Nickname and email are optional; when email is supplied, its verification code is required and consumed during registration.
- Duplicate username → `409 username already exists`.
- Registration consumes an **invitation code**: unknown → `404`, already used → `409 invitation code already used`, past its window → `410 invitation code expired`. Claiming is an atomic conditional `UPDATE` with a `rowcount` check, so two simultaneous registrations cannot share one code.
- Invitation codes are created by a super admin with a validity of 1, 7, or 30 days and record `created_by_user_id` for audit.

## Super admin

Created at startup **only if missing**, then kept enabled with role `superAdmin`. The dev password is `superAdmin@123`; production startup refuses to boot if `SCENEFLOW_JWT_SECRET`, `SCENEFLOW_AES_KEY`, or `SCENEFLOW_SUPER_ADMIN_PASSWORD` are still the development defaults (`app/core/config.py`).

Super admin is exempt from balance checks and from balance deduction — see `feature-billing.md`.

## Frontend

- `useUserStore` (Zustand, persisted) holds the token and user; it is the **only** business-adjacent thing in `localStorage`.
- The axios request interceptor attaches the token; the response interceptor calls `logout()` on any `401`. Do not add per-call 401 handling.
- Authenticated pages live under the `(workspace)` route group; the workbench lives at `/projects/[projectId]`.
- Login/register are at `/login` and `/register`.
- The UI displays `nickname` when present and falls back to `username`; username remains the login credential.

## Rules when extending

1. **Never widen the token.** Roles and state are read from the database per request, not from JWT claims, so disabling a user or changing a role takes effect immediately. Putting a role in the token would break that.
2. **Every project-scoped endpoint proves ownership.** The established message is `403 project does not belong to current user`; `404` is acceptable where confirming existence would leak.
3. **Keys never travel in cleartext except through the explicit reveal endpoint** (`GET /api/settings/keys/:id`, which decrypts for the owner). A key that cannot be decrypted is `400 stored API key cannot be decrypted`, never a 500.
4. **Signed artifact URLs are bearer credentials.** They are signed with a key derived from the JWT secret and expire in 30 days; rotating `SCENEFLOW_JWT_SECRET` invalidates every outstanding link and existing rows are cleaned up by `_migrate_scene_assets`.
5. The `baseUrl` of a custom provider is validated against private networks (`400 baseUrl must not target a private network`) — this is SSRF protection, keep it on any new URL input.

## Known gaps

- No refresh-token flow; a 24h expiry means a long editing session can end in a logout. There is no token revocation list — disabling the account is the revocation mechanism.
- No rate limiting on login or registration.
- CORS origins come from `SCENEFLOW_CORS_ORIGINS` and default to the two local frontend origins; production must set it explicitly.
