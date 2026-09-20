"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Clock,
  History,
  Image as ImageIcon,
  Layers,
  MessageSquare,
  Mic,
  RotateCcw,
  ShieldCheck,
  Trash2,
  Video as VideoIcon,
} from "lucide-react";
import { useState, type FormEvent } from "react";

import {
  getGenerationRetentionAction,
  sweepGenerationRetentionAction,
  updateGenerationRetentionAction,
} from "@/actions/admin-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useUserStore } from "@/store/user-store";
import {
  RETENTION_CATEGORIES,
  type GenerationRetentionResponse,
  type GenerationRetentionUpdate,
  type RetentionCategory,
} from "@/types/admin";

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

const CATEGORY_ICONS: Record<
  RetentionCategory,
  {
    icon: typeof ImageIcon;
    badgeStyle: string;
  }
> = {
  image: {
    icon: ImageIcon,
    badgeStyle: "bg-indigo-500/10 text-indigo-500 dark:text-indigo-400 border-indigo-500/20",
  },
  video: {
    icon: VideoIcon,
    badgeStyle: "bg-rose-500/10 text-rose-500 dark:text-rose-400 border-rose-500/20",
  },
  chat: {
    icon: MessageSquare,
    badgeStyle: "bg-emerald-500/10 text-emerald-500 dark:text-emerald-400 border-emerald-500/20",
  },
  voice: {
    icon: Mic,
    badgeStyle: "bg-amber-500/10 text-amber-500 dark:text-amber-400 border-amber-500/20",
  },
};

