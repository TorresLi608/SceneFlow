"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Film, Loader2, Play, Sparkles, Trash2, X } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";

import {
  createExportAction,
  deleteExportAction,
  getEpisodeAction,
  listEpisodesAction,
  listExportsAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { MediaPreviewDialog } from "@/app/projects/[projectId]/episode/[episodeId]/_components/media-preview-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { ExportJob, ExportStatus } from "@/types/project";

/** While a merge is queued or running the history polls; it is a background task. */
const EXPORT_POLL_MS = 2_000;

interface Clip {
  sceneId: string;
  label: string;
  url: string;
}

export default function VideosPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { t, formatDateTime } = useI18n();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const [rangeLabel, setRangeLabel] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [previewItem, setPreviewItem] = useState<{ kind: "image" | "video"; url: string; title: string } | null>(null);
  const [pendingDeleteJob, setPendingDeleteJob] = useState<ExportJob | null>(null);

  const episodesQuery = useQuery({
    queryKey: queryKeys.episodes(projectId),
    queryFn: () => listEpisodesAction(projectId),
  });
  const episodes = episodesQuery.data?.episodes ?? [];

  // One request per episode: the list endpoint carries summaries, and the clips live on the
  // shots inside each episode. The episode ids are part of the key, not just the closure —
  // without them adding or deleting an episode left this list showing the old clips.
  const episodeIds = episodes.map((episode) => episode.id).join(",");
  const episodeDetails = useQuery({
    queryKey: [...queryKeys.episodes(projectId), "clips", episodeIds],
    enabled: episodes.length > 0,
    queryFn: async () => {
      const details = await Promise.all(
        episodes.map((episode) => getEpisodeAction(projectId, episode.id))
      );
      return details.flatMap<Clip>(({ episode }) =>
        episode.scenes
          .filter((scene) => scene.video.url)
          .map((scene) => ({
            sceneId: scene.id,
            label: `${episode.title} · ${scene.order}`,
            url: scene.video.url as string,
          }))
      );
    },
  });
  const clips = episodeDetails.data ?? [];

  const exportsQuery = useQuery({
    queryKey: queryKeys.exports(projectId),
    queryFn: () => listExportsAction(projectId),
    refetchInterval: (query) => {
      const jobs = query.state.data?.exports ?? [];
      return jobs.some((job) => job.status === "queued" || job.status === "running") ? EXPORT_POLL_MS : false;
    },
  });

  const mergeMutation = useMutation({
    mutationFn: () => createExportAction(projectId, { sceneIds: selected, rangeLabel: rangeLabel.trim() }),
    onSuccess: () => {
      setMessage(null);
      setSelected([]);
      setRangeLabel("");
      void queryClient.invalidateQueries({ queryKey: queryKeys.exports(projectId) });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("video.mergeFailed"))),
  });

  const deleteMutation = useMutation({
    mutationFn: (exportId: string) => deleteExportAction(projectId, exportId),
    onSuccess: () => {
      setPendingDeleteJob(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.exports(projectId) });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("video.deleteFailed"))),
  });

  const toggle = (sceneId: string) =>
    setSelected((current) =>
      current.includes(sceneId) ? current.filter((item) => item !== sceneId) : [...current, sceneId]
    );

  const statusLabel: Record<ExportStatus, string> = {
    queued: t("video.exportStatus.queued"),
    running: t("video.exportStatus.running"),
    succeeded: t("video.exportStatus.succeeded"),
    failed: t("video.exportStatus.failed"),
    canceled: t("video.exportStatus.canceled"),
  };

  const historyRow = (job: ExportJob) => (
    <section
      key={job.id}
      className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border/70 bg-card/60 p-4 transition-colors hover:border-border"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{job.rangeLabel || formatDateTime(job.createdAt)}</span>
          <Badge variant={job.status === "succeeded" ? "default" : job.status === "failed" ? "destructive" : "outline"}>
            {statusLabel[job.status]}
          </Badge>
          <span className="text-xs text-muted-foreground">{t("video.clipCount", { count: job.sceneIds.length })}</span>
        </div>
        {job.errorMessage ? <p className="mt-1 text-xs text-destructive">{job.errorMessage}</p> : null}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {job.videoUrl ? (
          <button
            type="button"
            title={t("video.preview")}
            aria-label={t("video.preview")}
            onClick={() =>
              setPreviewItem({
                kind: "video",
                url: job.videoUrl!,
                title: job.rangeLabel || formatDateTime(job.createdAt),
              })
            }
            className="group relative flex h-18 w-28 shrink-0 cursor-zoom-in items-center justify-center overflow-hidden rounded-md border border-border/70 bg-black/80 transition hover:border-primary/60 hover:shadow-md"
          >
            <video
              src={job.videoUrl}
              preload="metadata"
              className="size-full object-cover opacity-90 transition-transform duration-200 group-hover:scale-105"
            />
            <div className="absolute inset-0 flex items-center justify-center bg-black/25 transition-colors group-hover:bg-black/10">
              <div className="flex size-7 items-center justify-center rounded-full bg-background/90 text-foreground shadow backdrop-blur-sm transition-transform group-hover:scale-110">
                <Play className="ml-0.5 size-3.5 fill-current" />
              </div>
            </div>
          </button>
        ) : null}

        <div className="flex items-center gap-1.5">
          {job.videoUrl ? (
            <Button size="sm" variant="outline" render={<a href={job.videoUrl} download />}>
              <Download data-icon="inline-start" />
              {t("video.download")}
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            title={t("video.deleteExport")}
            onClick={() => setPendingDeleteJob(job)}
          >
            <Trash2 data-icon="inline-start" />
            {t("video.deleteExport")}
          </Button>
        </div>
      </div>
    </section>
  );

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t("video.title")}</h1>
        <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{t("video.subtitle")}</p>
      </div>

      <section className="flex flex-col gap-3 rounded-lg border border-border/70 bg-card/40 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("video.available")}</p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">{t("video.selected", { count: selected.length })}</span>
            {selected.length > 0 ? (
              <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
                <X data-icon="inline-start" />
                {t("video.clearSelection")}
              </Button>
            ) : null}
          </div>
        </div>

        {episodeDetails.isLoading ? (
          <Skeleton className="h-32 rounded-lg" />
        ) : clips.length === 0 ? (
          <p className="rounded-md border border-dashed border-border/70 p-6 text-center text-xs text-muted-foreground">
            {t("video.noClips")}
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {clips.map((clip) => {
              const order = selected.indexOf(clip.sceneId);
              return (
                <button
                  key={clip.sceneId}
                  type="button"
                  onClick={() => toggle(clip.sceneId)}
                  aria-pressed={order >= 0}
                  className={cn(
                    "flex flex-col gap-2 rounded-lg border p-2 text-left transition",
                    order >= 0 ? "border-primary bg-primary/5" : "border-border/60 hover:border-primary/40"
                  )}
                >
                  <span className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate">{clip.label}</span>
                    {/* The badge is the position in the cut, not the shot number. */}
                    {order >= 0 ? <Badge>{order + 1}</Badge> : <Film className="size-3.5 text-muted-foreground" />}
                  </span>
                  <video src={clip.url} className="aspect-video w-full rounded-md bg-muted" muted preload="metadata" />
                </button>
              );
            })}
          </div>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <Field className="max-w-xs flex-1">
            <FieldLabel htmlFor="rangeLabel">{t("video.rangeLabel")}</FieldLabel>
            <Input
              id="rangeLabel"
              value={rangeLabel}
              maxLength={120}
              placeholder={t("video.rangeLabelPlaceholder")}
              onChange={(event) => setRangeLabel(event.target.value)}
            />
          </Field>
          <Button
            disabled={mergeMutation.isPending || selected.length === 0}
            title={selected.length === 0 ? t("video.needsSelection") : undefined}
            onClick={() => mergeMutation.mutate()}
          >
            {mergeMutation.isPending ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Sparkles data-icon="inline-start" />
            )}
            {mergeMutation.isPending ? t("video.merging") : t("video.merge")}
          </Button>
        </div>

        {message ? <p className="text-sm text-amber-600">{message}</p> : null}
      </section>

      <section className="flex flex-col gap-3">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("video.history")}</p>
        {exportsQuery.isLoading ? (
          <Skeleton className="h-24 rounded-lg" />
        ) : (exportsQuery.data?.exports ?? []).length === 0 ? (
          <p className="rounded-lg border border-dashed border-border/70 p-6 text-center text-xs text-muted-foreground">
            {t("video.noHistory")}
          </p>
        ) : (
          (exportsQuery.data?.exports ?? []).map(historyRow)
        )}
      </section>

      <MediaPreviewDialog item={previewItem} onOpenChange={(open) => !open && setPreviewItem(null)} />

      <Dialog open={Boolean(pendingDeleteJob)} onOpenChange={(open) => (open ? null : setPendingDeleteJob(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("video.deleteExport")}</DialogTitle>
            <DialogDescription>{t("video.deleteExportConfirm")}</DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="outline" disabled={deleteMutation.isPending} onClick={() => setPendingDeleteJob(null)}>
              <X data-icon="inline-start" />
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => pendingDeleteJob && deleteMutation.mutate(pendingDeleteJob.id)}
            >
              {deleteMutation.isPending ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : (
                <Trash2 data-icon="inline-start" />
              )}
              {t("common.delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
