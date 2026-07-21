"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, RotateCcw, X } from "lucide-react";
import { useMemo, useState } from "react";

import { createInvitationCodeAction, listInvitationCodesAction } from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { InvitationCodeDays, InvitationCodeStatus } from "@/types/admin";

const pageSize = 10;
const statusVariant: Record<InvitationCodeStatus, "default" | "destructive" | "outline"> = {
  unused: "outline",
  expired: "destructive",
  used: "default",
};

export function InvitationCodeManager() {
  const { t, formatDateTime } = useI18n();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [days, setDays] = useState<InvitationCodeDays>(7);
  const [status, setStatus] = useState<InvitationCodeStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [message, setMessage] = useState<string | null>(null);
  const statusItems = useMemo(
    () => [
      { value: "all", label: t("common.all") },
      { value: "unused", label: t("admin.invitationStatus.unused") },
      { value: "used", label: t("admin.invitationStatus.used") },
      { value: "expired", label: t("admin.invitationStatus.expired") },
    ],
    [t]
  );
  const dayItems = useMemo(
    () => ([1, 7, 30] as const).map((value) => ({ value: String(value), label: t("admin.validityDays", { days: value }) })),
    [t]
  );
  const codesQuery = useQuery({
    queryKey: queryKeys.invitationCodes(status, search, page),
    queryFn: () => listInvitationCodesAction({ status, search: search.trim(), page, pageSize }),
  });
  const createMutation = useMutation({
    mutationFn: createInvitationCodeAction,
    onSuccess: async () => {
      setCreateOpen(false);
      setMessage(t("admin.invitationCodeCreated"));
      await queryClient.invalidateQueries({ queryKey: ["invitation-codes"] });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("admin.createInvitationCodeFailed"))),
  });
  const pagination = codesQuery.data?.pagination ?? { total: 0, page, pageSize, pageCount: 1 };
  const filtersActive = status !== "all" || Boolean(search.trim());

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{t("admin.invitationCodes")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("admin.invitationCodesDescription")}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus data-icon="inline-start" />
          {t("admin.createInvitationCode")}
        </Button>
      </div>

      <div className="grid gap-3 rounded-lg border bg-muted/20 p-3 md:grid-cols-[minmax(220px,1fr)_180px_auto]">
        <Input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder={t("admin.searchInvitationUser")} />
        <Select items={statusItems} value={status} onValueChange={(value) => { setStatus((value ?? "all") as InvitationCodeStatus | "all"); setPage(1); }}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectGroup>{statusItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup>
          </SelectContent>
        </Select>
        {filtersActive ? (
          <Button variant="outline" onClick={() => { setSearch(""); setStatus("all"); setPage(1); }}>
            <RotateCcw data-icon="inline-start" />
            {t("common.clearFilters")}
          </Button>
        ) : null}
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table className="min-w-[820px]">
          <TableHeader>
            <TableRow>
              <TableHead>{t("admin.invitationCode")}</TableHead>
              <TableHead>{t("admin.status")}</TableHead>
              <TableHead>{t("admin.tableCreatedAt")}</TableHead>
              <TableHead>{t("admin.expiresAt")}</TableHead>
              <TableHead>{t("admin.usedBy")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {codesQuery.data?.invitationCodes.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-mono font-medium tracking-wide">{item.code}</TableCell>
                <TableCell><Badge variant={statusVariant[item.status]}>{t(`admin.invitationStatus.${item.status}`)}</Badge></TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(item.createdAt)}</TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(item.expiresAt)}</TableCell>
                <TableCell>{item.usedBy?.username ?? "—"}</TableCell>
              </TableRow>
            ))}
            {codesQuery.isLoading ? <TableRow><TableCell colSpan={5} className="py-8 text-center text-muted-foreground">{t("common.loading")}</TableCell></TableRow> : null}
            {!codesQuery.isLoading && !codesQuery.data?.invitationCodes.length ? <TableRow><TableCell colSpan={5} className="py-8 text-center text-muted-foreground">{t("admin.noInvitationCodes")}</TableCell></TableRow> : null}
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

      {message ? <Alert><AlertDescription>{message}</AlertDescription></Alert> : null}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("admin.createInvitationCode")}</DialogTitle>
            <DialogDescription>{t("admin.createInvitationCodeDescription")}</DialogDescription>
          </DialogHeader>
          <form className="flex flex-col gap-4" onSubmit={(event) => { event.preventDefault(); createMutation.mutate(days); }}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="invitationCodeDays">{t("admin.invitationValidity")}</FieldLabel>
                <Select items={dayItems} value={String(days)} onValueChange={(value) => setDays(Number(value) as InvitationCodeDays)}>
                  <SelectTrigger id="invitationCodeDays"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectGroup>{dayItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup></SelectContent>
                </Select>
              </Field>
            </FieldGroup>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}><X data-icon="inline-start" />{t("common.cancel")}</Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Plus data-icon="inline-start" />}
                {createMutation.isPending ? t("common.loading") : t("admin.createInvitationCode")}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
