"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Film, ImageIcon, Loader2, Plus, Save, Sparkles, Trash2, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import {
  createProjectSceneAction,
  deleteProjectSceneAction,
  generateStoryboardAction,
  generateVideoAction,
  getEpisodeAction,
  listEpisodesAction,
  listProjectsAction,
  parseProjectAction,
  updateEpisodeAction,
  updateProjectSceneAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import type { Episode, Scene } from "@/types/project";

/** While a render is in flight the page polls; the run is a background task with no reply. */
const RENDER_POLL_MS = 3_000;

function ShotRow({
  projectId,
  scene,
  index,
  busy,
  onError,
}: {
  projectId: string;
  scene: Scene;
  index: number;
  busy: boolean;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [text, setText] = useState(scene.narration);
  const dirty = text !== scene.narration;

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.episode(projectId, scene.episodeId ?? "") });

  const saveMutation = useMutation({
    mutationFn: () => updateProjectSceneAction(projectId, scene.id, { narration: text }),
    onSuccess: () => void refresh(),
    onError: (error) => onError(resolveRequestError(error, t("episode.saveFailed"))),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteProjectSceneAction(projectId, scene.id),
    onSuccess: () => void refresh(),
    onError: (error) => onError(resolveRequestError(error, t("reference.deleteFailed"))),
  });

  const statusTone =
    scene.image.status === "success"
      ? "default"
      : scene.image.status === "error"
        ? "destructive"
        : "outline";

  return (
    <div className="grid gap-3 rounded-lg border border-border/60 p-3 md:grid-cols-[minmax(0,1fr)_220px]">
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{index + 1}</Badge>
          <Badge variant={statusTone}>{scene.image.status}</Badge>
          {scene.errorMessage ? (
            <span className="text-xs text-destructive">{scene.errorMessage}</span>
          ) : null}
        </div>
        <Textarea
          value={text}
          maxLength={4000}
          rows={3}
          placeholder={t("episode.shotPlaceholder")}
          onChange={(event) => setText(event.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy || saveMutation.isPending || !dirty}
            onClick={() => saveMutation.mutate()}
          >
            {saveMutation.isPending ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Save data-icon="inline-start" />
            )}
            {t("common.save")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={busy || deleteMutation.isPending}
            onClick={() => deleteMutation.mutate()}
          >
            <Trash2 data-icon="inline-start" />
            {t("episode.deleteShot")}
          </Button>
        </div>
      </div>

      <span className="relative flex aspect-video w-full items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-muted">
        {scene.image.url ? (
          <Image src={scene.image.url} alt="" fill unoptimized sizes="220px" className="object-cover" />
        ) : (
          <ImageIcon className="size-5 text-muted-foreground" />
        )}
      </span>
    </div>
  );
}

