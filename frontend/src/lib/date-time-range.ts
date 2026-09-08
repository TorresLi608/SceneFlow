import dayjs from "dayjs";
import customParseFormat from "dayjs/plugin/customParseFormat.js";

dayjs.extend(customParseFormat);

export type DateTimeRange = { from: Date; to: Date };
export type TimeRangeParams = { startTime: string; endTime: string };

export function todayTimeRange(date = new Date()): DateTimeRange {
  return {
    from: dayjs(date).startOf("day").toDate(),
    to: dayjs(date).endOf("day").startOf("second").toDate(),
  };
}

export function isTodayTimeRange(range: DateTimeRange): boolean {
  const today = todayTimeRange();
  return range.from.getTime() === today.from.getTime() && range.to.getTime() === today.to.getTime();
}

export function timeRangeParams(range: DateTimeRange): TimeRangeParams {
  return { startTime: range.from.toISOString(), endTime: range.to.toISOString() };
}

export function formatDateTime(value: Date | string): string {
  return dayjs(value).format("YYYY-MM-DD HH:mm:ss");
}

export function dateWithTime(date: Date | undefined, time: string): Date | null {
  if (!date) return null;
  // Native time inputs may omit :00 seconds even with step=1.
  const seconds = time.length === 5 ? `${time}:00` : time;
  const parsed = dayjs(`${dayjs(date).format("YYYY-MM-DD")} ${seconds}`, "YYYY-MM-DD HH:mm:ss", true);
  return parsed.isValid() ? parsed.toDate() : null;
}
