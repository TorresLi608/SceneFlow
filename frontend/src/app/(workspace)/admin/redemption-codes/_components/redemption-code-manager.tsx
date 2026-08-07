"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeDollarSign, Loader2, Plus, RotateCcw, X } from "lucide-react";
import { useMemo, useState } from "react";

import { createRedemptionCodeAction, listRedemptionCodesAction } from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "@/components/ui/toast";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { formatMoney } from "@/lib/money";
import type { InvitationCodeDays, RedemptionCodeStatus } from "@/types/admin";

const pageSize = 10;
const statusVariant: Record<RedemptionCodeStatus, "default" | "destructive" | "outline"> = {
  unused: "outline",
  expired: "destructive",
  redeemed: "default",
};

export function RedemptionCodeManager() {
  const { t, formatDateTime } = useI18n();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<RedemptionCodeStatus | "all">("all");
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [amount, setAmount] = useState("");
  const [days, setDays] = useState<InvitationCodeDays>(7);
  const statusItems = useMemo(
    () => [
      { value: "all", label: t("common.all") },
      { value: "unused", label: t("admin.redemptionStatus.unused") },
      { value: "redeemed", label: t("admin.redemptionStatus.redeemed") },
      { value: "expired", label: t("admin.redemptionStatus.expired") },
    ],
    [t]
  );
  const dayItems = useMemo(
    () => ([1, 7, 30] as const).map((value) => ({ value: String(value), label: t("admin.validityDays", { days: value }) })),
    [t]
  );
  const codesQuery = useQuery({
    queryKey: queryKeys.redemptionCodes(status, page),
    queryFn: () => listRedemptionCodesAction({ status, page, pageSize }),
  });
  const createMutation = useMutation({
    mutationFn: createRedemptionCodeAction,
    onSuccess: async () => {
      setCreateOpen(false);
      setAmount("");
      toast.add({ title: t("admin.redemptionCodeCreated"), type: "success" });
      await queryClient.invalidateQueries({ queryKey: ["redemption-codes"] });
    },
    onError: (error) => toast.add({ title: resolveRequestError(error, t("admin.createRedemptionCodeFailed")), type: "error", priority: "high" }),
  });
  const pagination = codesQuery.data?.pagination ?? { total: 0, page, pageSize, pageCount: 1 };

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{t("admin.redemptionCodes")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("admin.redemptionCodesDescription")}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}><Plus data-icon="inline-start" />{t("admin.createRedemptionCode")}</Button>
      </div>

      <div className="flex justify-end gap-2 rounded-lg border bg-muted/20 p-3">
        <Select items={statusItems} value={status} onValueChange={(value) => { setStatus((value ?? "all") as RedemptionCodeStatus | "all"); setPage(1); }}>
          <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent><SelectGroup>{statusItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup></SelectContent>
        </Select>
        {status !== "all" ? (
          <Button variant="outline" onClick={() => { setStatus("all"); setPage(1); }}>
            <RotateCcw data-icon="inline-start" />
            {t("common.clearFilters")}
          </Button>
        ) : null}
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table className="min-w-[1200px]">
          <TableHeader>
            <TableRow>
              <TableHead>{t("admin.redemptionCode")}</TableHead>
              <TableHead>{t("admin.status")}</TableHead>
              <TableHead>{t("admin.redemptionAmount")}</TableHead>
              <TableHead>{t("admin.redeemedBy")}</TableHead>
              <TableHead>{t("admin.redeemedAt")}</TableHead>
              <TableHead>{t("admin.createdBy")}</TableHead>
              <TableHead>{t("admin.tableCreatedAt")}</TableHead>
              <TableHead>{t("admin.expiresAt")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {codesQuery.data?.redemptionCodes.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-mono font-medium tracking-wide">{item.code}</TableCell>
                <TableCell><Badge variant={statusVariant[item.status]}>{t(`admin.redemptionStatus.${item.status}`)}</Badge></TableCell>
                <TableCell className="font-medium tabular-nums">{formatMoney(item.amountMicros)}</TableCell>
                <TableCell>{item.redeemedBy?.username ?? "—"}</TableCell>
                <TableCell className="text-muted-foreground">{item.redeemedAt ? formatDateTime(item.redeemedAt) : "—"}</TableCell>
                <TableCell>{item.createdBy?.username ?? "—"}</TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(item.createdAt)}</TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(item.expiresAt)}</TableCell>
              </TableRow>
            ))}
            {codesQuery.isLoading ? <TableRow><TableCell colSpan={8} className="py-8 text-center text-muted-foreground">{t("common.loading")}</TableCell></TableRow> : null}
            {!codesQuery.isLoading && !codesQuery.data?.redemptionCodes.length ? <TableRow><TableCell colSpan={8} className="py-8 text-center text-muted-foreground">{t("admin.noRedemptionCodes")}</TableCell></TableRow> : null}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
        <span>{t("admin.pagination", { total: pagination.total, page: pagination.page, pageCount: pagination.pageCount })}</span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>{t("common.previous")}</Button>
          <Button variant="outline" size="sm" disabled={page >= pagination.pageCount} onClick={() => setPage((value) => value + 1)}>{t("common.next")}</Button>
        </div>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("admin.createRedemptionCode")}</DialogTitle>
            <DialogDescription>{t("admin.createRedemptionCodeDescription")}</DialogDescription>
          </DialogHeader>
          <form className="flex flex-col gap-4" onSubmit={(event) => { event.preventDefault(); createMutation.mutate({ amount, days }); }}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="redemptionAmount">{t("admin.redemptionAmount")}</FieldLabel>
                <Input id="redemptionAmount" type="number" min="0.01" max="1000000" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} required />
              </Field>
              <Field>
                <FieldLabel htmlFor="redemptionDays">{t("admin.invitationValidity")}</FieldLabel>
                <Select items={dayItems} value={String(days)} onValueChange={(value) => setDays(Number(value) as InvitationCodeDays)}>
                  <SelectTrigger id="redemptionDays"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectGroup>{dayItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup></SelectContent>
                </Select>
              </Field>
            </FieldGroup>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}><X data-icon="inline-start" />{t("common.cancel")}</Button>
              <Button type="submit" disabled={createMutation.isPending || !amount}>
                {createMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <BadgeDollarSign data-icon="inline-start" />}
                {createMutation.isPending ? t("common.loading") : t("admin.createRedemptionCode")}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
