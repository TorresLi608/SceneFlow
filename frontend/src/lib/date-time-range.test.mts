import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node's type stripping executes this TypeScript source directly.
import { dateWithTime, formatDateTime, isTodayTimeRange, timeRangeParams, todayTimeRange } from "./date-time-range.ts";

test("ranges preserve local day boundaries and exact seconds across time zones", () => {
  const previousTZ = process.env.TZ;
  try {
    process.env.TZ = "Asia/Shanghai";
    const range = todayTimeRange(new Date(2026, 8, 8, 18, 26, 14));
    assert.equal(formatDateTime(range.from), "2026-09-08 00:00:00");
    assert.equal(formatDateTime(range.to), "2026-09-08 23:59:59");
    assert.deepEqual(timeRangeParams(range), {
      startTime: "2026-09-07T16:00:00.000Z",
      endTime: "2026-09-08T15:59:59.000Z",
    });
    assert.equal(isTodayTimeRange(todayTimeRange()), true);
    assert.equal(isTodayTimeRange({ ...range, to: range.from }), false);
    assert.equal(formatDateTime(dateWithTime(range.from, "18:26:14")!), "2026-09-08 18:26:14");
    assert.equal(formatDateTime(dateWithTime(range.from, "18:26")!), "2026-09-08 18:26:00");
    for (const invalid of ["", "24:00:00", "18:60:00", "18:26:60"]) {
      assert.equal(dateWithTime(range.from, invalid), null);
    }
    assert.equal(dateWithTime(undefined, "00:00:00"), null);

    process.env.TZ = "America/New_York";
    const spring = todayTimeRange(new Date(2026, 2, 8, 12));
    const fall = todayTimeRange(new Date(2026, 10, 1, 12));
    assert.equal((spring.to.getTime() - spring.from.getTime()) / 1000, 23 * 3600 - 1);
    assert.equal((fall.to.getTime() - fall.from.getTime()) / 1000, 25 * 3600 - 1);
    assert.equal(dateWithTime(spring.from, "02:30:00"), null);
  } finally {
    if (previousTZ === undefined) delete process.env.TZ;
    else process.env.TZ = previousTZ;
  }
});
