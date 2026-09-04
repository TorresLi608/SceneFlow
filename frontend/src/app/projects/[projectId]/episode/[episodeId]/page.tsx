"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isCancel } from "axios";
import {
  ArrowLeft,
  BookOpen,
  Film,
  Layers,
  Library,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  breakdownEpisodeAction,
  cancelProjectRunAction,
  createProjectSceneAction,
  deleteGenerationReferenceAction,
  deleteAssetAction,
  generateStoryboardAction,
  generateToneSheetAction,
  generateVideoAction,
  getEpisodeAction,
  getProjectModelsAction,
  listCharactersAction,
  listAssetsAction,
  listEpisodesAction,
  listProjectsAction,
  listPropsAction,
  listVoicesAction,
  updateEpisodeAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { artifactBffUrl } from "@/lib/artifact-url";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { BreakdownDetailLevel, BreakdownTarget, Episode, GenerationReferenceInput, Scene } from "@/types/project";

import { BreakdownPanel, EMPTY_SELECTION, type BreakdownSelection } from "./_components/breakdown-panel";
import { ReferencePicker, type ReferenceAssetOption } from "./_components/reference-picker";
import { ShotRow } from "./_components/shot-row";
import { MediaPreviewDialog } from "./_components/media-preview-dialog";
import { AssetLibraryDialog } from "./_components/asset-library-dialog";

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
  const [detailLevel, setDetailLevel] = useState<BreakdownDetailLevel>("standard");
  const [detailPrompt, setDetailPrompt] = useState(() => t("episode.detailStandardPrompt"));
  const [selection, setSelection] = useState<BreakdownSelection>(EMPTY_SELECTION);
  const [selectedShots, setSelectedShots] = useState<string[]>([]);
  const [confirmDiscard, setConfirmDiscard] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [activeBatch, setActiveBatch] = useState<"image" | "video" | null>(null);
  const [assetLibraryOpen, setAssetLibraryOpen] = useState(false);
  const activeBatchWasBusy = useRef(false);
  const breakdownController = useRef<AbortController | null>(null);

  const isInfoDirty =
    title !== episode.title || synopsis !== episode.synopsis || script !== episode.sourceText;

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
  const assetsQuery = useQuery({ queryKey: queryKeys.assets(projectId), queryFn: () => listAssetsAction(projectId) });

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
        { target, detailLevel, detailPrompt: detailLevel === "custom" ? detailPrompt : undefined, script, references: selection, replaceAll },
        breakdownController.current?.signal
      ),
    onSuccess: (response) => {
      // The backend holds off rather than silently discarding rendered shots.
      if (!response.applied) {
        setConfirmDiscard(response.discardsScenes ?? response.discardsGeneratedScenes);
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
      asset.kind === "asset"
        ? deleteAssetAction(projectId, asset.id)
        : deleteGenerationReferenceAction(projectId, asset.kind, asset.id),
    onSuccess: (_response, asset) => {
      const deleted = (item: GenerationReferenceInput) => item.kind === asset.kind && item.id === asset.id;
      setToneReferences((current) => current.filter((item) => !deleted(item)));
      setMessage(null);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.characters(projectId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.props(projectId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.voices(projectId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.assets(projectId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.episodes(projectId) }),
        refreshEpisode(),
        refreshProject(),
      ]);
    },
    onError: (error) => setMessage(resolveRequestError(error, t("episode.referenceDeleteFailed"))),
  });

  const deleteReference = (asset: ReferenceAssetOption) => deleteReferenceMutation.mutateAsync(asset);

  const shots = episode.scenes;
  const readyImagesCount = shots.filter((s) => s.image.status === "success").length;
  const readyVideosCount = shots.filter((s) => s.video.status === "success").length;
  const toneReady = episode.toneImageStatus === "success" && Boolean(episode.toneImageUrl);
  const toneGenerating = toneMutation.isPending || episode.toneImageStatus === "generating";
  const targetShots = (): BatchTarget => ({
    sceneIds: selectedShots.length > 0 ? selectedShots : undefined,
  });
  const targetVideoShots = (): BatchTarget => ({
    sceneIds: (selectedShots.length > 0 ? selectedShots : shots.map((shot) => shot.id)).filter((sceneId) =>
      shots.some((shot) => shot.id === sceneId && !shot.isLocked && Boolean(shot.image.url))
    ),
  });
  const allSelected = shots.length > 0 && selectedShots.length === shots.length;
  const imageBatchGenerating = (activeBatch === "image" && busy) || renderMutation.isPending;
  const videoBatchGenerating = (activeBatch === "video" && busy) || videoMutation.isPending;

  // Mirrors the backend's rule for what a rerun touches, so the retry button can say how
  // many shots it will redo and the spinner lands on the rows actually being redone.
  const pendingShots = (kind: "image" | "video") =>
    shots.filter((shot) => !shot.isLocked && shot[kind].status !== "success" && (kind !== "video" || Boolean(shot.image.url)));
  const videoBatchCandidates = shots.filter((shot) => !shot.isLocked && Boolean(shot.image.url));
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
        label: character.name,
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
      label: item.title,
      media: "image",
      url: artifactBffUrl(item.toneImageUrl!),
    }));
  const sceneImageAssets: ReferenceAssetOption[] = shots
    .filter((scene) => scene.image.url)
    .map((scene) => ({
      kind: "sceneImage",
      id: scene.id,
      label: t("episode.shotNumber", { order: scene.order }),
      media: "image",
      url: artifactBffUrl(scene.image.url!),
    }));
  const sceneVideoAssets: ReferenceAssetOption[] = shots
    .filter((scene) => scene.video.url)
    .map((scene) => ({
      kind: "sceneVideo",
      id: scene.id,
      label: t("episode.shotNumber", { order: scene.order }),
      media: "video",
      url: artifactBffUrl(scene.video.url!),
    }));
  const voiceAssets: ReferenceAssetOption[] = (voicesQuery.data?.voices ?? [])
    .filter((voice) => voice.audioUrl)
    .map((voice) => ({ kind: "voice", id: voice.id, label: voice.name, media: "audio", url: artifactBffUrl(voice.audioUrl!) }));
  const imageModelLimit = modelsQuery.data?.models.image?.capabilities?.maxReferenceImages ?? 0;
  const customAssets: ReferenceAssetOption[] = (assetsQuery.data?.assets ?? [])
    .filter((asset) => asset.url)
    .map((asset) => ({ kind: "asset", id: asset.id, label: asset.name, media: asset.kind, url: artifactBffUrl(asset.url!) }));
  const imageReferenceLimit = imageModelLimit;
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

  // Re-splitting an episode that already has shots is a supported edit, not an error state.
  // What protects rendered work is the discard confirmation below — the backend reports
  // `applied: false` with a count first, and only destroys anything once the user agrees.
  // Gating on the tone sheet instead made re-splitting impossible in the ordinary case:
  // shots exist, no anchor has been drawn yet, and the user wants a different breakdown.
  const breakdownBlocked = !script.trim() || (target === "video" && shots.length === 0);
  const breakdownBlockedReason = !script.trim()
    ? t("episode.splitNeedsScript")
    : t("episode.breakdownNeedsShots");

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* Top Navigation Header */}
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border/70 bg-background/80 px-5 py-3 backdrop-blur-md z-10 shadow-xs">
        <div className="flex items-center gap-2.5">
          <Link
            href={`/projects/${projectId}/episodes`}
            className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-muted-foreground hover:bg-muted/80 hover:text-foreground transition-colors"
          >
            <ArrowLeft className="size-4" />
            {t("episode.backToEpisodes")}
          </Link>
          <span className="text-muted-foreground/40">/</span>
          <span className="max-w-[160px] truncate text-sm font-medium text-muted-foreground">{project?.title}</span>
          <span className="text-muted-foreground/40">/</span>
          <span className="max-w-[200px] truncate text-sm font-semibold text-foreground">{episode.title}</span>

          {/* 剧集制作进度概览徽章 */}
          <div className="hidden lg:flex items-center gap-1.5 ml-2 pl-3 border-l border-border/50 text-xs">
            <span className="inline-flex items-center gap-1 rounded-full bg-muted/60 px-2.5 py-0.5 font-mono text-[11px] text-muted-foreground border border-border/40">
              <Layers className="size-3 text-primary" />
              {shots.length} {t("episode.shots")}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 font-mono text-[11px] text-emerald-600 dark:text-emerald-400 border border-emerald-500/25">
              <Sparkles className="size-3" />
              {t("episode.imagesBadge", { ready: readyImagesCount, total: shots.length })}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 px-2.5 py-0.5 font-mono text-[11px] text-blue-600 dark:text-blue-400 border border-blue-500/25">
              <Film className="size-3" />
              {t("episode.videosBadge", { ready: readyVideosCount, total: shots.length })}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {busy ? (
            <Badge variant="outline" className="animate-pulse border-primary/50 text-primary">
              <Loader2 className="mr-1 size-3 animate-spin" />
              {project?.status}
            </Badge>
          ) : null}
          <Button type="button" size="sm" variant="outline" onClick={() => setAssetLibraryOpen(true)} className="cursor-pointer">
            <Library data-icon="inline-start" />
            {t("episode.assetLibrary")}
          </Button>
          {busy ? (
            <Button
              type="button"
              size="sm"
              variant="destructive"
              disabled={cancelMutation.isPending}
              onClick={() => cancelMutation.mutate()}
              className="cursor-pointer"
            >
              {cancelMutation.isPending ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : (
                <Square data-icon="inline-start" className="size-3 fill-current" />
              )}
              {cancelMutation.isPending ? t("episode.stopping") : t("common.stopGeneration")}
            </Button>
          ) : null}
          <PreferencesSwitcher />
        </div>
      </header>

      {/* Main Workspace Body */}
      <main className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-4 md:p-6 chat-message-list-scrollbar max-w-7xl mx-auto w-full">
        {/* Section 1: Combined Episode Story & Script Workbench */}
        <section className="flex flex-col rounded-xl border border-border/70 bg-card/60 shadow-sm transition-all">
          {/* Header with Title and Save Button */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/50 px-4 py-3 bg-muted/20">
            <div className="flex items-center gap-2">
              <div className="flex size-7 items-center justify-center rounded-md bg-primary/10 text-primary">
                <BookOpen className="size-4" />
              </div>
              <h2 className="text-sm font-semibold">{t("episode.info")}</h2>
              {isInfoDirty ? (
                <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]">
                  {t("episode.unsavedChanges")}
                </Badge>
              ) : null}
            </div>

            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground font-mono">
                {t("episode.charCount", { count: script.length })}
              </span>
              <Button
                size="sm"
                variant={isInfoDirty ? "default" : "outline"}
                disabled={saveInfoMutation.isPending || !isInfoDirty}
                onClick={() => saveInfoMutation.mutate()}
                className="cursor-pointer"
              >
                {saveInfoMutation.isPending ? (
                  <Loader2 data-icon="inline-start" className="animate-spin" />
                ) : (
                  <Save data-icon="inline-start" />
                )}
                {t("episode.saveInfo")}
              </Button>
            </div>
          </div>

          <div className="p-4 flex flex-col gap-4">
            {/* Top row: Episode Name & Synopsis */}
            <div className="grid gap-3 md:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="episodeTitle" className="text-xs font-medium text-muted-foreground">
                  {t("episode.name")}
                </FieldLabel>
                <Input
                  id="episodeTitle"
                  value={title}
                  maxLength={80}
                  required
                  placeholder={t("episode.namePlaceholder")}
                  onChange={(event) => setTitle(event.target.value)}
                  className="bg-background/80 text-sm"
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="episodeSynopsis" className="text-xs font-medium text-muted-foreground">
                  {t("episode.synopsis")}
                </FieldLabel>
                <Input
                  id="episodeSynopsis"
                  value={synopsis}
                  maxLength={4000}
                  placeholder={t("episode.synopsisPlaceholder")}
                  onChange={(event) => setSynopsis(event.target.value)}
                  className="bg-background/80 text-sm"
                />
              </Field>
            </div>

            {/* Bottom row: Script Editor */}
            <Field>
              <div className="flex items-center justify-between mb-1.5">
                <FieldLabel htmlFor="episodeScript" className="text-xs font-medium text-muted-foreground">
                  {t("episode.script")}
                </FieldLabel>
                <span className="text-[11px] text-muted-foreground/70">
                  {t("episode.scriptSectionDesc")}
                </span>
              </div>
              <Textarea
                id="episodeScript"
                value={script}
                maxLength={200_000}
                placeholder={t("episode.scriptPlaceholder")}
                onChange={(event) => setScript(event.target.value)}
                className="field-sizing-fixed min-h-48 max-h-[50vh] resize-y overflow-auto bg-background/80 font-sans text-sm leading-relaxed"
              />
            </Field>
          </div>
        </section>

        {/* Section 2: AI Breakdown Panel */}
        <BreakdownPanel
          characters={charactersQuery.data?.characters ?? []}
          props={propsQuery.data?.props ?? []}
          voices={voicesQuery.data?.voices ?? []}
          selection={selection}
          onSelectionChange={setSelection}
          target={target}
          onTargetChange={setTarget}
          detailLevel={detailLevel}
          onDetailLevelChange={setDetailLevel}
          detailPrompt={detailPrompt}
          onDetailPromptChange={setDetailPrompt}
          running={breakdownMutation.isPending}
          disabled={busy || breakdownBlocked}
          targetDisabled={busy}
          disabledReason={breakdownBlocked ? breakdownBlockedReason : undefined}
          defaultCollapsed={shots.length > 0}
          onStart={startBreakdown}
          onStop={stopBreakdown}
        />

        {/* Section 3: Tone Sheet Panel */}
        <section className="grid gap-4 rounded-xl border border-border/70 bg-card/50 p-4.5 shadow-sm md:grid-cols-[minmax(0,300px)_minmax(0,1fr)] lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t("episode.toneSheet")}
            </p>
            <div className="relative flex aspect-[16/10] w-full items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-muted/40 group">
              {episode.toneImageUrl ? (
                <>
                  <Image
                    src={artifactBffUrl(episode.toneImageUrl)}
                    alt=""
                    fill
                    unoptimized
                    sizes="340px"
                    className="object-cover transition-transform duration-300 group-hover:scale-105"
                  />
                  <button
                    type="button"
                    className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center cursor-zoom-in text-white text-xs font-medium gap-1"
                    aria-label={t("episode.openPreview")}
                    onClick={() =>
                      setTonePreview({
                        kind: "image",
                        url: artifactBffUrl(episode.toneImageUrl!),
                        title: t("episode.toneSheet"),
                      })
                    }
                  >
                    {t("episode.openPreview")}
                  </button>
                </>
              ) : (
                <span className="px-4 text-center text-xs text-muted-foreground">{t("episode.noToneSheet")}</span>
              )}
            </div>
          </div>

          <div className="flex flex-col justify-between gap-3">
            <div className="flex flex-col gap-2.5">
              <p className="text-xs text-muted-foreground leading-relaxed">{t("episode.toneSheetHint")}</p>

              <ReferencePicker
                title={t("episode.toneReferences")}
                hint={t("episode.toneReferencesHint")}
                assets={[...characterAssets, ...propAssets, ...toneAssets, ...customAssets.filter((item) => item.media === "image")]}
                selected={toneReferences}
                limits={{ image: imageModelLimit }}
                onChange={setToneReferences}
                onDelete={busy ? undefined : deleteReference}
              />
            </div>

            <div className="pt-1">
              <Button
                disabled={busy || shots.length === 0}
                title={shots.length === 0 ? t("episode.toneSheetNeedsShots") : undefined}
                onClick={() => toneMutation.mutate()}
                className="cursor-pointer"
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

        {/* Section 4: Shots & Videos List */}
        <section className="flex flex-col gap-3.5 rounded-xl border border-border/70 bg-card/40 p-4 shadow-sm relative">
          {/* Smart Sticky Batch Actions Toolbar */}
          <div className="sticky top-0 z-20 -mx-4 -mt-4 mb-0.5 flex flex-wrap items-center justify-between gap-3 rounded-t-xl border-b border-border/60 bg-background/90 px-4 py-3 shadow-xs backdrop-blur-md transition-all">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex size-7 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Layers className="size-4" />
              </div>
              <h2 className="text-sm font-semibold">{t("episode.imagesSection")}</h2>
              <Badge variant="secondary" className="text-xs font-mono font-medium">
                {t("episode.selectedCount", { count: selectedShots.length })}
              </Badge>
              <Button
                size="xs"
                variant="ghost"
                disabled={shots.length === 0}
                onClick={() => setSelectedShots(allSelected ? [] : shots.map((shot) => shot.id))}
                className="cursor-pointer text-xs text-muted-foreground hover:text-foreground"
              >
                {allSelected ? <X className="mr-1 size-3" /> : null}
                {allSelected ? t("episode.clearSelection") : t("episode.selectAll")}
              </Button>
            </div>

            {/* Batch actions grouped by type */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Frame Generation Group */}
              <Button
                size="sm"
                disabled={busy || shots.length === 0 || !toneReady}
                title={toneReady ? undefined : t("episode.needsToneSheetFirst")}
                onClick={() => {
                  setActiveBatch("image");
                  renderMutation.mutate(targetShots());
                }}
                className="cursor-pointer shadow-xs"
              >
                {imageBatchGenerating ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Sparkles data-icon="inline-start" />}
                {t("episode.batchImages")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy || !toneReady || pendingShots("image").length === 0}
                onClick={() => {
                  setActiveBatch("image");
                  renderMutation.mutate({ pendingOnly: true });
                }}
                className="cursor-pointer shadow-xs text-xs"
              >
                <RefreshCw data-icon="inline-start" />
                {t("episode.retryPendingImages", { count: pendingShots("image").length })}
              </Button>

              <div className="h-4 w-px bg-border/60 mx-0.5" />

              {/* Video Generation Group */}
              <Button
                size="sm"
                variant="secondary"
                disabled={busy || !toneReady || videoBatchCandidates.length === 0}
                title={toneReady ? (videoBatchCandidates.length > 0 ? undefined : t("episode.needsImageFirst")) : t("episode.needsToneSheetFirst")}
                onClick={() => {
                  setActiveBatch("video");
                  videoMutation.mutate(targetVideoShots());
                }}
                className="cursor-pointer shadow-xs"
              >
                {videoBatchGenerating ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Film data-icon="inline-start" />}
                {t("episode.batchVideos")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy || !toneReady || pendingShots("video").length === 0}
                title={toneReady ? (pendingShots("video").length > 0 ? undefined : t("episode.needsImageFirst")) : t("episode.needsToneSheetFirst")}
                onClick={() => {
                  setActiveBatch("video");
                  videoMutation.mutate({ sceneIds: pendingShots("video").map((shot) => shot.id), pendingOnly: true });
                }}
                className="cursor-pointer shadow-xs text-xs"
              >
                <RefreshCw data-icon="inline-start" />
                {t("episode.retryPendingVideos", { count: pendingShots("video").length })}
              </Button>

              <div className="h-4 w-px bg-border/60 mx-0.5" />

              {/* Add Shot Button */}
              <Button size="sm" variant="outline" disabled={busy} onClick={() => addShotMutation.mutate()} className="cursor-pointer shadow-xs text-xs">
                <Plus data-icon="inline-start" className="text-primary" />
                {t("episode.newShot")}
              </Button>
            </div>
          </div>

          {/* Shot Cards list */}
          {shots.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border/70 p-8 text-center text-xs text-muted-foreground">
              {t("episode.noShots")}
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {shots.map((scene, index) => (
                <ShotRow
                  key={scene.id}
                  projectId={projectId}
                  scene={scene}
                  index={index}
                  defaultImageReferences={
                    scene.imageReferencesExplicit ? [] : (scene.characterIds ?? []).flatMap((id) => {
                      const asset = characterAssets.find((item) => item.id === id);
                      return asset ? [{ kind: asset.kind, id: asset.id }] : [];
                    }).slice(0, imageReferenceLimit)
                  }
                  // The shot's own frame is deliberately absent: it is the first-frame
                  // slot's job, and the render prepends it anyway (`defaultVideoReferencePaths`).
                  // Listing it here too spent a second reference slot on the same image and
                  // wrote `@分镜 N` into the motion prompt on every reload.
                  defaultVideoReferences={
                    scene.videoReferencesExplicit || !videoCapabilities?.referenceImages
                      ? []
                      : (scene.characterIds ?? [])
                          .flatMap((id) => {
                            const asset = characterAssets.find((item) => item.id === id);
                            return asset ? [{ kind: asset.kind, id: asset.id }] : [];
                          })
                          .slice(0, videoCapabilities.maxReferenceImages)
                  }
                  selected={selectedShots.includes(scene.id)}
                  toneReady={toneReady}
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
                  imageReferenceAssets={[...characterAssets, ...propAssets, ...toneAssets, ...sceneImageAssets, ...customAssets.filter((item) => item.media === "image")]}
                  videoReferenceAssets={[
                    ...characterAssets,
                    ...propAssets,
                    ...toneAssets,
                    ...sceneImageAssets,
                    ...customAssets,
                    ...sceneVideoAssets.filter((asset) => asset.id !== scene.id),
                    ...voiceAssets,
                  ]}
                  imageReferenceLimit={imageReferenceLimit}
                  videoReferenceLimits={{
                    image: videoCapabilities?.referenceImages ? videoCapabilities.maxReferenceImages : 0,
                    video: videoCapabilities?.referenceVideo ? videoCapabilities.maxReferenceVideos : 0,
                    audio: videoCapabilities?.referenceAudio ? videoCapabilities.maxReferenceAudios : 0,
                  }}
                  supportsStartEndFrames={Boolean(videoCapabilities?.supportsStartEndFrames)}
                  supportsFirstFrame={Boolean(videoCapabilities?.supportsFirstFrame)}
                  supportsLastFrame={Boolean(videoCapabilities?.supportsLastFrame)}
                  videoDisabled={!scene.image.url}
                  onError={setMessage}
                />
              ))}
            </div>
          )}
        </section>

        {message ? (
          <p className={cn("text-sm px-1", message === t("episode.stopped") ? "text-muted-foreground" : "text-amber-600")}>
            {message}
          </p>
        ) : null}
      </main>

      {/* Discard Confirmation Dialog */}
      <AssetLibraryDialog
        projectId={projectId}
        open={assetLibraryOpen}
        onOpenChange={setAssetLibraryOpen}
        assets={assetsQuery.data?.assets ?? []}
        generatedImages={[
          ...characterAssets.map((item) => ({ id: `${item.kind}:${item.id}`, name: item.label, url: item.url })),
          ...propAssets.map((item) => ({ id: `${item.kind}:${item.id}`, name: item.label, url: item.url })),
          ...toneAssets.map((item) => ({ id: `${item.kind}:${item.id}`, name: item.label, url: item.url })),
          ...shots.filter((shot) => shot.image.url).map((shot) => ({ id: `scene:${shot.id}`, name: t("episode.shotNumber", { order: shot.order }), url: artifactBffUrl(shot.image.url!) })),
        ]}
        onChanged={() => {
          void queryClient.invalidateQueries({ queryKey: queryKeys.assets(projectId) });
          void refreshEpisode();
        }}
      />
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
