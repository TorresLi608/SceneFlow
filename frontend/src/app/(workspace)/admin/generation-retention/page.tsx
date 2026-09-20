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
import { RETENTION_CATEGORIES, type GenerationRetentionResponse, type GenerationRetentionUpdate, type RetentionCategory } from "@/types/admin";

/** Sidebar label of the menu each window governs, so the admin sees the same names users do. */
const CATEGORY_LABEL_KEY: Record<RetentionCategory, string> = {
  image: "home.images",
  video: "home.videos",
  chat: "home.chat",
  voice: "home.audioGeneration",
};

const CATEGORY_SCOPE_KEY: Record<RetentionCategory, string> = {
  image: "admin.retentionScopeImage",
  video: "admin.retentionScopeVideo",
  chat: "admin.retentionScopeChat",
  voice: "admin.retentionScopeVoice",
};

function parseDays(value: string): number {
  return value.trim() === "" ? Number.NaN : Number(value);
}

export default function AdminGenerationRetentionPage() {
  const { t, formatDateTime } = useI18n();
  const user = useUserStore((state) => state.user);
  const queryClient = useQueryClient();
  // `edited` holds only the fields the user typed into; a field absent here shows the saved
  // window, so a fresh server value never has to be copied into state.
  const [edited, setEdited] = useState<Partial<Record<RetentionCategory, string>>>({});
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const isSuperAdmin = user?.role === "superAdmin";

  const query = useQuery({
    queryKey: queryKeys.generationRetention,
    queryFn: getGenerationRetentionAction,
    enabled: isSuperAdmin,
  });
  const saved = query.data;

  const applyResponse = (data: GenerationRetentionResponse) => {
    queryClient.setQueryData(queryKeys.generationRetention, data);
    setEdited({});
  };

  const saveMutation = useMutation({
    mutationFn: updateGenerationRetentionAction,
    onSuccess: (data) => {
      applyResponse(data);
      setMessage({ kind: "ok", text: t("admin.retentionSaved") });
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

  const maxDays = saved?.maxDays ?? 3650;
  const busy = saveMutation.isPending || sweepMutation.isPending;
  const draftFor = (category: RetentionCategory) => edited[category] ?? (saved ? String(saved.policies[category].retentionDays) : "");
  const isValid = (draft: string) => {
    const parsed = parseDays(draft);
    return Number.isInteger(parsed) && parsed >= 0 && parsed <= maxDays;
  };
  // Only categories the admin changed are sent, so the others cannot be overwritten by a
  // stale value from before another admin saved.
  const changes: GenerationRetentionUpdate = {};
  for (const category of RETENTION_CATEGORIES) {
    const draft = draftFor(category);
    if (saved && draft.trim() !== String(saved.policies[category].retentionDays)) {
      changes[category] = { retentionDays: parseDays(draft) };
    }
  }
  const dirty = Object.keys(changes).length > 0;
  const allValid = RETENTION_CATEGORIES.every((category) => isValid(draftFor(category)));
  const anyWindow = saved ? RETENTION_CATEGORIES.some((category) => saved.policies[category].retentionDays > 0) : false;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!allValid || !dirty || busy) return;
    setMessage(null);
    saveMutation.mutate(changes);
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
      <div className="flex max-w-3xl min-w-0 flex-col gap-4">
        <div>
          <h2 className="text-base font-semibold">{t("home.generationRetention")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("admin.retentionDescription")}</p>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-4 rounded-lg border bg-muted/20 p-4">
          <div className="flex flex-col gap-3">
            {RETENTION_CATEGORIES.map((category) => {
              const draft = draftFor(category);
              const invalid = draft.trim() !== "" && !isValid(draft);
              const policy = saved?.policies[category];
              const inputId = `generation-retention-${category}-days`;
              return (
                <div key={category} className="grid gap-2 rounded-md border bg-background/60 p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                  <div className="flex min-w-0 flex-col gap-1">
                    <Label htmlFor={inputId} className="text-sm font-semibold">
                      {t(CATEGORY_LABEL_KEY[category])}
                    </Label>
                    <p className="text-xs text-muted-foreground">{t(CATEGORY_SCOPE_KEY[category])}</p>
                    <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      <div className="flex gap-1">
                        <dt>{t("admin.retentionCurrent")}:</dt>
                        <dd className="font-medium text-foreground">
                          {query.isLoading || !policy
                            ? t("common.loading")
                            : policy.retentionDays
                              ? t("admin.retentionDaysValue", { days: policy.retentionDays })
                              : t("admin.retentionDisabled")}
                        </dd>
                      </div>
                      <div className="flex gap-1">
                        <dt>{t("admin.retentionExpiredCount")}:</dt>
                        <dd className="font-medium text-foreground">{query.isLoading || !policy ? t("common.loading") : policy.expiredCount}</dd>
                      </div>
                      {policy?.updatedAt ? <div>{t("admin.retentionUpdatedAt", { time: formatDateTime(policy.updatedAt) })}</div> : null}
                    </dl>
                    {invalid ? <p className="text-xs text-destructive">{t("admin.retentionDaysInvalid", { max: maxDays })}</p> : null}
                  </div>
                  <div className="flex items-center gap-2">
                    <Input
                      id={inputId}
                      type="number"
                      inputMode="numeric"
                      min={0}
                      max={maxDays}
                      step={1}
                      value={draft}
                      onChange={(event) => {
                        const value = event.target.value;
                        setEdited((current) => ({ ...current, [category]: value }));
                        setMessage(null);
                      }}
                      disabled={query.isLoading || busy}
                      aria-invalid={invalid}
                      aria-label={`${t(CATEGORY_LABEL_KEY[category])} ${t("admin.retentionDaysLabel")}`}
                      className="w-28"
                    />
                    <span className="text-sm text-muted-foreground">{t("admin.retentionDaysUnit")}</span>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="text-xs text-muted-foreground">{t("admin.retentionDaysHint", { max: maxDays })}</p>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={!allValid || !dirty || busy || query.isLoading}>
              {saveMutation.isPending ? t("common.saving") : t("common.save")}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy || query.isLoading || !anyWindow}
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
