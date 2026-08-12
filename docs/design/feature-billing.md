# Feature: billing and metering

Every model call is priced, logged, and — when it runs on an **official** configuration — deducted from the user's balance. Personal configurations are metered but never charged, because the user is paying the provider directly.

## Units

**Micros. Everywhere.** One micro is 1e-6 of the account currency, stored as an integer (`cost_micros`, `balance_micros`, `amount_micros`).

- Arithmetic is `decimal.Decimal` on the backend and `decimal.js` on the frontend.
- Micro values cross the wire as **strings**, because a balance can exceed `Number.MAX_SAFE_INTEGER` and JSON numbers would silently lose precision. `money.test.mts` pins this: `"9007199254740993"` micros must render as `$9007199254.740993`.
- Display goes through `formatMicros`/`formatMoney` in `src/lib/money.ts`. Never divide by 1e6 by hand.
- Rounding to micros is `ROUND_HALF_UP`, applied once at the end of the calculation.

## Pricing model

A model configuration carries seven pricing fields, normalised by `normalize_pricing`:

| Field | Meaning |
|---|---|
| `input_price_per_million` | Uncached input tokens |
| `output_price_per_million` | Output tokens |
| `cache_read_price_per_million` | Cache-read tokens |
| `cache_write_price_per_million` | Cache-write tokens |
| `unit_price` | Per-unit cost for non-token work |
| `unit_name` | `token` \| `request` \| `image` \| `second` |
| `pricing_multiplier` | Applied last; must be > 0 |

```
uncached_input = input_tokens - cache_read - cache_write        # floored at 0
token_cost = (uncached_input·in + output·out + read·cr + write·cw) / 1_000_000
cost       = (token_cost + quantity·unit_price) · pricing_multiplier
cost_micros = round_half_up(cost · 1_000_000)
```

Cache-read and cache-write tokens are **subtracted from** the input count before pricing, so they are never charged twice.

## The two hooks around a provider call

```python
require_model_balance(session, user_id, config)   # BEFORE — may raise 402
...                                                # provider call
record_usage(user_id, config, feature, started_at, usage, quantity)   # AFTER
```

- `require_model_balance` only gates **official** configurations, exempts `superAdmin`, and raises `402` when `balance_micros <= 0`. It is a gate, not a reservation: a single call can push a balance negative-in-spirit, which is why the decrement floors at zero.
- `record_usage` prices the call, writes a `usage_logs` row, and — for official configs only — decrements the balance with an **atomic SQL expression** (`max(0, balance_micros - cost)`), so concurrent requests cannot clobber each other. `superAdmin` is excluded in the same `WHERE`.

**A usage log stores a snapshot of the prices**, not a reference to the config. Editing a model's price later must not rewrite history; `pricing_json` plus the individual columns preserve what was charged at the time.

Add both hooks whenever you introduce a new provider-backed feature. The `feature` string is truncated to 40 chars and is what the usage dashboard groups by.

## Topping up

`RedemptionCode` rows carry `amount_micros`, an expiry, and audit fields (`created_by_user_id`, `redeemed_by_user_id`, `redeemed_at`). Redemption is an atomic conditional `UPDATE` with a `rowcount` check, so a code cannot be redeemed twice: unknown → `404`, already redeemed → `409`, expired → `410`. Codes are created by a super admin with a validity of 1, 7, or 30 days.

## Reporting

- Per-user: `GET /api/usage/logs` with `feature`/`days`/`source` filters, returning a `summary` (calls, input tokens, output tokens, `costMicros`) plus up to 500 rows. Config names are joined in with an outer join so a deleted configuration still shows its logs.
- Admin: `GET /api/admin/usage-logs` with username search and pagination.

## Rules when extending

1. **Never move money through a float**, on either side of the wire.
2. **Never recompute a historical cost** from current prices — read the snapshot on the log row.
3. **Meter personal configs too.** They are free, but the usage dashboard is the only place a user sees what their own keys are spending.
4. **Charge after success, gate before.** A failed provider call should not deduct balance; record the failure without a cost rather than charging for nothing.
5. **`superAdmin` is exempt in both directions** — no gate, no deduction. A regression here is invisible until an admin's balance quietly drains; there is a regression test for it.
6. Validate prices as finite and non-negative (`_number`) and reject `pricing_multiplier <= 0` at the edge. The admin form keeps price inputs as **strings** in component state and converts on save, so a field can be cleared without snapping back to `0`.

## Known gaps

- No invoicing, no currency field, no tax handling — `micros` are unit-less by design.
- No spend alerts or budget caps; the only control is the `402` at zero balance.
- Balance is floored at zero rather than blocking mid-run, so a long generation run can end up costing more than the remaining balance.
