"use client";

import { useQuery } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useState } from "react";

import { listAdminUsageLogsAction } from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useI18n } from "@/lib/i18n";
import { formatMoney } from "@/lib/money";
import { providerLabel } from "@/lib/model-providers";
import { useUserStore } from "@/store/user-store";

const pageSize = 20;

export default function AdminUsageLogsPage() {
  const { t, formatDateTime } = useI18n();
  const user = useUserStore((state) => state.user);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: queryKeys.adminUsageLogs(search.trim(), page),
    queryFn: () => listAdminUsageLogsAction({ search: search.trim(), page, pageSize }),
    enabled: user?.role === "superAdmin",
  });
  const pagination = query.data?.pagination ?? { total: 0, page, pageSize, pageCount: 1 };

  if (user?.role !== "superAdmin") {
    return <div className="p-6 text-sm text-muted-foreground">{user ? t("home.noAllUsageRecordsPermission") : t("common.loading")}</div>;
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
      <div className="flex min-w-0 flex-col gap-4">
        <div>
          <h2 className="text-base font-semibold">{t("home.allUsageRecords")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("admin.allUsageRecordsDescription")}</p>
        </div>

        <div className="flex gap-2 rounded-lg border bg-muted/20 p-3">
          <Input
            value={search}
            onChange={(event) => { setSearch(event.target.value); setPage(1); }}
            placeholder={t("admin.searchUsageUser")}
            className="max-w-sm"
          />
          {search ? (
            <Button variant="outline" onClick={() => { setSearch(""); setPage(1); }}>
              <RotateCcw data-icon="inline-start" />
              {t("common.clearFilters")}
            </Button>
          ) : null}
        </div>

        <div className="overflow-hidden rounded-lg border">
          <Table className="min-w-[1280px]">
            <TableHeader>
              <TableRow>
                <TableHead>{t("admin.usageUser")}</TableHead>
                <TableHead>{t("usage.time")}</TableHead>
                <TableHead>{t("usage.type")}</TableHead>
                <TableHead>{t("usage.source")}</TableHead>
                <TableHead>{t("usage.configName")}</TableHead>
                <TableHead>{t("usage.model")}</TableHead>
                <TableHead className="text-right">{t("usage.input")}</TableHead>
                <TableHead className="text-right">{t("usage.output")}</TableHead>
                <TableHead className="text-right">{t("usage.cost")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data?.usageLogs.map((item) => (
                <TableRow key={item.id}>
                  <TableCell><p className="font-medium">{item.user.username}</p><p className="text-xs text-muted-foreground">ID {item.user.id}</p></TableCell>
                  <TableCell className="whitespace-nowrap">{formatDateTime(item.createdAt)}</TableCell>
                  <TableCell>{t(`usage.feature.${item.feature}`)}</TableCell>
                  <TableCell><Badge variant={item.source === "official" ? "default" : "secondary"}>{item.source === "official" ? t("config.source.official") : t("config.source.user")}</Badge></TableCell>
                  <TableCell><p className="max-w-40 truncate font-medium">{item.configName || "—"}</p></TableCell>
                  <TableCell><p className="max-w-52 truncate font-medium">{item.model}</p><p className="text-xs text-muted-foreground">{providerLabel(item.provider, t)}</p></TableCell>
                  <TableCell className="text-right tabular-nums">{item.inputTokens.toLocaleString()}</TableCell>
                  <TableCell className="text-right tabular-nums">{item.outputTokens.toLocaleString()}</TableCell>
                  <TableCell className="text-right font-medium tabular-nums">{formatMoney(item.costMicros, 6)}</TableCell>
                </TableRow>
              ))}
              {query.isLoading ? <TableRow><TableCell colSpan={9} className="py-10 text-center text-muted-foreground">{t("common.loading")}</TableCell></TableRow> : null}
              {!query.isLoading && !query.data?.usageLogs.length ? <TableRow><TableCell colSpan={9} className="py-10 text-center text-muted-foreground">{t("admin.noUsageRecords")}</TableCell></TableRow> : null}
            </TableBody>
          </Table>
        </div>

        <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
          <span>{t("admin.pagination", { total: pagination.total, page: pagination.page, pageCount: pagination.pageCount })}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>{t("common.previous")}</Button>
            <Button variant="outline" size="sm" disabled={page >= pagination.pageCount} onClick={() => setPage((value) => value + 1)}>{t("common.next")}</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
