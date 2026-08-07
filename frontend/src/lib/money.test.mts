import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node's type stripping executes this TypeScript source directly.
import { formatMicros, formatMoney } from "./money.ts";

test("formats micros without JavaScript number precision loss", () => {
  assert.equal(formatMoney("9007199254740993", 6), "$9007199254.740993");
  assert.equal(formatMicros("12500000"), "12.50");
});
