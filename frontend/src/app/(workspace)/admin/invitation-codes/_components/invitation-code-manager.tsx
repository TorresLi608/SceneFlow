"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Link2, Loader2, Plus, RotateCcw, X } from "lucide-react";
import { useMemo, useState } from "react";

import { createInvitationCodeAction, listInvitationCodesAction } from "@/actions/admin-actions";
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
    onSuccess: async (data) => {
      setCreateOpen(false);
      toast.add({ title: t("admin.invitationCodeCreated"), type: "success" });
      await queryClient.invalidateQueries({ queryKey: ["invitation-codes"] });
      if (data?.invitationCode?.code) {
        handleCopyInviteLink(data.invitationCode.code);
      }
    },
    onError: (error) => toast.add({ title: resolveRequestError(error, t("admin.createInvitationCodeFailed")), type: "error", priority: "high" }),
  });

  const pagination = codesQuery.data?.pagination ?? { total: 0, page, pageSize, pageCount: 1 };
  const filtersActive = status !== "all" || Boolean(search.trim());

  const handleCopyInviteLink = (code: string) => {
    if (typeof window === "undefined") return;
    const url = `${window.location.origin}/register?code=${encodeURIComponent(code)}`;
    navigator.clipboard.writeText(url);
    toast.add({ title: t("admin.invitationLinkCopied"), type: "success" });
  };

  const handleCopyCode = (code: string) => {
    if (typeof window === "undefined") return;
    navigator.clipboard.writeText(code);
    toast.add({ title: t("admin.invitationCodeCopied"), type: "success" });
  };

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{t("admin.invitationCodes")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("admin.invitationCodesDescription")}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)} className="cursor-pointer">
          <Plus className="size-4" />
          {t("admin.createInvitationCode")}
        </Button>
      </div>

      <div className="grid gap-3 rounded-2xl border border-border/80 bg-muted/20 p-3.5 backdrop-blur-md md:grid-cols-[minmax(220px,1fr)_180px_auto]">
        <Input
          value={search}
          onChange={(event) => { setSearch(event.target.value); setPage(1); }}
          placeholder={t("admin.searchInvitationUser")}
          className="h-9 text-xs sm:text-sm"
        />
        <Select
          items={statusItems}
          value={status}
          onValueChange={(value) => { setStatus((value ?? "all") as InvitationCodeStatus | "all"); setPage(1); }}
        >
          <SelectTrigger className="h-9 text-xs sm:text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectGroup>{statusItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup>
          </SelectContent>
        </Select>
        {filtersActive ? (
          <Button variant="outline" size="sm" onClick={() => { setSearch(""); setStatus("all"); setPage(1); }} className="h-9 cursor-pointer">
            <RotateCcw className="size-3.5" />
            {t("common.clearFilters")}
          </Button>
        ) : null}
      </div>

      <div className="overflow-hidden rounded-2xl border border-border/80 bg-card/60 shadow-xs backdrop-blur-md">
        <Table className="min-w-[1080px]">
          <TableHeader>
            <TableRow>
              <TableHead>{t("admin.invitationCode")}</TableHead>
              <TableHead>{t("admin.status")}</TableHead>
              <TableHead>{t("admin.tableCreatedAt")}</TableHead>
              <TableHead>{t("admin.expiresAt")}</TableHead>
              <TableHead>{t("admin.usedBy")}</TableHead>
              <TableHead>{t("admin.usedAt")}</TableHead>
              <TableHead>{t("admin.createdBy")}</TableHead>
              <TableHead className="text-right">{t("admin.tableActions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {codesQuery.data?.invitationCodes.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-mono font-semibold tracking-wide">
                  <div className="flex items-center gap-2">
                    <span>{item.code}</span>
                    <button
                      type="button"
                      onClick={() => handleCopyCode(item.code)}
                      className="inline-flex size-6 items-center justify-center rounded-md text-muted-foreground transition hover:bg-muted hover:text-foreground cursor-pointer"
                      title={t("admin.copyInvitationCode")}
                    >
                      <Copy className="size-3.5" />
                    </button>
                  </div>
                </TableCell>
                <TableCell><Badge variant={statusVariant[item.status]}>{t(`admin.invitationStatus.${item.status}`)}</Badge></TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(item.createdAt)}</TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(item.expiresAt)}</TableCell>
                <TableCell>{item.usedBy?.username ?? "—"}</TableCell>
                <TableCell className="text-muted-foreground">{item.usedAt ? formatDateTime(item.usedAt) : "—"}</TableCell>
                <TableCell>{item.createdBy?.username ?? "—"}</TableCell>
                <TableCell className="text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 gap-1.5 text-xs font-medium cursor-pointer"
                    onClick={() => handleCopyInviteLink(item.code)}
                    title={t("admin.copyInvitationLink")}
                  >
                    <Link2 className="size-3.5 text-primary" />
                    {t("admin.copyInvitationLink")}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {codesQuery.isLoading ? (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                  {t("common.loading")}
                </TableCell>
              </TableRow>
            ) : null}
            {!codesQuery.isLoading && !codesQuery.data?.invitationCodes.length ? (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                  {t("admin.noInvitationCodes")}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
        <span>{t("admin.pagination", { total: pagination.total, page: pagination.page, pageCount: pagination.pageCount })}</span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} className="cursor-pointer">{t("common.previous")}</Button>
          <Button variant="outline" size="sm" disabled={page >= pagination.pageCount} onClick={() => setPage((value) => value + 1)} className="cursor-pointer">{t("common.next")}</Button>
        </div>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("admin.createInvitationCode")}</DialogTitle>
            <DialogDescription>{t("admin.createInvitationCodeDescription")}</DialogDescription>
          </DialogHeader>
          <form className="flex flex-col gap-4" onSubmit={(event) => { event.preventDefault(); createMutation.mutate(days); }}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="invitationCodeDays">
                  {t("admin.invitationValidity")}
                  <span className="ml-1 font-bold text-destructive" title="必填项">*</span>
                </FieldLabel>
                <Select items={dayItems} value={String(days)} onValueChange={(value) => setDays(Number(value) as InvitationCodeDays)}>
                  <SelectTrigger id="invitationCodeDays"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectGroup>{dayItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup></SelectContent>
                </Select>
              </Field>
            </FieldGroup>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)} className="cursor-pointer">
                <X className="size-4" />
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={createMutation.isPending} className="cursor-pointer">
                {createMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                {createMutation.isPending ? t("common.loading") : t("admin.createInvitationCode")}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
