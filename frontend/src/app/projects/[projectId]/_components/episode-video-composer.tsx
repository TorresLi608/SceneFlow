"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { getEpisodeAction, listExportsAction, mergeEpisodeVideoAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";
import { resolveRequestError } from "@/lib/http/errors";
import { cn } from "@/lib/utils";

export function EpisodeVideoComposer({ projectId, episodeId, open, onOpenChange, initialSelection = [] }: {
  projectId: string;
  episodeId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialSelection?: string[];
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(initialSelection);
  const episodeQuery = useQuery({ queryKey: queryKeys.episode(projectId, episodeId), queryFn: () => getEpisodeAction(projectId, episodeId) });
  const jobsQuery = useQuery({
    queryKey: queryKeys.exports(projectId), queryFn: () => listExportsAction(projectId),
    refetchInterval: (query) => query.state.data?.exports.some((job) => job.status === "queued" || job.status === "running") ? 2000 : false,
  });
  const episode = episodeQuery.data?.episode;
  const job = jobsQuery.data?.exports.find((item) => item.targetEpisodeId === episodeId);
  const running = job?.status === "queued" || job?.status === "running";
  const clips = episode?.scenes.filter((scene) => scene.video.status === "success" && scene.video.url) ?? [];
  const selection = selected.filter((id) => clips.some((clip) => clip.id === id));
  useEffect(() => {
    if (job?.status !== "succeeded") return;
    void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.episode(projectId, episodeId) });
  }, [job?.id, job?.status, projectId, episodeId, queryClient]);
  const merge = useMutation({
    mutationFn: () => mergeEpisodeVideoAction(projectId, episodeId, selection),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: queryKeys.exports(projectId) }); },
  });
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
      <DialogHeader>
        <DialogTitle>{t("episode.composeVideo")} · {episode?.title}</DialogTitle>
        <DialogDescription>{t("episode.composeHint")}</DialogDescription>
      </DialogHeader>
      {episodeQuery.isPending ? <p>{t("common.loading")}</p> : null}
      {episodeQuery.isError ? <p role="alert">{resolveRequestError(episodeQuery.error, t("video.mergeFailed"))}</p> : null}
      {!episodeQuery.isPending && !clips.length ? <p>{t("episode.composeEmpty")}</p> : null}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {clips.map((clip) => {
          const order = selection.indexOf(clip.id);
          return <div key={clip.id} className={cn("rounded-md border p-2", order >= 0 && "border-primary bg-primary/5")}>
            <button type="button" aria-pressed={order >= 0} disabled={running || merge.isPending || (order < 0 && selection.length >= 60)} className="mb-2 flex w-full items-center justify-between text-left text-sm" onClick={() => setSelected((current) => current.includes(clip.id) ? current.filter((id) => id !== clip.id) : [...current, clip.id])}>
              <span>{t("episode.shotNumber", { order: clip.order })}</span><Badge variant={order >= 0 ? "default" : "outline"}>{order >= 0 ? order + 1 : "+"}</Badge>
            </button>
            <video controls preload="metadata" src={clip.video.url!} className="aspect-video w-full rounded bg-black" />
          </div>;
        })}
      </div>
      <p className="text-sm">{t("episode.composeOrder")}: {selection.map((id) => t("episode.shotNumber", { order: clips.find((clip) => clip.id === id)!.order })).join(" → ") || "—"}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button disabled={running || merge.isPending || !selection.length || selection.length > 60} onClick={() => merge.mutate()}>
          {running || merge.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : null}{t("episode.composeVideo")}
        </Button>
        <Button variant="ghost" disabled={running || merge.isPending} onClick={() => setSelected([])}>{t("video.clearSelection")}</Button>
        {job ? <span role="status" className="text-xs">{t(`video.exportStatus.${job.status}`)} {job.progress}%</span> : null}
      </div>
      {merge.isError ? <p role="alert" className="text-destructive">{resolveRequestError(merge.error, t("video.mergeFailed"))}</p> : null}
      {job?.errorMessage ? <p role="alert" className="text-destructive">{job.errorMessage}</p> : null}
      {episode?.videoUrl ? <section className="flex flex-col gap-2 border-t pt-3">
        <p className="text-sm font-medium">{t("episode.composedVideo")}</p>
        <video controls preload="metadata" src={episode.videoUrl} className="max-h-64 w-full rounded bg-black" />
        <Button variant="outline" className="self-start" render={<a href={episode.videoUrl} download />}><Download data-icon="inline-start" />{t("video.download")}</Button>
      </section> : null}
    </DialogContent>
  </Dialog>;
}
