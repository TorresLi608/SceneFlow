"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { getGenerationRetentionAction, sweepGenerationRetentionAction, updateGenerationRetentionAction } from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";
import type { GenerationRetentionResponse } from "@/types/admin";

export default function AdminGenerationRetentionPage() {
  const { t, formatDateTime } = useI18n();
  const user = useUserStore((state) => state.user);
  const queryClient = useQueryClient();
  // `edited` is the user's unsaved input; while null the field shows the saved policy, so a
  // fresh server value never has to be copied into state.
  const [edited, setEdited] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const isSuperAdmin = user?.role === "superAdmin";

  const query = useQuery({
    queryKey: queryKeys.generationRetention,
    queryFn: getGenerationRetentionAction,
    enabled: isSuperAdmin,
  });
  const saved = query.data;
  const draft = edited ?? (saved ? String(saved.retentionDays) : "");

  const applyResponse = (data: GenerationRetentionResponse) => {
    queryClient.setQueryData(queryKeys.generationRetention, data);
    setEdited(null);
  };

  const saveMutation = useMutation({
    mutationFn: updateGenerationRetentionAction,
    onSuccess: (data) => {
      applyResponse(data);
      setMessage({ kind: "ok", text: data.retentionDays === 0 ? t("admin.retentionSavedDisabled") : t("admin.retentionSaved", { days: data.retentionDays }) });
    },
    onError: (error) => setMessage({ kind: "error", text: resolveRequestError(error, t("admin.retentionSaveFailed")) }),
  });

  const sweepMutation = useMutation({
    mutationFn: sweepGenerationRetentionAction,
    onSuccess: (data) => {
      applyResponse(data);
      setMessage({ kind: "ok", text: t("admin.retentionSwept", { count: data.removedCount ?? 0 }) });
    },
    onError: (error) => setMessage({ kind: "error", text: resolveRequestError(error, t("admin.retentionSweepFailed")) }),
  });

  if (!isSuperAdmin) {
    return <div className="p-6 text-sm text-muted-foreground">{user ? t("home.noAdminPermission") : t("common.loading")}</div>;
  }

  const parsed = draft.trim() === "" ? Number.NaN : Number(draft);
  const maxDays = saved?.maxDays ?? 3650;
  const draftValid = Number.isInteger(parsed) && parsed >= 0 && parsed <= maxDays;
  const dirty = saved ? draft.trim() !== String(saved.retentionDays) : false;
  const busy = saveMutation.isPending || sweepMutation.isPending;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draftValid || !dirty || busy) return;
    setMessage(null);
    saveMutation.mutate(parsed);
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
      <div className="flex max-w-2xl min-w-0 flex-col gap-4">
        <div>
          <h2 className="text-base font-semibold">{t("home.generationRetention")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("admin.retentionDescription")}</p>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-4 rounded-lg border bg-muted/20 p-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="generation-retention-days">{t("admin.retentionDaysLabel")}</Label>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                id="generation-retention-days"
                type="number"
                inputMode="numeric"
                min={0}
                max={maxDays}
                step={1}
                value={draft}
                onChange={(event) => { setEdited(event.target.value); setMessage(null); }}
                disabled={query.isLoading || busy}
                aria-invalid={draft.trim() !== "" && !draftValid}
                className="w-40"
              />
              <span className="text-sm text-muted-foreground">{t("admin.retentionDaysUnit")}</span>
            </div>
            <p className="text-xs text-muted-foreground">{t("admin.retentionDaysHint", { max: maxDays })}</p>
            {draft.trim() !== "" && !draftValid ? (
              <p className="text-xs text-destructive">{t("admin.retentionDaysInvalid", { max: maxDays })}</p>
            ) : null}
          </div>

          <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
            <div className="rounded-md border bg-background/60 p-3">
              <dt className="text-xs text-muted-foreground">{t("admin.retentionCurrent")}</dt>
              <dd className="mt-1 font-medium">
                {query.isLoading ? t("common.loading") : saved?.retentionDays ? t("admin.retentionDaysValue", { days: saved.retentionDays }) : t("admin.retentionDisabled")}
              </dd>
            </div>
            <div className="rounded-md border bg-background/60 p-3">
              <dt className="text-xs text-muted-foreground">{t("admin.retentionExpiredCount")}</dt>
              <dd className="mt-1 font-medium">{query.isLoading ? t("common.loading") : (saved?.expiredCount ?? 0)}</dd>
            </div>
          </dl>
          {saved?.updatedAt ? (
            <p className="text-xs text-muted-foreground">{t("admin.retentionUpdatedAt", { time: formatDateTime(saved.updatedAt) })}</p>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={!draftValid || !dirty || busy || query.isLoading}>
              {saveMutation.isPending ? t("common.saving") : t("common.save")}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy || query.isLoading || !saved?.retentionDays}
              onClick={() => { setMessage(null); sweepMutation.mutate(); }}
              title={t("admin.retentionSweepHint")}
            >
              <Trash2 data-icon="inline-start" />
              {sweepMutation.isPending ? t("admin.retentionSweeping") : t("admin.retentionSweepNow")}
            </Button>
          </div>
          {message ? (
            <p className={message.kind === "ok" ? "text-sm text-emerald-600" : "text-sm text-destructive"} role="status">
              {message.text}
            </p>
          ) : null}
          {query.isError ? <p className="text-sm text-destructive">{t("admin.retentionLoadFailed")}</p> : null}
        </form>

        <p className="text-xs text-muted-foreground">{t("admin.retentionScopeNote")}</p>
      </div>
    </div>
  );
}