function EpisodeEditor({ projectId, episode }: { projectId: string; episode: Episode }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [script, setScript] = useState(episode.sourceText);
  const [previousEpisodeId, setPreviousEpisodeId] = useState("");
  const [mergeReferences, setMergeReferences] = useState(true);
  const [regenerate, setRegenerate] = useState(false);
  const [withAudio, setWithAudio] = useState(false);
  const [confirmRerender, setConfirmRerender] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: listProjectsAction,
    staleTime: 300_000,
  });
  const project = projectsQuery.data?.projects.find((item) => item.id === projectId);
  const episodesQuery = useQuery({
    queryKey: queryKeys.episodes(projectId),
    queryFn: () => listEpisodesAction(projectId),
  });

  const busy = project ? ["parsing", "generating", "video_generating"].includes(project.status) : false;
  const refreshEpisode = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.episode(projectId, episode.id) });

  const saveScriptMutation = useMutation({
    mutationFn: () => updateEpisodeAction(projectId, episode.id, { sourceText: script }),
    onSuccess: () => void refreshEpisode(),
    onError: (error) => setMessage(resolveRequestError(error, t("episode.saveFailed"))),
  });

  const splitMutation = useMutation({
    mutationFn: (replaceAll: boolean) =>
      parseProjectAction(projectId, { script, episodeId: episode.id, replaceAll }),
    onSuccess: (response) => {
      // The backend holds off rather than silently discarding rendered shots.
      if (!response.applied) {
        setMessage(t("episode.splitWouldDiscard", { count: response.discardsGeneratedScenes }));
        return;
      }
      setMessage(null);
      void refreshEpisode();
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("episode.splitFailed"))),
  });

  const addShotMutation = useMutation({
    mutationFn: () => createProjectSceneAction(projectId, { episodeId: episode.id, narration: "" }),
    onSuccess: () => void refreshEpisode(),
    onError: (error) => setMessage(resolveRequestError(error, t("episode.saveFailed"))),
  });

  const renderMutation = useMutation({
    mutationFn: () =>
      generateStoryboardAction(projectId, episode.id, {
        previousEpisodeId: previousEpisodeId || undefined,
        mergeReferences,
        regenerate,
      }),
    onSuccess: () => {
      setMessage(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("episode.generateFailed"))),
  });

  const videoMutation = useMutation({
    mutationFn: () =>
      generateVideoAction(projectId, { episodeId: episode.id, withAudio }),
    onSuccess: () => {
      setMessage(null);
      setConfirmRerender(false);
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("video.generateFailed"))),
  });

  const renderedClips = episode.scenes.filter((scene) => scene.video.url).length;
  // Re-rendering overwrites clips the user may have accepted, so it asks first. Purely a
  // client-side check: the backend has no way to know whether the overwrite was intended.
  const startVideo = () => (renderedClips > 0 ? setConfirmRerender(true) : videoMutation.mutate());

  const previousItems = [
    { value: "", label: t("episode.previousEpisodeNone") },
    ...(episodesQuery.data?.episodes ?? [])
      .filter((item) => item.id !== episode.id)
      .map((item) => ({ value: item.id, label: item.title })),
  ];

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border/70 px-4 py-3">
        <Link
          href={`/projects/${projectId}/episodes`}
          className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted/60"
        >
          <ArrowLeft className="size-4" />
          {t("episode.backToEpisodes")}
        </Link>
        <span className="truncate text-sm font-semibold">{project?.title}</span>
        <span className="text-muted-foreground">/</span>
        <span className="truncate text-sm">{episode.title}</span>
      </header>

      <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 md:p-6">
        <section className="flex flex-col gap-3 rounded-lg border border-border/70 bg-card/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">{t("episode.script")}</h2>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={saveScriptMutation.isPending || script === episode.sourceText}
                onClick={() => saveScriptMutation.mutate()}
              >
                {saveScriptMutation.isPending ? (
                  <Loader2 data-icon="inline-start" className="animate-spin" />
                ) : (
                  <Save data-icon="inline-start" />
                )}
                {t("common.save")}
              </Button>
              <Button
                size="sm"
                disabled={busy || splitMutation.isPending || !script.trim()}
                onClick={() => splitMutation.mutate(false)}
              >
                {splitMutation.isPending ? (
                  <Loader2 data-icon="inline-start" className="animate-spin" />
                ) : (
                  <Sparkles data-icon="inline-start" />
                )}
                {splitMutation.isPending ? t("episode.splitting") : t("episode.splitShots")}
              </Button>
            </div>
          </div>
          <Textarea
            value={script}
            maxLength={200_000}
            rows={10}
            placeholder={t("episode.scriptPlaceholder")}
            onChange={(event) => setScript(event.target.value)}
          />
          {message ? (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm text-amber-600">{message}</p>
              {splitMutation.data && !splitMutation.data.applied ? (
                <Button size="sm" variant="destructive" onClick={() => splitMutation.mutate(true)}>
                  {t("common.confirm")}
                </Button>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className="grid gap-4 rounded-lg border border-border/70 bg-card/40 p-4 md:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("episode.toneSheet")}
            </p>
            <span className="relative flex aspect-[3/2] w-full items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-muted">
              {episode.toneImageUrl ? (
                <Image src={episode.toneImageUrl} alt="" fill unoptimized sizes="320px" className="object-contain" />
              ) : (
                <span className="px-4 text-center text-xs text-muted-foreground">{t("episode.noToneSheet")}</span>
              )}
            </span>
          </div>

          <div className="flex flex-col gap-3">
            <Field>
              <FieldLabel htmlFor="previousEpisode">{t("episode.previousEpisode")}</FieldLabel>
              <Select
                items={previousItems}
                value={previousEpisodeId}
                onValueChange={(value) => setPreviousEpisodeId(value ?? "")}
              >
                <SelectTrigger id="previousEpisode" className="w-full max-w-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {previousItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <FieldDescription>{t("episode.previousEpisodeHint")}</FieldDescription>
            </Field>

            <Field orientation="horizontal">
              <Switch id="mergeReferences" checked={mergeReferences} onCheckedChange={setMergeReferences} />
              <FieldLabel htmlFor="mergeReferences">{t("episode.mergeReferences")}</FieldLabel>
            </Field>
            <FieldDescription>{t("episode.mergeReferencesHint")}</FieldDescription>

            <Field orientation="horizontal">
              <Switch id="regenerateTone" checked={regenerate} onCheckedChange={setRegenerate} />
              <FieldLabel htmlFor="regenerateTone">{t("episode.regenerate")}</FieldLabel>
            </Field>
            <FieldDescription>{t("episode.regenerateHint")}</FieldDescription>

            <Field orientation="horizontal">
              <Switch id="withAudio" checked={withAudio} onCheckedChange={setWithAudio} />
              <FieldLabel htmlFor="withAudio">{t("video.withAudio")}</FieldLabel>
            </Field>
            <FieldDescription>{t("video.withAudioHint")}</FieldDescription>

            <div className="flex flex-wrap gap-2">
              <Button
                disabled={busy || renderMutation.isPending || episode.scenes.length === 0}
                onClick={() => renderMutation.mutate()}
              >
                {busy || renderMutation.isPending ? (
                  <Loader2 data-icon="inline-start" className="animate-spin" />
                ) : (
                  <Sparkles data-icon="inline-start" />
                )}
                {busy ? t("episode.generating") : t("episode.generateStoryboard")}
              </Button>
              <Button
                variant="secondary"
                disabled={busy || videoMutation.isPending || episode.scenes.length === 0}
                onClick={startVideo}
              >
                {videoMutation.isPending ? (
                  <Loader2 data-icon="inline-start" className="animate-spin" />
                ) : (
                  <Film data-icon="inline-start" />
                )}
                {busy ? t("video.generating") : t("video.generateVideo")}
              </Button>
            </div>
          </div>
        </section>

        <section className="flex flex-col gap-3 rounded-lg border border-border/70 bg-card/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">{t("episode.shots")}</h2>
            <Button size="sm" variant="outline" disabled={busy || addShotMutation.isPending} onClick={() => addShotMutation.mutate()}>
              <Plus data-icon="inline-start" />
              {t("episode.newShot")}
            </Button>
          </div>

          {episode.scenes.length === 0 ? (
            <p className="rounded-md border border-dashed border-border/70 p-6 text-center text-xs text-muted-foreground">
              {t("episode.noShots")}
            </p>
          ) : (
            episode.scenes.map((scene, index) => (
              // Keyed on the rendered image too, so a finished render re-seeds the row.
              <ShotRow
                key={`${scene.id}-${scene.image.url ?? "none"}`}
                projectId={projectId}
                scene={scene}
                index={index}
                busy={busy}
                onError={setMessage}
              />
            ))
          )}
        </section>
      </main>

      <Dialog open={confirmRerender} onOpenChange={setConfirmRerender}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("video.regenerateTitle")}</DialogTitle>
            <DialogDescription>{t("video.regenerateConfirm", { count: renderedClips })}</DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="outline" disabled={videoMutation.isPending} onClick={() => setConfirmRerender(false)}>
              <X data-icon="inline-start" />
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" disabled={videoMutation.isPending} onClick={() => videoMutation.mutate()}>
              {videoMutation.isPending ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : (
                <Film data-icon="inline-start" />
              )}
              {t("common.confirm")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function EpisodeEditorPage() {
  const { projectId, episodeId } = useParams<{ projectId: string; episodeId: string }>();
  const { t } = useI18n();

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: listProjectsAction,
    staleTime: 300_000,
  });
  const project = projectsQuery.data?.projects.find((item) => item.id === projectId);
  const rendering = project ? ["parsing", "generating", "video_generating"].includes(project.status) : false;

  const episodeQuery = useQuery({
    queryKey: queryKeys.episode(projectId, episodeId),
    queryFn: () => getEpisodeAction(projectId, episodeId),
    // The render is a background task, so the page polls itself while one is in flight —
    // and polls the project list too, since that is what carries the busy status.
    refetchInterval: rendering ? RENDER_POLL_MS : false,
  });
  useQuery({
    queryKey: [...queryKeys.projects, "poll"],
    queryFn: listProjectsAction,
    enabled: rendering,
    refetchInterval: RENDER_POLL_MS,
  });

  const episode = episodeQuery.data?.episode;
  if (!episode) {
    return (
      <div className="p-6">
        {episodeQuery.isLoading ? <Skeleton className="h-72 rounded-lg" /> : <p className="text-sm">{t("episode.empty")}</p>}
      </div>
    );
  }

  // Keyed so switching episodes re-seeds the script and shot fields.
  return <EpisodeEditor key={episode.id} projectId={projectId} episode={episode} />;
}
