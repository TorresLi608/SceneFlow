"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isCancel } from "axios";
import { ArrowLeft, Film, Loader2, Plus, RefreshCw, Save, Sparkles, Square, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  breakdownEpisodeAction,
  cancelProjectRunAction,
  createProjectSceneAction,
  deleteGenerationReferenceAction,
  generateStoryboardAction,
  generateToneSheetAction,
  generateVideoAction,
  getEpisodeAction,
  getProjectModelsAction,
  listCharactersAction,
  listEpisodesAction,
  listProjectsAction,
  listPropsAction,
  listVoicesAction,
  updateEpisodeAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { artifactBffUrl } from "@/lib/artifact-url";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { BreakdownTarget, Episode, GenerationReferenceInput, Scene } from "@/types/project";

import { BreakdownPanel, EMPTY_SELECTION, type BreakdownSelection } from "./_components/breakdown-panel";
import { ReferencePicker, type ReferenceAssetOption } from "./_components/reference-picker";
import { ShotRow } from "./_components/shot-row";
import { MediaPreviewDialog } from "./_components/media-preview-dialog";

/** While a render is in flight the page polls; the run is a background task with no reply. */
const RENDER_POLL_MS = 3_000;
const BUSY_STATUSES = ["parsing", "generating", "video_generating"];

/**
 * What a batch button asks for. `pendingOnly` is the difference between "render this
 * episode" and "retry the ones that failed": without it the backend re-renders every
 * unlocked shot, so retrying two failures out of twenty pays for twenty.
 */
interface BatchTarget {
  sceneIds?: string[];
  pendingOnly?: boolean;
}

function EpisodeEditor({ projectId, episode }: { projectId: string; episode: Episode }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(episode.title);
  const [synopsis, setSynopsis] = useState(episode.synopsis);
  const [script, setScript] = useState(episode.sourceText);
  const [toneReferences, setToneReferences] = useState<GenerationReferenceInput[]>([]);
  const [tonePreview, setTonePreview] = useState<{ kind: "image"; url: string; title: string } | null>(null);
  const [target, setTarget] = useState<BreakdownTarget>("both");
  const [selection, setSelection] = useState<BreakdownSelection>(EMPTY_SELECTION);
  const [selectedShots, setSelectedShots] = useState<string[]>([]);
  const [confirmDiscard, setConfirmDiscard] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [activeBatch, setActiveBatch] = useState<"image" | "video" | null>(null);
  const activeBatchWasBusy = useRef(false);
  const breakdownController = useRef<AbortController | null>(null);

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: listProjectsAction,
    staleTime: 300_000,
  });
  const project = projectsQuery.data?.projects.find((item) => item.id === projectId);
  const busy = project ? BUSY_STATUSES.includes(project.status) : false;

  useEffect(() => {
    if (activeBatch && busy) {
      activeBatchWasBusy.current = true;
      return;
    }
    if (!activeBatchWasBusy.current || busy) return;
    activeBatchWasBusy.current = false;
    const clear = window.setTimeout(() => setActiveBatch(null), 0);
    return () => window.clearTimeout(clear);
  }, [activeBatch, busy]);

  const modelsQuery = useQuery({
    queryKey: queryKeys.projectModels(projectId),
    queryFn: () => getProjectModelsAction(projectId),
    staleTime: 300_000,
  });

  const episodesQuery = useQuery({
    queryKey: queryKeys.episodes(projectId),
    queryFn: () => listEpisodesAction(projectId),
  });
  const charactersQuery = useQuery({
    queryKey: queryKeys.characters(projectId),
    queryFn: () => listCharactersAction(projectId),
  });
  const propsQuery = useQuery({
    queryKey: queryKeys.props(projectId),
    queryFn: () => listPropsAction(projectId),
  });
  const voicesQuery = useQuery({
    queryKey: queryKeys.voices(projectId),
    queryFn: () => listVoicesAction(projectId),
  });

  const refreshEpisode = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.episode(projectId, episode.id) });
  const refreshProject = () => queryClient.invalidateQueries({ queryKey: queryKeys.projects });

  const saveInfoMutation = useMutation({
    mutationFn: () =>
      updateEpisodeAction(projectId, episode.id, {
        title: title.trim(),
        synopsis: synopsis.trim(),
        sourceText: script,
      }),
    onSuccess: () => {
      setMessage(t("episode.infoSaved"));
      void refreshEpisode();
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });
    },
    onError: (error) => setMessage(resolveRequestError(error, t("episode.saveFailed"))),
  });

  const breakdownMutation = useMutation({
    mutationFn: (replaceAll: boolean) =>
      breakdownEpisodeAction(
        projectId,
        episode.id,
        { target, script, references: selection, replaceAll },
        breakdownController.current?.signal
      ),
    onSuccess: (response) => {
      // The backend holds off rather than silently discarding rendered shots.
      if (!response.applied) {
        setConfirmDiscard(response.discardsGeneratedScenes);
        return;
      }
      setConfirmDiscard(null);
      setMessage(null);
      setSelectedShots([]);
      void refreshEpisode();
      void refreshProject();
      void queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) });
    },
    onError: (error) => {
      if (isCancel(error)) return;
      setMessage(resolveRequestError(error, t("episode.breakdownFailed")));
    },
    onSettled: () => {
      breakdownController.current = null;
    },
  });

  const toneMutation = useMutation({
    mutationFn: () =>
      generateToneSheetAction(projectId, episode.id, {
        regenerate: true,
        references: toneReferences,
      }),
    onSuccess: () => {
      setMessage(null);
      void refreshProject();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("episode.generateFailed"))),
  });

  const renderMutation = useMutation({
    mutationFn: ({ sceneIds, pendingOnly }: BatchTarget) =>
      generateStoryboardAction(projectId, episode.id, {
        sceneIds,
        pendingOnly,
      }),
    onSuccess: () => {
      setMessage(null);
      void refreshProject();
    },
    onError: (error) => {
      setActiveBatch(null);
      setMessage(resolveRequestError(error, t("episode.generateFailed")));
    },
  });

  const videoMutation = useMutation({
    mutationFn: ({ sceneIds, pendingOnly }: BatchTarget) =>
      generateVideoAction(projectId, { episodeId: episode.id, sceneIds, pendingOnly }),
    onSuccess: () => {
      setMessage(null);
      void refreshProject();
    },
    onError: (error) => {
      setActiveBatch(null);
      setMessage(resolveRequestError(error, t("video.generateFailed")));
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelProjectRunAction(projectId),
    onSuccess: () => {
      setMessage(t("episode.stopped"));
      void refreshProject();
      void refreshEpisode();
    },
    onError: (error) => setMessage(resolveRequestError(error, t("episode.cancelFailed"))),
  });

  const addShotMutation = useMutation({
    mutationFn: () => createProjectSceneAction(projectId, { episodeId: episode.id, narration: "" }),
    onSuccess: () => void refreshEpisode(),
    onError: (error) => setMessage(resolveRequestError(error, t("episode.saveFailed"))),
  });

  const deleteReferenceMutation = useMutation({
    mutationFn: (asset: ReferenceAssetOption) =>
      deleteGenerationReferenceAction(projectId, asset.kind, asset.id),
    onSuccess: (_response, asset) => {
      const deleted = (item: GenerationReferenceInput) => item.kind === asset.kind && item.id === asset.id;
      setToneReferences((current) => current.filter((item) => !deleted(item)));
      setMessage(null);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.characters(projectId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.props(projectId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.voices(projectId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) }),
        refreshEpisode(),
        refreshProject(),
      ]);
    },
    onError: (error) => setMessage(resolveRequestError(error, t("episode.referenceDeleteFailed"))),
  });

  const deleteReference = (asset: ReferenceAssetOption) => deleteReferenceMutation.mutateAsync(asset);

  const shots = episode.scenes;
  const toneReady = episode.toneImageStatus === "success" && Boolean(episode.toneImageUrl);
  const toneGenerating = toneMutation.isPending || episode.toneImageStatus === "generating";
  const targetShots = (): BatchTarget => ({
    sceneIds: selectedShots.length > 0 ? selectedShots : undefined,
  });
  const allSelected = shots.length > 0 && selectedShots.length === shots.length;
  const imageBatchGenerating = (activeBatch === "image" && busy) || renderMutation.isPending;
  const videoBatchGenerating = (activeBatch === "video" && busy) || videoMutation.isPending;
  // Mirrors the backend's rule for what a rerun touches, so the retry button can say how
  // many shots it will redo and the spinner lands on the rows actually being redone.
  const pendingShots = (kind: "image" | "video") =>
    shots.filter((shot) => !shot.isLocked && shot[kind].status !== "success");
  const batchIncludes = (scene: Scene, kind: "image" | "video", target: BatchTarget | undefined) => {
    if (target?.sceneIds?.length) return target.sceneIds.includes(scene.id);
    if (scene.isLocked) return false;
    return target?.pendingOnly ? scene[kind].status !== "success" : true;
  };

  const toggleShot = (sceneId: string) =>
    setSelectedShots((current) =>
      current.includes(sceneId) ? current.filter((item) => item !== sceneId) : [...current, sceneId]
    );

  const characterAssets: ReferenceAssetOption[] = (charactersQuery.data?.characters ?? []).flatMap((character) => [
    ...(character.sheetImageUrl || character.referenceImageUrl
      ? [{
          kind: "character" as const,
          id: character.id,
          label: t("episode.referenceCharacter", { name: character.name }),
          media: "image" as const,
          url: artifactBffUrl((character.sheetImageUrl || character.referenceImageUrl)!),
        }]
      : []),
    ...character.states
      .filter((state) => state.referenceImageUrl)
      .map((state) => ({
        kind: "characterState" as const,
        id: state.id,
        label: `${character.name} · ${state.name}`,
        media: "image" as const,
        url: artifactBffUrl(state.referenceImageUrl!),
      })),
  ]);
  const propAssets: ReferenceAssetOption[] = (propsQuery.data?.props ?? [])
    .filter((prop) => prop.imageUrl)
    .map((prop) => ({ kind: "prop", id: prop.id, label: prop.name, media: "image", url: artifactBffUrl(prop.imageUrl!) }));
  const toneAssets: ReferenceAssetOption[] = [episode, ...(episodesQuery.data?.episodes ?? []).filter((item) => item.id !== episode.id)]
    .filter((item) => item.toneImageUrl)
    .map((item) => ({
      kind: "tone",
      id: item.id,
      label: t("episode.referenceTone", { title: item.title }),
      media: "image",
      url: artifactBffUrl(item.toneImageUrl!),
    }));
  const sceneImageAssets: ReferenceAssetOption[] = shots
    .filter((scene) => scene.image.url)
    .map((scene) => ({
      kind: "sceneImage",
      id: scene.id,
      label: t("episode.referenceShot", { number: scene.order }),
      media: "image",
      url: artifactBffUrl(scene.image.url!),
    }));
  const sceneVideoAssets: ReferenceAssetOption[] = shots
    .filter((scene) => scene.video.url)
    .map((scene) => ({
      kind: "sceneVideo",
      id: scene.id,
      label: t("episode.referenceShot", { number: scene.order }),
      media: "video",
      url: artifactBffUrl(scene.video.url!),
    }));
  const voiceAssets: ReferenceAssetOption[] = (voicesQuery.data?.voices ?? [])
    .filter((voice) => voice.audioUrl)
    .map((voice) => ({ kind: "voice", id: voice.id, label: voice.name, media: "audio", url: artifactBffUrl(voice.audioUrl!) }));
  const imageModelLimit = modelsQuery.data?.models.image?.capabilities?.maxReferenceImages ?? 0;
  const imageReferenceLimit = Math.max(0, imageModelLimit - 1);
  const videoCapabilities = modelsQuery.data?.models.video?.capabilities;

  const startBreakdown = () => {
    breakdownController.current = new AbortController();
    breakdownMutation.mutate(false);
  };

  const stopBreakdown = () => {
    breakdownController.current?.abort();
    breakdownController.current = null;
    breakdownMutation.reset();
  };

  const breakdownBlocked = !script.trim() || (target === "video" && shots.length === 0);
  const breakdownBlockedReason = !script.trim()
    ? t("episode.splitNeedsScript")
    : t("episode.breakdownNeedsShots");

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
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
        {busy ? (
          <Badge variant="outline" className="ml-auto animate-pulse">
            {project?.status}
          </Badge>
        ) : null}
        {busy ? (
          <Button
            type="button"
            size="sm"
            variant="destructive"
            disabled={cancelMutation.isPending}
            onClick={() => cancelMutation.mutate()}
          >
            {cancelMutation.isPending ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Square data-icon="inline-start" className="size-3 fill-current" />
            )}
            {cancelMutation.isPending ? t("episode.stopping") : t("common.stopGeneration")}
          </Button>
        ) : null}
      </header>

      <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 md:p-6 chat-message-list-scrollbar">
        {/* Episode info moved in from the list: the title and synopsis describe the script
            below them, and editing all three in one place is the only arrangement where
            that relationship is visible. */}
        <section className="flex flex-col gap-3 rounded-lg border border-border/70 bg-card/60 p-4">
          <h2 className="text-sm font-semibold">{t("episode.info")}</h2>
          <div className="grid gap-3 md:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="episodeTitle">{t("episode.name")}</FieldLabel>
              <Input
                id="episodeTitle"
                value={title}
                maxLength={80}
                required
                onChange={(event) => setTitle(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="episodeSynopsis">{t("episode.synopsis")}</FieldLabel>
              <Textarea
                id="episodeSynopsis"
                value={synopsis}
                maxLength={4000}
                rows={2}
                placeholder={t("episode.synopsisPlaceholder")}
                onChange={(event) => setSynopsis(event.target.value)}
                className="field-sizing-fixed min-h-16 resize-y"
              />
            </Field>
          </div>
        </section>

        <section className="flex flex-col gap-3 rounded-lg border border-border/70 bg-card/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">{t("episode.script")}</h2>
            <Button
              size="sm"
              variant="outline"
              disabled={saveInfoMutation.isPending}
              onClick={() => saveInfoMutation.mutate()}
            >
              {saveInfoMutation.isPending ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : (
                <Save data-icon="inline-start" />
              )}
              {t("episode.saveInfo")}
            </Button>
          </div>
          {/*
            A fixed starting height that the user can drag. The default `field-sizing-content`
            grew the box to the length of the script, which on a full episode pushed every
            control below it off the screen.
          */}
          <Textarea
            value={script}
            maxLength={200_000}
            placeholder={t("episode.scriptPlaceholder")}
            onChange={(event) => setScript(event.target.value)}
            className="field-sizing-fixed min-h-56 max-h-[60vh] resize-y overflow-auto"
          />
        </section>

        <BreakdownPanel
          characters={charactersQuery.data?.characters ?? []}
          props={propsQuery.data?.props ?? []}
          voices={voicesQuery.data?.voices ?? []}
          selection={selection}
          onSelectionChange={setSelection}
          target={target}
          onTargetChange={setTarget}
          running={breakdownMutation.isPending}
          disabled={busy || breakdownBlocked}
          disabledReason={breakdownBlocked ? breakdownBlockedReason : undefined}
          onStart={startBreakdown}
          onStop={stopBreakdown}
        />

        <section className="grid gap-4 rounded-lg border border-border/70 bg-card/40 p-4 md:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("episode.toneSheet")}
            </p>
            <span className="relative flex aspect-[3/2] w-full items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-muted">
              {episode.toneImageUrl ? (
                <button
                  type="button"
                  className="absolute inset-0 cursor-zoom-in"
                  aria-label={t("episode.openPreview")}
                  onClick={() => setTonePreview({ kind: "image", url: artifactBffUrl(episode.toneImageUrl!), title: t("episode.toneSheet") })}
                >
                  <Image src={artifactBffUrl(episode.toneImageUrl)} alt="" fill unoptimized sizes="320px" className="object-contain" />
                </button>
              ) : (
                <span className="px-4 text-center text-xs text-muted-foreground">{t("episode.noToneSheet")}</span>
              )}
            </span>
          </div>

          <div className="flex flex-col gap-3">
            <p className="text-xs text-muted-foreground">{t("episode.toneSheetHint")}</p>

            <ReferencePicker
              title={t("episode.toneReferences")}
              hint={t("episode.toneReferencesHint")}
              assets={[...characterAssets, ...propAssets, ...toneAssets]}
              selected={toneReferences}
              limits={{ image: imageModelLimit }}
              onChange={setToneReferences}
              onDelete={busy ? undefined : deleteReference}
            />

            <div>
              <Button
                disabled={busy || shots.length === 0}
                title={shots.length === 0 ? t("episode.toneSheetNeedsShots") : undefined}
                onClick={() => toneMutation.mutate()}
              >
                {toneGenerating ? (
                  <Loader2 data-icon="inline-start" className="animate-spin" />
                ) : (
                  <Sparkles data-icon="inline-start" />
                )}
                {toneReady ? t("episode.regenerateToneSheet") : t("episode.generateToneSheet")}
              </Button>
            </div>
          </div>
        </section>

        <MediaPreviewDialog item={tonePreview} onOpenChange={(open) => !open && setTonePreview(null)} />

        <section className="flex flex-col gap-3 rounded-lg border border-border/70 bg-card/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold">{t("episode.imagesSection")}</h2>
              <Badge variant="outline">{t("episode.selectedCount", { count: selectedShots.length })}</Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="ghost"
                disabled={shots.length === 0}
                onClick={() => setSelectedShots(allSelected ? [] : shots.map((shot) => shot.id))}
              >
                {allSelected ? <X data-icon="inline-start" /> : null}
                {allSelected ? t("episode.clearSelection") : t("episode.selectAll")}
              </Button>
              <Button
                size="sm"
                disabled={busy || shots.length === 0 || !toneReady}
                title={toneReady ? undefined : t("episode.needsToneSheetFirst")}
                onClick={() => {
                  setActiveBatch("image");
                  renderMutation.mutate(targetShots());
                }}
              >
                {imageBatchGenerating ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Sparkles data-icon="inline-start" />}
                {t("episode.batchImages")}
              </Button>
              {/* Its own button rather than a smarter 批量生成: a plain rerun is also how a
                  user resamples an episode they did not like, so narrowing that silently
                  would take away the only way to redo a shot that came out wrong. */}
              <Button
                size="sm"
                variant="outline"
                disabled={busy || !toneReady || pendingShots("image").length === 0}
                onClick={() => {
                  setActiveBatch("image");
                  renderMutation.mutate({ pendingOnly: true });
                }}
              >
                <RefreshCw data-icon="inline-start" />
                {t("episode.retryPendingImages", { count: pendingShots("image").length })}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={busy || shots.length === 0}
                onClick={() => {
                  setActiveBatch("video");
                  videoMutation.mutate(targetShots());
                }}
              >
                {videoBatchGenerating ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Film data-icon="inline-start" />}
                {t("episode.batchVideos")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy || pendingShots("video").length === 0}
                onClick={() => {
                  setActiveBatch("video");
                  videoMutation.mutate({ pendingOnly: true });
                }}
              >
                <RefreshCw data-icon="inline-start" />
                {t("episode.retryPendingVideos", { count: pendingShots("video").length })}
              </Button>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => addShotMutation.mutate()}>
                <Plus data-icon="inline-start" />
                {t("episode.newShot")}
              </Button>
            </div>
          </div>

          {shots.length === 0 ? (
            <p className="rounded-md border border-dashed border-border/70 p-6 text-center text-xs text-muted-foreground">
              {t("episode.noShots")}
            </p>
          ) : (
            shots.map((scene, index) => (
              // Keyed on updatedAt, not on the image URL: signed links are minted fresh on
              // every response, so a URL-keyed row remounted on every poll and threw away
              // whatever the user was typing.
              <ShotRow
                key={`${scene.id}-${scene.updatedAt}`}
                projectId={projectId}
                scene={scene}
                index={index}
                characters={charactersQuery.data?.characters ?? []}
                selected={selectedShots.includes(scene.id)}
                onToggle={() => toggleShot(scene.id)}
                busy={busy}
                onGenerateImage={() => {
                  setActiveBatch(null);
                  renderMutation.mutate({ sceneIds: [scene.id] });
                }}
                onGenerateVideo={() => {
                  setActiveBatch(null);
                  videoMutation.mutate({ sceneIds: [scene.id] });
                }}
                imageGenerating={
                  scene.image.status === "generating" ||
                  (imageBatchGenerating && batchIncludes(scene, "image", renderMutation.variables)) ||
                  (!toneGenerating && activeBatch === null && project?.status === "generating" &&
                    batchIncludes(scene, "image", renderMutation.variables))
                }
                videoGenerating={
                  scene.video.status === "generating" ||
                  (videoBatchGenerating && batchIncludes(scene, "video", videoMutation.variables)) ||
                  (activeBatch === null && project?.status === "video_generating" &&
                    batchIncludes(scene, "video", videoMutation.variables))
                }
                imageReferenceAssets={[...characterAssets, ...propAssets, ...toneAssets, ...sceneImageAssets]}
                videoReferenceAssets={[
                  ...characterAssets,
                  ...propAssets,
                  ...toneAssets,
                  ...sceneImageAssets.filter((asset) => asset.id !== scene.id),
                  ...sceneVideoAssets.filter((asset) => asset.id !== scene.id),
                  ...voiceAssets,
                ]}
                imageReferenceLimit={imageReferenceLimit}
                videoReferenceLimits={{
                  image: videoCapabilities?.referenceImages
                    ? Math.max(0, videoCapabilities.maxReferenceImages - Number(Boolean(scene.image.url)))
                    : 0,
                  video: videoCapabilities?.referenceVideo ? videoCapabilities.maxReferenceVideos : 0,
                  audio: videoCapabilities?.referenceAudio ? videoCapabilities.maxReferenceAudios : 0,
                }}
                videoDisabled={Boolean(
                  videoCapabilities?.referenceImagesRequired && !scene.image.url
                )}
                onError={setMessage}
              />
            ))
          )}
        </section>

        {message ? (
          <p className={cn("text-sm", message === t("episode.stopped") ? "text-muted-foreground" : "text-amber-600")}>
            {message}
          </p>
        ) : null}
      </main>

      <Dialog open={confirmDiscard !== null} onOpenChange={(open) => (open ? null : setConfirmDiscard(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("episode.splitShots")}</DialogTitle>
            <DialogDescription>
              {t("episode.breakdownWouldDiscard", { count: confirmDiscard ?? 0 })}
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="outline" disabled={breakdownMutation.isPending} onClick={() => setConfirmDiscard(null)}>
              <X data-icon="inline-start" />
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={breakdownMutation.isPending}
              onClick={() => {
                breakdownController.current = new AbortController();
                breakdownMutation.mutate(true);
              }}
            >
              {breakdownMutation.isPending ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : (
                <Sparkles data-icon="inline-start" />
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
  const queryClient = useQueryClient();

  /**
   * The busy flag and the poll must read the *same* cache entry.
   *
   * They used to not: `rendering` was derived from `queryKeys.projects` (staleTime 5
   * minutes, no interval) while the poll wrote to `[...projects, "poll"]` — a different
   * key nothing rendered from. So the status never refreshed, `rendering` stayed true
   * forever, and the page polled every three seconds for the rest of the session. Together
   * with re-minted asset URLs that reads exactly like "it keeps generating over and over".
   */
  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: listProjectsAction,
    staleTime: 300_000,
    refetchInterval: (query) => {
      const project = query.state.data?.projects.find((item) => item.id === projectId);
      return project && BUSY_STATUSES.includes(project.status) ? RENDER_POLL_MS : false;
    },
  });
  const project = projectsQuery.data?.projects.find((item) => item.id === projectId);
  const rendering = project ? BUSY_STATUSES.includes(project.status) : false;
  const wasRendering = useRef(false);

  useEffect(() => {
    if (rendering) {
      wasRendering.current = true;
      return;
    }
    if (!wasRendering.current) return;
    wasRendering.current = false;
    void queryClient.invalidateQueries({ queryKey: queryKeys.episode(projectId, episodeId) });
  }, [episodeId, projectId, queryClient, rendering]);

  const episodeQuery = useQuery({
    queryKey: queryKeys.episode(projectId, episodeId),
    queryFn: () => getEpisodeAction(projectId, episodeId),
    refetchInterval: rendering ? RENDER_POLL_MS : false,
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
