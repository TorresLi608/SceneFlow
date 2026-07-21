export function formatMoney(micros: number, fractionDigits = 2) {
  return `$${(micros / 1_000_000).toFixed(fractionDigits)}`;
}
