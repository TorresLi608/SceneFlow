"use client";

import { useQuery } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useState } from "react";

import { listUsageLogsAction } from "@/actions/usage-actions";
import { queryKeys } from "@/actions/query-keys";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/lib/i18n";
import { formatMoney } from "@/lib/money";
import { providerLabel } from "@/lib/model-providers";
import type { UsageLogItem } from "@/types/usage";

const featureValues = ["all", "chat", "image", "video", "agent_image", "script_parse", "script_optimize", "storyboard_image"];
const dayValues = ["7", "30", "90"];
type UsageSource = "all" | "official" | "user";

function number(value: number) {
  return new Intl.NumberFormat().format(value);
}

export default function UsagePage() {
  const { t, formatDateTime } = useI18n();
  const [feature, setFeature] = useState("all");
  const [days, setDays] = useState(30);
  const [source, setSource] = useState<UsageSource>("all");
  const query = useQuery({
    queryKey: [...queryKeys.usageLogs, feature, days, source],
    queryFn: () => listUsageLogsAction(feature, days, source),
  });
  const summary = query.data?.summary ?? { calls: 0, inputTokens: 0, outputTokens: 0, costMicros: 0 };
  const logs = query.data?.logs ?? [];
  const featureLabel = (value: string) => t(`usage.feature.${value}`);
  const featureItems = featureValues.map((value) => ({ value, label: featureLabel(value) }));
  const dayItems = dayValues.map((value) => ({ value, label: t("usage.days", { days: Number(value) }) }));
  const sourceItems = [
    { value: "all", label: t("common.all") },
    { value: "official", label: t("config.source.official") },
    { value: "user", label: t("config.source.user") },
  ];
  const filtersActive = feature !== "all" || days !== 30 || source !== "all";

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{t("usage.title")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("usage.description")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select items={featureItems} value={feature} onValueChange={(value) => setFeature(value ?? "all")}>
            <SelectTrigger className="w-40"><SelectValue>{featureLabel(feature)}</SelectValue></SelectTrigger>
            <SelectContent>
              <SelectGroup>{featureValues.map((value) => <SelectItem key={value} value={value}>{featureLabel(value)}</SelectItem>)}</SelectGroup>
            </SelectContent>
          </Select>
          <Select items={sourceItems} value={source} onValueChange={(value) => setSource((value ?? "all") as UsageSource)}>
            <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectGroup>{sourceItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup>
            </SelectContent>
          </Select>
          <Select items={dayItems} value={String(days)} onValueChange={(value) => setDays(Number(value))}>
            <SelectTrigger className="w-28"><SelectValue>{t("usage.days", { days })}</SelectValue></SelectTrigger>
            <SelectContent>
              <SelectGroup>{dayItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup>
            </SelectContent>
          </Select>
          {filtersActive ? (
            <Button variant="outline" size="sm" onClick={() => { setFeature("all"); setSource("all"); setDays(30); }}>
              <RotateCcw data-icon="inline-start" />
              {t("common.clearFilters")}
            </Button>
          ) : null}
        </div>
      </div>

      <div className="mt-5 grid divide-y rounded-lg border border-border/70 bg-muted/10 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <Summary label={t("usage.calls")} value={number(summary.calls)} />
        <Summary label={t("usage.totalTokens")} value={number(summary.inputTokens + summary.outputTokens)} />
        <Summary label={t("usage.totalCost")} value={formatMoney(summary.costMicros, 6)} />
      </div>

      <div className="mt-4 overflow-x-auto rounded-lg border border-border/70">
        <table className="w-full min-w-[1180px] text-sm">
          <thead className="bg-muted/40 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">{t("usage.time")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("usage.type")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("usage.source")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("usage.model")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("usage.duration")}</th>
              <th className="px-3 py-2 text-right font-medium">{t("usage.input")}</th>
              <th className="px-3 py-2 text-right font-medium">{t("usage.output")}</th>
              <th className="px-3 py-2 text-right font-medium">{t("usage.cost")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("usage.details")}</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((item) => <UsageRow key={item.id} item={item} t={t} formatDateTime={formatDateTime} featureLabel={featureLabel} />)}
            {!query.isLoading && logs.length === 0 ? (
              <tr><td colSpan={9} className="px-3 py-10 text-center text-muted-foreground">{t("usage.empty")}</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return <div className="px-4 py-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-lg font-semibold tabular-nums">{value}</p></div>;
}

function UsageRow({
  item,
  t,
  formatDateTime,
  featureLabel,
}: {
  item: UsageLogItem;
  t: (key: string, params?: Record<string, string | number>) => string;
  formatDateTime: (value: string) => string;
  featureLabel: (value: string) => string;
}) {
  return (
    <tr className="border-t border-border/70 align-top">
      <td className="whitespace-nowrap px-3 py-3">{formatDateTime(item.createdAt)}</td>
      <td className="px-3 py-3">{featureLabel(item.feature)}</td>
      <td className="px-3 py-3">{item.source === "official" ? t("config.source.official") : t("config.source.user")}</td>
      <td className="px-3 py-3"><p className="max-w-52 truncate font-medium">{item.model}</p><p className="mt-1 text-xs text-muted-foreground">{providerLabel(item.provider, t)}</p></td>
      <td className="whitespace-nowrap px-3 py-3 tabular-nums">{(item.durationMs / 1000).toFixed(1)} s</td>
      <td className="px-3 py-3 text-right tabular-nums"><p>{number(item.inputTokens)}</p>{item.cacheReadTokens ? <p className="text-xs text-muted-foreground">{t("usage.cached", { value: number(item.cacheReadTokens) })}</p> : null}</td>
      <td className="px-3 py-3 text-right tabular-nums">{number(item.outputTokens)}</td>
      <td className="px-3 py-3 text-right font-medium tabular-nums">{formatMoney(item.costMicros, 6)}</td>
      <td className="px-3 py-3 text-xs text-muted-foreground">
        <details>
          <summary className="cursor-pointer text-foreground">{t("usage.viewDetails")}</summary>
          <div className="mt-2 min-w-48 space-y-1">
            <p>{t("usage.multiplier")}: {item.pricingMultiplier}x</p>
            <p>{t("usage.inputPrice")}: ${item.inputPricePerMillion} / 1M</p>
            <p>{t("usage.outputPrice")}: ${item.outputPricePerMillion} / 1M</p>
            <p>{t("usage.cacheReadPrice")}: ${item.cacheReadPricePerMillion} / 1M</p>
            <p>{t("usage.cacheWritePrice")}: ${item.cacheWritePricePerMillion} / 1M</p>
            {item.unitPrice ? <p>{t("usage.unitPrice")}: ${item.unitPrice} / {t(`usage.unit.${item.unitName}`)} × {item.quantity}</p> : null}
          </div>
        </details>
      </td>
    </tr>
  );
}
