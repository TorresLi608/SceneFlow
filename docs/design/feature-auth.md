# Feature: authentication and access control

Verified on **2026-09-07**. Covers registration, login, session tokens, roles, account state, and how credentials reach the WebSocket and provider layer. Owners and checks are in the [code map](../architecture/code-map.md).

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
- Registration consumes an **invitation code**: unknown → `400 invalid invitation code`, already used → `409 invitation code already used`, past its window → `410 invitation code expired`. Claiming is an atomic conditional `UPDATE` with a `rowcount` check, so two simultaneous registrations cannot share one code.
- Invitation codes are created by a super admin with a validity of 1, 7, or 30 days and record `created_by_user_id` for audit.
- `POST /api/auth/send-verification-code` issues a six-digit code valid for 300 seconds, with a 60-second per-email cooldown (`429`). `verification_service.py` validates/consumes it; `email_service.py` uses SMTP. When SMTP host/user are absent, the current implementation prints the code to its log, including outside development; configure SMTP for deployed email registration.

## Super admin

`SCENEFLOW_SUPER_ADMIN_USERNAME` selects the login name (default `superAdmin`, 3–64 characters after trimming). On a fresh database, startup creates it with `SCENEFLOW_SUPER_ADMIN_PASSWORD`; subsequent startups keep that admin enabled without resetting its password. The role string remains `superAdmin` regardless of the login name; authorization and billing use the role, not a hardcoded username.

When an existing installation first changes the default login, `seed_super_admin()` renames the old `superAdmin` row with role `superAdmin` in place. Its ID, password, balance, ownership, and relationships remain intact; login by the old name stops working. An occupied destination fails startup, including a collision with another admin. A configured name belonging to a non-admin also fails instead of promoting that user.

After the default account has been renamed, this setting is not a general account-renaming tool. If another super admin already exists and the configured name matches none, startup fails instead of creating another privileged account or guessing which one to rename. For a subsequent rename, stop the backend, back up the database, explicitly update that account's `username` without changing its ID or password, and update the environment to match before restarting. Password changes use the authenticated account-profile flow.

The dev password is `superAdmin@123`; production startup refuses to boot if `SCENEFLOW_JWT_SECRET`, `SCENEFLOW_AES_KEY`, or `SCENEFLOW_SUPER_ADMIN_PASSWORD` are still the development defaults (`app/core/config.py`). Customizing a login name does not replace a strong password or login rate limiting; the current rate-limit gap remains listed below.

Super admin is exempt from balance checks and from balance deduction — see `feature-billing.md`.

## Frontend

- `useUserStore` (Zustand, persisted) holds the token and user. Standalone image/video histories also use separate localStorage lists; project/episode/shot working copies are not persisted there. Resetting a generation editor must preserve both authentication and history.
- The axios request interceptor attaches the token; the response interceptor calls `logout()` on any `401`. Do not add per-call 401 handling.
- General authenticated pages use the `(workspace)` shell. `/projects/[projectId]` redirects to `/info`; the six project sections and full-screen episode/legacy editors have their own layouts. Backend dependencies enforce authorization independently of these layouts.
- Login/register are at `/login` and `/register`.
- The UI displays `nickname` when present and falls back to `username`; username remains the login credential.

## Rules when extending

1. **Never widen the token.** Roles and state are read from the database per request, not from JWT claims, so disabling a user or changing a role takes effect immediately. Putting a role in the token would break that.
2. **Every project-scoped endpoint proves ownership.** The established message is `403 project does not belong to current user`; `404` is acceptable where confirming existence would leak.
3. **Config detail is not secret reveal.** `GET /api/settings/keys/:id` returns metadata. `POST /api/settings/keys/:id/secret` reveals a personal key to its owner; `POST /api/admin/model-configs/:id/secret` is the super-admin equivalent. A key that cannot be decrypted is `400 stored API key cannot be decrypted`.
4. **Signed artifact URLs are bearer credentials.** They use a key derived from the JWT secret and expire in 30 days. Rotating `SCENEFLOW_JWT_SECRET` invalidates current JWTs and outstanding URLs; relative stored paths remain intact and serializers can issue new links. `_migrate_scene_assets` is historical migration code, not a rotation-time cleanup job.
5. The `baseUrl` of a custom provider is validated against private networks (`400 baseUrl must not target a private network`) — this is SSRF protection, keep it on any new URL input.

## Known gaps

- No refresh-token flow; a 24h expiry means a long editing session can end in a logout. There is no token revocation list — disabling the account is the revocation mechanism.
- No general rate limiting on login/registration or verification attempts; sending email codes has the per-email cooldown above.
- CORS origins come from `SCENEFLOW_CORS_ORIGINS` and default to the two local frontend origins; production must set it explicitly.
