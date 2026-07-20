"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useState } from "react";

import { createInvitationCodeAction, listInvitationCodesAction } from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { InvitationCodeDays, InvitationCodeStatus } from "@/types/admin";

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
  const [message, setMessage] = useState<string | null>(null);
  const codesQuery = useQuery({ queryKey: queryKeys.invitationCodes, queryFn: listInvitationCodesAction });
  const createMutation = useMutation({
    mutationFn: createInvitationCodeAction,
    onSuccess: async () => {
      setCreateOpen(false);
      setMessage(t("admin.invitationCodeCreated"));
      await queryClient.invalidateQueries({ queryKey: queryKeys.invitationCodes });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("admin.createInvitationCodeFailed"))),
  });

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{t("admin.invitationCodes")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("admin.invitationCodesDescription")}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" />
          {t("admin.createInvitationCode")}
        </Button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border/70">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-muted/40 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">{t("admin.invitationCode")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("admin.status")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("admin.tableCreatedAt")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("admin.expiresAt")}</th>
              <th className="px-3 py-2 text-left font-medium">{t("admin.usedBy")}</th>
            </tr>
          </thead>
          <tbody>
            {codesQuery.data?.invitationCodes.map((item) => (
              <tr key={item.id} className="border-t border-border/70">
                <td className="px-3 py-3 font-mono font-medium tracking-wide">{item.code}</td>
                <td className="px-3 py-3"><Badge variant={statusVariant[item.status]}>{t(`admin.invitationStatus.${item.status}`)}</Badge></td>
                <td className="px-3 py-3 text-muted-foreground">{formatDateTime(item.createdAt)}</td>
                <td className="px-3 py-3 text-muted-foreground">{formatDateTime(item.expiresAt)}</td>
                <td className="px-3 py-3">{item.usedBy?.username ?? "—"}</td>
              </tr>
            ))}
            {codesQuery.isLoading ? <tr><td colSpan={5} className="px-3 py-8 text-center text-muted-foreground">{t("common.loading")}</td></tr> : null}
            {!codesQuery.isLoading && !codesQuery.data?.invitationCodes.length ? <tr><td colSpan={5} className="px-3 py-8 text-center text-muted-foreground">{t("admin.noInvitationCodes")}</td></tr> : null}
          </tbody>
        </table>
      </div>

      {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("admin.createInvitationCode")}</DialogTitle>
            <DialogDescription>{t("admin.createInvitationCodeDescription")}</DialogDescription>
          </DialogHeader>
          <form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); createMutation.mutate(days); }}>
            <div className="space-y-2">
              <Label htmlFor="invitationCodeDays">{t("admin.invitationValidity")}</Label>
              <Select value={String(days)} onValueChange={(value) => setDays(Number(value) as InvitationCodeDays)}>
                <SelectTrigger id="invitationCodeDays"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">{t("admin.validityDays", { days: 1 })}</SelectItem>
                  <SelectItem value="7">{t("admin.validityDays", { days: 7 })}</SelectItem>
                  <SelectItem value="30">{t("admin.validityDays", { days: 30 })}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}><X className="size-4" />{t("common.cancel")}</Button>
              <Button type="submit" disabled={createMutation.isPending}>{createMutation.isPending ? t("common.loading") : t("admin.createInvitationCode")}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