const PRESET_OPTIONS = [0, 7, 30, 90, 180] as const;

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
  const [confirmSweepOpen, setConfirmSweepOpen] = useState(false);
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
      toast.add({
        title: t("admin.retentionSaved"),
        type: "success",
      });
    },
    onError: (error) => {
      toast.add({
        title: resolveRequestError(error, t("admin.retentionSaveFailed")),
        type: "error",
        priority: "high",
      });
    },
  });

  const sweepMutation = useMutation({
    mutationFn: sweepGenerationRetentionAction,
    onSuccess: (data) => {
      applyResponse(data);
      setConfirmSweepOpen(false);
      toast.add({
        title: t("admin.retentionSwept", { count: data.removedCount ?? 0 }),
        type: "success",
      });
    },
    onError: (error) => {
      setConfirmSweepOpen(false);
      toast.add({
        title: resolveRequestError(error, t("admin.retentionSweepFailed")),
        type: "error",
        priority: "high",
      });
    },
  });

  if (!isSuperAdmin) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {user ? t("home.noAdminPermission") : t("common.loading")}
      </div>
    );
  }

  const maxDays = saved?.maxDays ?? 3650;
  const busy = saveMutation.isPending || sweepMutation.isPending;

  const draftFor = (category: RetentionCategory) =>
    edited[category] ?? (saved ? String(saved.policies[category].retentionDays) : "");

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

  const dirtyCount = Object.keys(changes).length;
  const dirty = dirtyCount > 0;
  const allValid = RETENTION_CATEGORIES.every((category) => isValid(draftFor(category)));
  const anyWindow = saved
    ? RETENTION_CATEGORIES.some((category) => saved.policies[category].retentionDays > 0)
    : false;

  // Overview metrics
  const activeCount = saved
    ? RETENTION_CATEGORIES.filter((category) => saved.policies[category].retentionDays > 0).length
    : 0;
  const totalExpiredCount = saved
    ? RETENTION_CATEGORIES.reduce((acc, cat) => acc + (saved.policies[cat]?.expiredCount ?? 0), 0)
    : 0;

  const handleReset = () => {
    setEdited({});
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!allValid || !dirty || busy) return;
    saveMutation.mutate(changes);
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
      <div className="flex max-w-4xl min-w-0 flex-col gap-6">
        {/* Page Header */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold tracking-tight">{t("home.generationRetention")}</h2>
            <Badge variant="outline" className="text-xs font-normal">
              {t("admin.retentionScopeNote").slice(0, 7)}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">{t("admin.retentionDescription")}</p>
        </div>

        {/* Protected Scope Banner */}
        <div className="flex items-start gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3.5 text-xs text-muted-foreground dark:bg-emerald-500/10">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
          <div className="flex flex-col gap-0.5">
            <span className="font-semibold text-foreground">{t("admin.retentionSafeScopeTitle")}</span>
            <p className="leading-relaxed">{t("admin.retentionSafeScopeContent")}</p>
          </div>
        </div>

        {/* Summary Metric Cards */}
        {query.isLoading ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Skeleton className="h-24 rounded-xl" />
            <Skeleton className="h-24 rounded-xl" />
            <Skeleton className="h-24 rounded-xl" />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Card size="sm" className="bg-background/80 shadow-xs border-border/70">
              <CardHeader className="flex flex-row items-center justify-between pb-1">
                <span className="text-xs font-medium text-muted-foreground">
                  {t("admin.retentionSummaryActive")}
                </span>
                <Layers className="size-4 text-muted-foreground/70" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold tracking-tight">
                  {activeCount} <span className="text-sm font-normal text-muted-foreground">/ 4</span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("admin.retentionSummaryActiveValue", { active: activeCount, total: 4 })}
                </p>
              </CardContent>
            </Card>

            <Card size="sm" className="bg-background/80 shadow-xs border-border/70">
              <CardHeader className="flex flex-row items-center justify-between pb-1">
                <span className="text-xs font-medium text-muted-foreground">
                  {t("admin.retentionSummaryTotalExpired")}
                </span>
                <Trash2
                  className={cn(
                    "size-4",
                    totalExpiredCount > 0 ? "text-amber-500" : "text-muted-foreground/70"
                  )}
                />
              </CardHeader>
              <CardContent>
                <div
                  className={cn(
                    "text-2xl font-bold tracking-tight",
                    totalExpiredCount > 0 && "text-amber-600 dark:text-amber-400"
                  )}
                >
                  {totalExpiredCount}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {totalExpiredCount > 0
                    ? t("admin.retentionExpiredCount")
                    : t("admin.retentionSummaryTotalExpiredEmpty")}
                </p>
              </CardContent>
            </Card>

            <Card size="sm" className="bg-background/80 shadow-xs border-border/70">
              <CardHeader className="flex flex-row items-center justify-between pb-1">
                <span className="text-xs font-medium text-muted-foreground">
                  {t("admin.retentionSummaryInterval")}
                </span>
                <Clock className="size-4 text-muted-foreground/70" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold tracking-tight">1h</div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("admin.retentionSummaryHourly")}
                </p>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Configuration Form & Category Cards */}
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-3">
            {query.isLoading ? (
              <div className="flex flex-col gap-3">
                <Skeleton className="h-44 rounded-xl" />
                <Skeleton className="h-44 rounded-xl" />
                <Skeleton className="h-44 rounded-xl" />
                <Skeleton className="h-44 rounded-xl" />
              </div>
            ) : (
              RETENTION_CATEGORIES.map((category) => {
                const draft = draftFor(category);
                const invalid = draft.trim() !== "" && !isValid(draft);
                const policy = saved?.policies[category];
                const inputId = `generation-retention-${category}-days`;
                const isModified =
                  saved && draft.trim() !== String(saved.policies[category].retentionDays);
                const parsedDraft = parseDays(draft);
                const isNever = Number.isInteger(parsedDraft) && parsedDraft === 0;

                const categoryConfig = CATEGORY_ICONS[category];
                const IconComponent = categoryConfig.icon;

                return (
                  <Card
                    key={category}
                    className={cn(
                      "transition-all duration-150 border-border/80 bg-background/60",
                      isModified &&
                        "border-primary/50 shadow-xs ring-1 ring-primary/20 bg-primary/[0.015]"
                    )}
                  >
                    <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            "flex size-9 shrink-0 items-center justify-center rounded-lg border",
                            categoryConfig.badgeStyle
                          )}
                        >
                          <IconComponent className="size-4" />
                        </div>
                        <div className="flex flex-col gap-0.5">
                          <Label htmlFor={inputId} className="text-sm font-semibold cursor-pointer">
                            {t(CATEGORY_LABEL_KEY[category])}
                          </Label>
                          <p className="text-xs text-muted-foreground">
                            {t(CATEGORY_SCOPE_KEY[category])}
                          </p>
                        </div>
                      </div>

                      {/* Status Badges */}
                      <div className="flex flex-wrap items-center gap-1.5 self-start sm:self-center">
                        {isModified ? (
                          <Badge variant="default" className="text-xs">
                            {t("admin.retentionCardModified")}
                          </Badge>
                        ) : null}

                        {!policy ? null : policy.retentionDays > 0 ? (
                          <Badge variant="outline" className="text-xs font-normal">
                            {t("admin.retentionDaysValue", { days: policy.retentionDays })}
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-xs font-normal">
                            {t("admin.retentionDisabled")}
                          </Badge>
                        )}

                        {policy && policy.expiredCount > 0 ? (
                          <Badge variant="destructive" className="text-xs">
                            {t("admin.retentionExpiredCount")}: {policy.expiredCount}
                          </Badge>
                        ) : null}
                      </div>
                    </CardHeader>

                    <CardContent className="flex flex-col gap-3 pt-0">
                      {/* Presets + Input Section */}
                      <div className="flex flex-col gap-2.5 rounded-lg border border-border/60 bg-muted/20 p-3 sm:flex-row sm:items-center sm:justify-between">
                        {/* Quick Presets */}
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-xs text-muted-foreground mr-1">
                            {t("admin.retentionCurrent")}:
                          </span>
                          {PRESET_OPTIONS.map((days) => {
                            const isSelected = parsedDraft === days;
                            return (
                              <Button
                                key={days}
                                type="button"
                                size="xs"
                                variant={isSelected ? "secondary" : "outline"}
                                className={cn(
                                  "h-6 rounded-md px-2 text-xs font-normal transition-colors",
                                  isSelected && "border-primary/40 font-medium text-foreground"
                                )}
                                onClick={() => {
                                  setEdited((current) => ({
                                    ...current,
                                    [category]: String(days),
                                  }));
                                }}
                                disabled={query.isLoading || busy}
                              >
                                {days === 0
                                  ? t("admin.retentionPresetNever")
                                  : t("admin.retentionPresetDays", { days })}
                              </Button>
                            );
                          })}
                        </div>

                        {/* Direct Number Input */}
                        <div className="flex items-center gap-2 self-start sm:self-auto">
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
                            }}
                            disabled={query.isLoading || busy}
                            aria-invalid={invalid}
                            aria-label={`${t(CATEGORY_LABEL_KEY[category])} ${t("admin.retentionDaysLabel")}`}
                            className="h-8 w-24 text-center font-mono text-xs"
                          />
                          <span className="text-xs text-muted-foreground">
                            {t("admin.retentionDaysUnit")}
                          </span>
                        </div>
                      </div>

                      {/* Helper status text and update timestamp */}
                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                        <div>
                          {invalid ? (
                            <span className="text-destructive font-medium">
                              {t("admin.retentionDaysInvalid", { max: maxDays })}
                            </span>
                          ) : isNever ? (
                            <span className="text-emerald-600 dark:text-emerald-400">
                              {t("admin.retentionStatusPermanent")}
                            </span>
                          ) : (
                            <span>
                              {t("admin.retentionStatusAutoDelete", { days: parsedDraft || 0 })}
                            </span>
                          )}
                        </div>
                        {policy?.updatedAt ? (
                          <div className="flex items-center gap-1 text-[11px] text-muted-foreground/80">
                            <History className="size-3" />
                            <span>
                              {t("admin.retentionUpdatedAt", {
                                time: formatDateTime(policy.updatedAt),
                              })}
                            </span>
                          </div>
                        ) : null}
                      </div>
                    </CardContent>
                  </Card>
                );
              })
            )}
          </div>

          <p className="text-xs text-muted-foreground">
            {t("admin.retentionDaysHint", { max: maxDays })}
          </p>

          {/* Action Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="submit"
                disabled={!allValid || !dirty || busy || query.isLoading}
                className="gap-1.5"
              >
                {saveMutation.isPending
                  ? t("common.saving")
                  : dirtyCount > 0
                    ? t("admin.retentionSaveWithCount", { count: dirtyCount })
                    : t("common.save")}
              </Button>

              <Button
                type="button"
                variant="outline"
                disabled={!dirty || busy}
                onClick={handleReset}
                className="gap-1.5"
              >
                <RotateCcw className="size-3.5" />
                {t("admin.retentionResetChanges")}
              </Button>
            </div>

            <Button
              type="button"
              variant="outline"
              disabled={busy || query.isLoading || !anyWindow}
              onClick={() => setConfirmSweepOpen(true)}
              title={
                totalExpiredCount === 0
                  ? t("admin.retentionSweepNoExpiredHint")
                  : t("admin.retentionSweepHint")
              }
              className={cn(
                "gap-1.5",
                totalExpiredCount > 0 &&
                  "border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
              )}
            >
              <Trash2 className="size-3.5" />
              {sweepMutation.isPending ? t("admin.retentionSweeping") : t("admin.retentionSweepNow")}
              {totalExpiredCount > 0 ? (
                <span className="rounded-full bg-destructive/10 px-1.5 py-0.2 text-[10px] font-bold">
                  {totalExpiredCount}
                </span>
              ) : null}
            </Button>
          </div>
        </form>

        {/* Confirmation Dialog for Immediate Cleanup */}
        <Dialog open={confirmSweepOpen} onOpenChange={setConfirmSweepOpen}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <div className="flex items-center gap-2 text-destructive">
                <AlertTriangle className="size-5" />
                <DialogTitle>{t("admin.retentionSweepConfirmTitle")}</DialogTitle>
              </div>
              <DialogDescription className="pt-2 text-xs leading-relaxed text-muted-foreground">
                {t("admin.retentionSweepConfirmDescription", { count: totalExpiredCount })}
              </DialogDescription>
            </DialogHeader>

            {/* List breakdown of expired items */}
            {saved ? (
              <div className="rounded-lg border border-border/80 bg-muted/20 p-3 text-xs">
                <div className="font-semibold text-foreground mb-2">
                  {t("admin.retentionExpiredCount")}:
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {RETENTION_CATEGORIES.map((cat) => (
                    <div key={cat} className="flex justify-between items-center text-muted-foreground">
                      <span>{t(CATEGORY_LABEL_KEY[cat])}:</span>
                      <span className="font-mono font-medium text-foreground">
                        {saved.policies[cat]?.expiredCount ?? 0}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <DialogFooter className="mt-2">
              <Button
                variant="outline"
                disabled={sweepMutation.isPending}
                onClick={() => setConfirmSweepOpen(false)}
              >
                {t("common.cancel")}
              </Button>
              <Button
                variant="destructive"
                disabled={sweepMutation.isPending}
                onClick={() => sweepMutation.mutate()}
              >
                {sweepMutation.isPending
                  ? t("admin.retentionSweeping")
                  : t("admin.retentionSweepNow")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
