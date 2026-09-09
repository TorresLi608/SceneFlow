"use client";

import dayjs from "dayjs";
import { CalendarClock, CalendarDays, Clock } from "lucide-react";
import { useId, useState } from "react";
import type { DateRange } from "react-day-picker";
import { enUS } from "react-day-picker/locale/en-US";
import { zhCN } from "react-day-picker/locale/zh-CN";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { dateWithTime, formatDateTime, todayTimeRange, type DateTimeRange } from "@/lib/date-time-range";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function DateTimeRangePicker({ value, onChange, className }: {
  value: DateTimeRange;
  onChange: (value: DateTimeRange) => void;
  className?: string;
}) {
  const { t, locale } = useI18n();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [dates, setDates] = useState<DateRange | undefined>(value);
  const [startTime, setStartTime] = useState(dayjs(value.from).format("HH:mm:ss"));
  const [endTime, setEndTime] = useState(dayjs(value.to).format("HH:mm:ss"));
  const from = dateWithTime(dates?.from, startTime);
  const to = dateWithTime(dates?.to, endTime);
  const invalidOrder = Boolean(from && to && from > to);
  const error = !dates?.from || !dates.to
    ? t("dateRange.selectDates")
    : !from || !to
      ? t("dateRange.invalidTime")
      : invalidOrder ? t("dateRange.invalidOrder") : null;

  function changeOpen(nextOpen: boolean) {
    if (nextOpen) {
      setDates(value);
      setStartTime(dayjs(value.from).format("HH:mm:ss"));
      setEndTime(dayjs(value.to).format("HH:mm:ss"));
    }
    setOpen(nextOpen);
  }

  return (
    <Popover open={open} onOpenChange={changeOpen}>
      <PopoverTrigger
        aria-label={`${t("dateRange.label")}: ${formatDateTime(value.from)} ~ ${formatDateTime(value.to)}`}
        render={<Button variant="outline" className={cn("h-auto min-h-8 w-full justify-between py-1 sm:w-auto", className)} />}
      >
        <span className="flex flex-wrap items-center gap-x-2 tabular-nums">
          <span>{formatDateTime(value.from)}</span>
          <span aria-hidden="true">~</span>
          <span>{formatDateTime(value.to)}</span>
        </span>
        <CalendarClock data-icon="inline-end" />
      </PopoverTrigger>
      <PopoverContent align="start" aria-label={t("dateRange.label")} className="max-h-(--available-height) w-auto max-w-[calc(100vw-2rem)] gap-0 overflow-y-auto p-0">
        <form onSubmit={(event) => {
          event.preventDefault();
          if (!error && from && to) {
            onChange({ from, to });
            setOpen(false);
          }
        }}>
          <Calendar
            mode="range"
            required
            resetOnSelect
            autoFocus
            captionLayout="dropdown"
            defaultMonth={value.from}
            selected={dates}
            onSelect={setDates}
            numberOfMonths={2}
            weekStartsOn={0}
            locale={locale === "zh" ? zhCN : enUS}
            className="p-3"
          />
          <Separator />
          <FieldGroup className="gap-3 p-3 md:flex-row">
            {([
              { key: "start", date: dates?.from, time: startTime, setTime: setStartTime, valid: from },
              { key: "end", date: dates?.to, time: endTime, setTime: setEndTime, valid: to },
            ] as const).map(({ key, date, time, setTime, valid }) => (
              <Field key={key} className="min-w-0 flex-1" data-invalid={Boolean(date && !valid) || invalidOrder || undefined}>
                <FieldLabel htmlFor={`${id}-${key}`} className="flex items-center justify-between gap-2">
                  <span className="sr-only">{t(`dateRange.${key}Time`)}</span>
                  <span className="flex items-center gap-2 tabular-nums">
                    <CalendarDays className="size-4" aria-hidden="true" />
                    {date ? dayjs(date).format("YYYY-MM-DD") : t(`dateRange.${key}Time`)}
                  </span>
                  <Clock className="size-4 text-muted-foreground" aria-hidden="true" />
                </FieldLabel>
                <Input
                  id={`${id}-${key}`}
                  type="time"
                  step={1}
                  required
                  value={time}
                  aria-invalid={Boolean(date && !valid) || invalidOrder || undefined}
                  aria-describedby={error ? `${id}-error` : undefined}
                  onChange={(event) => setTime(event.target.value)}
                  className="tabular-nums"
                />
              </Field>
            ))}
          </FieldGroup>
          {error ? <FieldDescription id={`${id}-error`} role="status" className="px-3 pb-3">{error}</FieldDescription> : null}
          <Separator />
          <div className="flex items-center justify-between gap-3 p-3">
            <Button type="button" variant="ghost" size="sm" onClick={() => { onChange(todayTimeRange()); setOpen(false); }}>{t("dateRange.today")}</Button>
            <div className="flex gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>{t("common.cancel")}</Button>
              <Button type="submit" size="sm" disabled={Boolean(error)}>{t("common.confirm")}</Button>
            </div>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}
