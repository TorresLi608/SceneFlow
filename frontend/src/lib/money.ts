import Decimal from "decimal.js";

export function formatMicros(micros: Decimal.Value, fractionDigits = 2) {
  return new Decimal(micros).div(1_000_000).toFixed(fractionDigits);
}

export function formatMoney(micros: Decimal.Value, fractionDigits = 2) {
  return `$${formatMicros(micros, fractionDigits)}`;
}

export function isZeroDecimal(value: Decimal.Value) {
  return new Decimal(value).isZero();
}
