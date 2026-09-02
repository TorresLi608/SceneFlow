"use client";

import { useQuery } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useState } from "react";

import { listAdminErrorLogsAction } from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";

const pageSize = 20;

export default function AdminErrorLogsPage() {
  const { t, formatDateTime } = useI18n();
  const user = useUserStore((state) => state.user);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: queryKeys.adminErrorLogs(search.trim(), page),
    queryFn: () => listAdminErrorLogsAction({ search: search.trim(), page, pageSize }),
    enabled: user?.role === "superAdmin",
  });
  const pagination = query.data?.pagination ?? { total: 0, page, pageSize, pageCount: 1 };

  if (user?.role !== "superAdmin") {
    return <div className="p-6 text-sm text-muted-foreground">{user ? t("home.noErrorLogsPermission") : t("common.loading")}</div>;
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
      <div className="flex min-w-0 flex-col gap-4">
        <div>
          <h2 className="text-base font-semibold">{t("home.errorLogs")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("admin.errorLogsDescription")}</p>
        </div>

        <div className="flex gap-2 border bg-muted/20 p-3">
          <Input
            value={search}
            onChange={(event) => { setSearch(event.target.value); setPage(1); }}
            placeholder={t("admin.searchErrorLogs")}
            className="max-w-lg"
          />
          {search ? (
            <Button variant="outline" onClick={() => { setSearch(""); setPage(1); }}>
              <RotateCcw data-icon="inline-start" />
              {t("common.clearFilters")}
            </Button>
          ) : null}
        </div>

        <div className="overflow-hidden border">
          <Table className="min-w-[1180px]">
            <TableHeader>
              <TableRow>
                <TableHead>{t("usage.time")}</TableHead>
                <TableHead>{t("admin.errorCode")}</TableHead>
                <TableHead>{t("admin.errorRequest")}</TableHead>
                <TableHead>{t("admin.errorResource")}</TableHead>
                <TableHead>{t("admin.errorMessage")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data?.errorLogs.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="whitespace-nowrap">{formatDateTime(item.createdAt)}</TableCell>
                  <TableCell><Badge variant="destructive">{item.errorCode}</Badge><p className="mt-1 text-xs text-muted-foreground">{t("admin.httpStatus", { status: item.statusCode })}</p></TableCell>
                  <TableCell><p className="font-mono text-xs">{item.requestId}</p><p className="mt-1 max-w-72 truncate text-xs text-muted-foreground">{item.method} {item.route}</p></TableCell>
                  <TableCell><p className="font-mono text-xs">{item.projectId || "-"}</p><p className="mt-1 font-mono text-xs text-muted-foreground">{item.episodeId || "-"}</p></TableCell>
                  <TableCell className="max-w-md whitespace-normal text-sm">{item.message}</TableCell>
                </TableRow>
              ))}
              {query.isLoading ? <TableRow><TableCell colSpan={5} className="py-10 text-center text-muted-foreground">{t("common.loading")}</TableCell></TableRow> : null}
              {!query.isLoading && !query.data?.errorLogs.length ? <TableRow><TableCell colSpan={5} className="py-10 text-center text-muted-foreground">{t("admin.noErrorLogs")}</TableCell></TableRow> : null}
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
