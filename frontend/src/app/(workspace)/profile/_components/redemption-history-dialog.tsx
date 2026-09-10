"use client";

import { useQuery } from "@tanstack/react-query";
import { History, RotateCcw } from "lucide-react";
import { useState } from "react";

import { queryKeys } from "@/actions/query-keys";
import { listRedemptionHistoryAction } from "@/actions/user-actions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { formatMoney } from "@/lib/money";
import { useUserStore } from "@/store/user-store";

const pageSize = 10;

export function RedemptionHistoryDialog() {
  const { t, formatDateTime } = useI18n();
  const userId = useUserStore((state) => state.user?.id);
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const historyQuery = useQuery({
    queryKey: [...queryKeys.redemptionHistory, userId, page],
    queryFn: () => listRedemptionHistoryAction({ page, pageSize }),
    enabled: open && !!userId,
  });
  const pagination = historyQuery.data?.pagination;

  return (
    <Dialog open={open} onOpenChange={(value) => { setOpen(value); if (value) setPage(1); }}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <History data-icon="inline-start" />
        {t("profile.redemptionHistory")}
      </DialogTrigger>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t("profile.redemptionHistory")}</DialogTitle>
          <DialogDescription>{t("profile.redemptionHistoryDescription")}</DialogDescription>
        </DialogHeader>

        {historyQuery.isError ? (
          <Alert>
            <AlertTitle>{t("profile.redemptionHistoryFailed")}</AlertTitle>
            <AlertDescription>{resolveRequestError(historyQuery.error, t("profile.redemptionHistoryFailed"))}</AlertDescription>
            <Button variant="outline" size="sm" className="justify-self-start" disabled={historyQuery.isFetching} onClick={() => void historyQuery.refetch()}>
              <RotateCcw data-icon="inline-start" />
              {t("common.retry")}
            </Button>
          </Alert>
        ) : null}

        <Table aria-label={t("profile.redemptionHistory")} aria-busy={historyQuery.isFetching}>
          <TableHeader>
            <TableRow>
              <TableHead>{t("profile.redeemedAt")}</TableHead>
              <TableHead>{t("profile.redeemCode")}</TableHead>
              <TableHead className="text-right">{t("profile.redeemedAmount")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {historyQuery.data?.redemptions.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="whitespace-nowrap">{formatDateTime(item.redeemedAt)}</TableCell>
                <TableCell className="font-mono whitespace-nowrap">{item.code}</TableCell>
                <TableCell className="text-right whitespace-nowrap tabular-nums">{formatMoney(item.amountMicros, 6)}</TableCell>
              </TableRow>
            ))}
            {historyQuery.isPending ? (
              <TableRow><TableCell colSpan={3} className="py-8 text-center text-muted-foreground">{t("common.loading")}</TableCell></TableRow>
            ) : historyQuery.isSuccess && !historyQuery.data.redemptions.length ? (
              <TableRow><TableCell colSpan={3} className="py-8 text-center text-muted-foreground">{t("profile.noRedemptions")}</TableCell></TableRow>
            ) : null}
          </TableBody>
        </Table>

        {pagination ? (
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
            <span aria-live="polite">{t("admin.pagination", { total: pagination.total, page: pagination.page, pageCount: pagination.pageCount })}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={historyQuery.isFetching || page <= 1} onClick={() => setPage((value) => value - 1)}>{t("common.previous")}</Button>
              <Button variant="outline" size="sm" disabled={historyQuery.isFetching || page >= pagination.pageCount} onClick={() => setPage((value) => value + 1)}>{t("common.next")}</Button>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
