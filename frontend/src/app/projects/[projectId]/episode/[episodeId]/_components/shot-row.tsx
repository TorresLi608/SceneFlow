"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { isCancel } from "axios";
import {
  Camera,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Eye,
  Film,
  ImageIcon,
  Loader2,
  Maximize2,
  Play,
  RotateCw,
  Save,
  Sparkles,
  Trash2,
} from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { deleteProjectSceneAction, updateProjectSceneAction } from "@/actions/projects-actions";
import { compilePromptAction } from "@/actions/prompt-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { artifactBffUrl } from "@/lib/artifact-url";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Scene } from "@/types/project";
import type { GenerationReferenceInput } from "@/types/project";
import type { ReferenceAssetOption } from "./reference-picker";
import { MentionTextarea } from "./mention-textarea";
import { MediaPreviewDialog } from "./media-preview-dialog";

const referenceKey = (item: GenerationReferenceInput) => `${item.kind}:${item.id}`;
const withDefaultMentions = (
  prompt: string,
  references: GenerationReferenceInput[],
  assets: ReferenceAssetOption[]
) =>
  references.reduce((value, reference) => {
    const asset = assets.find((item) => referenceKey(item) === referenceKey(reference));
    return asset && !value.includes(`@${asset.label}`) ? `${value.trim()} @${asset.label}`.trim() : value;
  }, prompt.trim());

export interface ShotRowProps {
  projectId: string;
  scene: Scene;
  index: number;
  defaultImageReferences: GenerationReferenceInput[];
  defaultVideoReferences: GenerationReferenceInput[];
  selected: boolean;
  onToggle: () => void;
  /** True while any run owns the project; per-shot actions are unavailable then. */
  busy: boolean;
  toneReady: boolean;
  onGenerateImage: () => void;
  onGenerateVideo: () => void;
  imageGenerating: boolean;
  videoGenerating: boolean;
  videoDisabled: boolean;
  imageReferenceAssets: ReferenceAssetOption[];
  videoReferenceAssets: ReferenceAssetOption[];
  imageReferenceLimit: number;
  videoReferenceLimits: { image: number; video: number; audio: number };
  onError: (message: string) => void;
}

export function ShotRow({
  projectId,
  scene,
  index,
  defaultImageReferences,
  defaultVideoReferences,
  selected,
  onToggle,
  busy,
  toneReady,
  onGenerateImage,
  onGenerateVideo,
  imageGenerating,
  videoGenerating,
  videoDisabled,
  imageReferenceAssets,
  videoReferenceAssets,
  imageReferenceLimit,
  videoReferenceLimits,
  onError,
}: ShotRowProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [narration, setNarration] = useState(scene.narration);
  const [visualPrompt, setVisualPrompt] = useState(() =>
    withDefaultMentions(
      scene.visualPrompt,
      scene.imageReferencesExplicit ? [] : defaultImageReferences,
      imageReferenceAssets
    )
  );
  const [shotType, setShotType] = useState(scene.shotType);
  const [cameraMove, setCameraMove] = useState(scene.cameraMove);
  const [transition, setTransition] = useState(scene.transition);
  const [videoPrompt, setVideoPrompt] = useState(() =>
    withDefaultMentions(
      scene.videoPrompt,
      scene.videoReferencesExplicit ? [] : defaultVideoReferences,
      videoReferenceAssets
    )
  );
  const [imageReferences, setImageReferences] = useState<GenerationReferenceInput[]>(
    scene.imageReferencesExplicit ? scene.imageReferences : defaultImageReferences
  );
  const [videoReferences, setVideoReferences] = useState<GenerationReferenceInput[]>(
    scene.videoReferencesExplicit ? scene.videoReferences : defaultVideoReferences
  );
  const [seconds, setSeconds] = useState(scene.durationMs ? String(Math.round(scene.durationMs / 1000)) : "");
  const [open, setOpen] = useState(false);
  const [userMediaTab, setUserMediaTab] = useState<"image" | "video" | null>(null);
  const activeMediaTab =
    userMediaTab ??
    (videoGenerating ? "video" : imageGenerating ? "image" : scene.video.url && !scene.image.url ? "video" : "image");
  const setActiveMediaTab = (tab: "image" | "video") => setUserMediaTab(tab);
  const [preview, setPreview] = useState<{ kind: "image" | "video"; url: string; title: string } | null>(null);
  const [compiledPrompt, setCompiledPrompt] = useState<string | null>(null);
  const imageDefaultsApplied = useRef(false);
  const videoDefaultsApplied = useRef(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const generationStartedAt = useRef<number | null>(null);

  useEffect(() => {
    const generating = imageGenerating || videoGenerating;
    if (!generating) {
      generationStartedAt.current = null;
      return;
    }
    generationStartedAt.current ??= Date.now();
    const update = () => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - (generationStartedAt.current ?? Date.now())) / 1000)));
    };
    const initial = window.setTimeout(update, 0);
    const timer = window.setInterval(update, 1000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [imageGenerating, videoGenerating]);

  useEffect(() => {
    const resolvedDefaults = defaultImageReferences.filter((reference) =>
      imageReferenceAssets.some((asset) => referenceKey(asset) === referenceKey(reference))
    );
    if (imageDefaultsApplied.current || scene.imageReferencesExplicit || !resolvedDefaults.length) return;
    imageDefaultsApplied.current = true;
    setImageReferences(resolvedDefaults);
    setVisualPrompt((current) => withDefaultMentions(current, resolvedDefaults, imageReferenceAssets));
  }, [defaultImageReferences, imageReferenceAssets, scene.imageReferencesExplicit]);

  useEffect(() => {
    const resolvedDefaults = defaultVideoReferences.filter((reference) =>
      videoReferenceAssets.some((asset) => referenceKey(asset) === referenceKey(reference))
    );
    if (videoDefaultsApplied.current || scene.videoReferencesExplicit || !resolvedDefaults.length) return;
    videoDefaultsApplied.current = true;
    setVideoReferences(resolvedDefaults);
    setVideoPrompt((current) => withDefaultMentions(current, resolvedDefaults, videoReferenceAssets));
  }, [defaultVideoReferences, videoReferenceAssets, scene.videoReferencesExplicit]);

  const lastSyncUpdatedAt = useRef(scene.updatedAt);
  useEffect(() => {
    if (scene.updatedAt !== lastSyncUpdatedAt.current) {
      lastSyncUpdatedAt.current = scene.updatedAt;
      setNarration(scene.narration);
      setVisualPrompt(scene.visualPrompt);
      setShotType(scene.shotType);
      setCameraMove(scene.cameraMove);
      setTransition(scene.transition);
      setVideoPrompt(scene.videoPrompt);
      setImageReferences(scene.imageReferences ?? []);
      setVideoReferences(scene.videoReferences ?? []);
      setSeconds(scene.durationMs ? String(Math.round(scene.durationMs / 1000)) : "");
    }
  }, [
    scene.updatedAt,
    scene.narration,
    scene.visualPrompt,
    scene.shotType,
    scene.cameraMove,
    scene.transition,
    scene.videoPrompt,
    scene.imageReferences,
    scene.videoReferences,
    scene.durationMs,
  ]);

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.episode(projectId, scene.episodeId ?? "") });

  const dirty =
    narration !== scene.narration ||
    visualPrompt !== scene.visualPrompt ||
    shotType !== scene.shotType ||
    cameraMove !== scene.cameraMove ||
    transition !== scene.transition ||
    videoPrompt !== scene.videoPrompt ||
    JSON.stringify(imageReferences) !== JSON.stringify(scene.imageReferences ?? []) ||
    JSON.stringify(videoReferences) !== JSON.stringify(scene.videoReferences ?? []) ||
    (seconds.trim() ? Number(seconds) * 1000 : 0) !== scene.durationMs;

  const saveMutation = useMutation({
    mutationFn: () =>
      updateProjectSceneAction(projectId, scene.id, {
        narration,
        visualPrompt,
        shotType,
        cameraMove,
        transition,
        videoPrompt,
        imageReferences,
        videoReferences,
        durationMs: seconds.trim() ? Math.round(Number(seconds) * 1000) : 0,
      }),
    onSuccess: () => void refresh(),
    onError: (error) => {
      if (isCancel(error)) return;
      onError(resolveRequestError(error, t("episode.saveFailed")));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteProjectSceneAction(projectId, scene.id),
    onSuccess: () => void refresh(),
    onError: (error) => onError(resolveRequestError(error, t("reference.deleteFailed"))),
  });

  const compileMutation = useMutation({
    mutationFn: (kind: "image" | "video") =>
      compilePromptAction({
        projectId,
        sceneId: scene.id,
        kind,
        prompt: kind === "image" ? visualPrompt : videoPrompt,
        dialogue: kind === "video" ? scene.dialogue : "",
        references: kind === "image" ? imageReferences : videoReferences,
      }),
    onSuccess: (result) => setCompiledPrompt(result.prompt),
    onError: (error) => {
      if (isCancel(error)) return;
      onError(resolveRequestError(error, t("episode.finalPromptPreviewFailed")));
    },
  });

  const hasImage = scene.image.status === "success" && Boolean(scene.image.url);
  const hasVideo = scene.video.status === "success" && Boolean(scene.video.url);
  const generating = imageGenerating || videoGenerating;

  const saveBeforeGenerate = (action: () => void) => {
    if (!dirty) {
      action();
      return;
    }
    saveMutation.mutate(undefined, { onSuccess: action });
  };

  const videoRefCounts = {
    image: videoReferences.filter(
      (item) => videoReferenceAssets.find((asset) => asset.kind === item.kind && asset.id === item.id)?.media === "image"
    ).length,
    video: videoReferences.filter(
      (item) => videoReferenceAssets.find((asset) => asset.kind === item.kind && asset.id === item.id)?.media === "video"
    ).length,
    audio: videoReferences.filter(
      (item) => videoReferenceAssets.find((asset) => asset.kind === item.kind && asset.id === item.id)?.media === "audio"
    ).length,
  };

  return (
    <div
      className={cn(
        "group relative rounded-xl border bg-card/60 p-4 transition-all duration-200 shadow-sm",
        selected ? "border-primary/80 bg-primary/[0.03] ring-1 ring-primary/30" : "border-border/70 hover:border-border hover:shadow-md",
        generating && "border-primary/80 bg-primary/[0.04] ring-2 ring-primary/40"
      )}
      aria-busy={generating}
    >
      {/* Top row: Checkbox, Number badge, Status badges, and Details Toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/40 pb-3 mb-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-pressed={selected}
            aria-label={t("episode.selectAll")}
            onClick={onToggle}
            className={cn(
              "flex size-5 shrink-0 items-center justify-center rounded border transition-colors cursor-pointer",
              selected ? "border-primary bg-primary text-primary-foreground" : "border-border/80 hover:border-primary/60 bg-background/80"
            )}
          >
            {selected ? <Check className="size-3.5" /> : null}
          </button>

          <Badge variant="secondary" className="font-mono font-semibold px-2 py-0.5 text-xs">
            #{String(index + 1).padStart(2, "0")}
          </Badge>

          {/* Quick status chips */}
          <div className="flex items-center gap-1.5">
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium border",
                scene.image.status === "success"
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : scene.image.status === "error"
                  ? "border-destructive/40 bg-destructive/10 text-destructive"
                  : "border-border/60 bg-muted/40 text-muted-foreground"
              )}
            >
              <ImageIcon className="size-3" />
              {scene.image.status === "success" ? "图就绪" : scene.image.status === "error" ? "图失败" : scene.image.status}
            </span>

            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium border",
                scene.video.status === "success"
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : scene.video.status === "error"
                  ? "border-destructive/40 bg-destructive/10 text-destructive"
                  : "border-border/60 bg-muted/40 text-muted-foreground"
              )}
            >
              <Film className="size-3" />
              {scene.video.status === "success" ? "视频就绪" : scene.video.status === "error" ? "视频失败" : scene.video.status}
            </span>
          </div>

          {/* Shot metadata badges */}
          {scene.cameraMove ? (
            <Badge variant="outline" className="text-[11px] text-muted-foreground bg-muted/20 border-border/50">
              <Camera className="mr-1 size-2.5" />
              {scene.cameraMove}
            </Badge>
          ) : null}
          {scene.transition ? (
            <Badge variant="outline" className="text-[11px] text-muted-foreground bg-muted/20 border-border/50">
              {scene.transition}
            </Badge>
          ) : null}
          {scene.durationMs ? (
            <Badge variant="outline" className="text-[11px] text-muted-foreground bg-muted/20 border-border/50">
              <Clock className="mr-1 size-2.5" />
              {Math.round(scene.durationMs / 1000)}s
            </Badge>
          ) : null}

          {dirty ? (
            <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]">
              {t("episode.unsavedChanges")}
            </Badge>
          ) : null}

          {generating ? (
            <Badge variant="secondary" className="text-primary animate-pulse text-[11px]">
              <Loader2 className="mr-1 size-3 animate-spin" />
              {t("episode.generatingSeconds", { seconds: elapsedSeconds })}
            </Badge>
          ) : null}
        </div>

        {/* Action icons right aligned */}
        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            size="xs"
            variant={open ? "secondary" : "ghost"}
            onClick={() => setOpen((current) => !current)}
            className="text-xs gap-1 text-muted-foreground hover:text-foreground cursor-pointer"
          >
            {t("episode.shotDetails")}
            {open ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          </Button>
        </div>
      </div>

      {/* Main Grid: Left side for text/narration, Right side for Media Box */}
      <div className="grid gap-4 items-start md:grid-cols-[minmax(0,1fr)_250px] lg:grid-cols-[minmax(0,1fr)_280px]">
        {/* Left column: Narration + reference pills */}
        <div className="flex min-w-0 flex-col gap-2.5">
          <div className="relative">
            <Textarea
              value={narration}
              maxLength={4000}
              rows={3}
              placeholder={t("episode.shotPlaceholder")}
              onChange={(event) => setNarration(event.target.value)}
              className="field-sizing-fixed min-h-20 resize-y bg-background/60 leading-relaxed text-sm focus-visible:ring-1 focus-visible:ring-primary"
            />
          </div>

          {/* Reference asset counts pills */}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            {imageReferenceLimit > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-muted/40 px-2 py-0.5 border border-border/40">
                <ImageIcon className="size-3 text-muted-foreground/70" />
                {t("episode.shotImageReferences", { count: imageReferences.length, limit: imageReferenceLimit })}
              </span>
            ) : null}
            {videoReferenceLimits.image > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-muted/40 px-2 py-0.5 border border-border/40">
                <Film className="size-3 text-muted-foreground/70" />
                {t("episode.shotVideoReferences", { count: videoRefCounts.image, limit: videoReferenceLimits.image })}
              </span>
            ) : null}
            {videoReferenceLimits.video > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-muted/40 px-2 py-0.5 border border-border/40">
                <Film className="size-3 text-muted-foreground/70" />
                {t("episode.shotVideoReferencesVideo", { count: videoRefCounts.video, limit: videoReferenceLimits.video })}
              </span>
            ) : null}
            {videoReferenceLimits.audio > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-muted/40 px-2 py-0.5 border border-border/40">
                {t("episode.shotVideoReferencesAudio", { count: videoRefCounts.audio, limit: videoReferenceLimits.audio })}
              </span>
            ) : null}
          </div>

          {scene.errorMessage ? (
            <p className="rounded-md bg-destructive/10 border border-destructive/20 px-2.5 py-1.5 text-xs text-destructive">
              {scene.errorMessage}
            </p>
          ) : null}
        </div>

        {/* Right column: Compact Media Switcher Box (Image & Video Tab) */}
        <div className="flex flex-col gap-2 rounded-lg border border-border/60 bg-muted/20 p-2.5">
          {/* Media Tab Header */}
          <div className="flex items-center justify-between rounded-md bg-muted/60 p-0.5 border border-border/40">
            <button
              type="button"
              onClick={() => setActiveMediaTab("image")}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded py-1 text-xs font-medium transition-all cursor-pointer",
                activeMediaTab === "image"
                  ? "bg-background text-foreground shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <ImageIcon className="size-3.5" />
              <span>{t("episode.tabImage")}</span>
              {hasImage ? (
                <span className="size-1.5 rounded-full bg-emerald-500" />
              ) : null}
            </button>
            <button
              type="button"
              onClick={() => setActiveMediaTab("video")}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded py-1 text-xs font-medium transition-all cursor-pointer",
                activeMediaTab === "video"
                  ? "bg-background text-foreground shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Film className="size-3.5" />
              <span>{t("episode.tabVideo")}</span>
              {hasVideo ? (
                <span className="size-1.5 rounded-full bg-emerald-500" />
              ) : null}
            </button>
          </div>

          {/* Media Viewport Area */}
          <div className="relative aspect-video w-full overflow-hidden rounded-md border border-border/60 bg-background/80 flex items-center justify-center group/media">
            {activeMediaTab === "image" ? (
              hasImage ? (
                <>
                  <Image
                    src={artifactBffUrl(scene.image.url!)}
                    alt=""
                    fill
                    unoptimized
                    sizes="280px"
                    className="object-cover transition-transform duration-300 group-hover/media:scale-105"
                  />
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/media:opacity-100 transition-opacity flex items-center justify-center gap-2">
                    <Button
                      type="button"
                      size="icon-xs"
                      variant="secondary"
                      className="rounded-full shadow-md cursor-pointer"
                      title={t("episode.openPreview")}
                      onClick={() =>
                        setPreview({
                          kind: "image",
                          url: artifactBffUrl(scene.image.url!),
                          title: t("episode.shotImageTitle", { number: index + 1 }),
                        })
                      }
                    >
                      <Maximize2 className="size-3.5" />
                    </Button>
                  </div>
                </>
              ) : (
                <div className="flex flex-col items-center justify-center gap-1.5 p-3 text-center text-muted-foreground">
                  <ImageIcon className="size-6 opacity-40" />
                  <span className="text-[11px] opacity-70">{t("episode.noImageGenerated")}</span>
                </div>
              )
            ) : (
              hasVideo ? (
                <>
                  <video
                    src={artifactBffUrl(scene.video.url!)}
                    preload="metadata"
                    className="size-full object-cover"
                  />
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/media:opacity-100 transition-opacity flex items-center justify-center gap-2">
                    <Button
                      type="button"
                      size="icon-xs"
                      variant="secondary"
                      className="rounded-full shadow-md cursor-pointer"
                      title={t("episode.openPreview")}
                      onClick={() =>
                        setPreview({
                          kind: "video",
                          url: artifactBffUrl(scene.video.url!),
                          title: t("episode.shotVideoTitle", { number: index + 1 }),
                        })
                      }
                    >
                      <Play className="size-3.5" />
                    </Button>
                  </div>
                </>
              ) : (
                <div className="flex flex-col items-center justify-center gap-1.5 p-3 text-center text-muted-foreground">
                  <Film className="size-6 opacity-40" />
                  <span className="text-[11px] opacity-70">{t("episode.noVideoGenerated")}</span>
                </div>
              )
            )}

            {/* Active generation overlay */}
            {((activeMediaTab === "image" && imageGenerating) || (activeMediaTab === "video" && videoGenerating)) ? (
              <div className="absolute inset-0 bg-background/80 backdrop-blur-xs flex flex-col items-center justify-center gap-1.5 text-primary">
                <Loader2 className="size-5 animate-spin" />
                <span className="text-[11px] font-medium font-mono">{elapsedSeconds}s</span>
              </div>
            ) : null}
          </div>

          {/* Quick Action Button for the active tab */}
          {activeMediaTab === "image" ? (
            <Button
              type="button"
              size="sm"
              variant={hasImage ? "outline" : "default"}
              disabled={busy || !toneReady || saveMutation.isPending}
              title={toneReady ? undefined : t("episode.needsToneSheetFirst")}
              onClick={() => saveBeforeGenerate(onGenerateImage)}
              className="w-full text-xs cursor-pointer justify-center"
            >
              {imageGenerating ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : hasImage ? (
                <RotateCw data-icon="inline-start" />
              ) : (
                <Sparkles data-icon="inline-start" />
              )}
              {hasImage ? t("episode.regenerateImage") : t("episode.generateImage")}
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              variant={hasVideo ? "outline" : "secondary"}
              disabled={busy || !toneReady || videoDisabled || saveMutation.isPending}
              title={!toneReady ? t("episode.needsToneSheetFirst") : videoDisabled ? t("episode.needsImageFirst") : undefined}
              onClick={() => saveBeforeGenerate(onGenerateVideo)}
              className="w-full text-xs cursor-pointer justify-center"
            >
              {videoGenerating ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : (
                <Film data-icon="inline-start" />
              )}
              {hasVideo ? t("episode.regenerateVideo") : t("episode.generateVideo")}
            </Button>
          )}
        </div>
      </div>

      {/* Expanded details section */}
      {open ? (
        <div className="mt-3.5 flex flex-col gap-3 rounded-lg border border-border/50 bg-muted/30 p-3.5 text-xs animate-in fade-in-50 duration-200">
          {/* Visual Settings Section */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground flex items-center gap-1.5">
                <ImageIcon className="size-3.5 text-primary" />
                {t("episode.frameSettings")}
              </span>
              <Button
                type="button"
                size="xs"
                variant="ghost"
                className="h-6 text-[11px] text-muted-foreground hover:text-foreground"
                disabled={compileMutation.isPending}
                onClick={() => compileMutation.mutate("image")}
              >
                <Eye className="mr-1 size-3" />
                {t("episode.finalPromptPreview")}
              </Button>
            </div>

            <Field>
              <FieldLabel htmlFor={`visual-${scene.id}`} className="text-xs text-muted-foreground">
                {t("episode.visualPrompt")}
              </FieldLabel>
              <MentionTextarea
                id={`visual-${scene.id}`}
                value={visualPrompt}
                maxLength={4000}
                rows={2}
                onChange={(event) => setVisualPrompt(event.target.value)}
                references={imageReferences}
                onReferencesChange={setImageReferences}
                assets={imageReferenceAssets}
                limits={{ image: imageReferenceLimit }}
                className="field-sizing-fixed min-h-16 resize-y bg-background/80 text-xs"
              />
            </Field>
          </div>

          <div className="my-1 border-t border-border/40" />

          {/* Motion & Video Settings Section */}
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground flex items-center gap-1.5">
                <Film className="size-3.5 text-primary" />
                {t("episode.motionSettings")}
              </span>
              <Button
                type="button"
                size="xs"
                variant="ghost"
                className="h-6 text-[11px] text-muted-foreground hover:text-foreground"
                disabled={compileMutation.isPending}
                onClick={() => compileMutation.mutate("video")}
              >
                <Eye className="mr-1 size-3" />
                {t("episode.finalPromptPreview")}
              </Button>
            </div>

            <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
              <Field>
                <FieldLabel htmlFor={`shotType-${scene.id}`} className="text-[11px] text-muted-foreground">
                  {t("episode.shotType")}
                </FieldLabel>
                <Input
                  id={`shotType-${scene.id}`}
                  value={shotType}
                  maxLength={80}
                  className="h-8 text-xs bg-background/80"
                  onChange={(event) => setShotType(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor={`cameraMove-${scene.id}`} className="text-[11px] text-muted-foreground">
                  {t("episode.cameraMove")}
                </FieldLabel>
                <Input
                  id={`cameraMove-${scene.id}`}
                  value={cameraMove}
                  maxLength={80}
                  className="h-8 text-xs bg-background/80"
                  onChange={(event) => setCameraMove(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor={`transition-${scene.id}`} className="text-[11px] text-muted-foreground">
                  {t("episode.transition")}
                </FieldLabel>
                <Input
                  id={`transition-${scene.id}`}
                  value={transition}
                  maxLength={80}
                  className="h-8 text-xs bg-background/80"
                  onChange={(event) => setTransition(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor={`seconds-${scene.id}`} className="text-[11px] text-muted-foreground">
                  {t("episode.durationSeconds")}
                </FieldLabel>
                <Input
                  id={`seconds-${scene.id}`}
                  type="number"
                  min={0}
                  max={60}
                  value={seconds}
                  className="h-8 text-xs bg-background/80"
                  onChange={(event) => setSeconds(event.target.value)}
                />
              </Field>
            </div>

            <Field>
              <FieldLabel htmlFor={`videoPrompt-${scene.id}`} className="text-[11px] text-muted-foreground">
                {t("episode.videoPrompt")}
              </FieldLabel>
              <MentionTextarea
                id={`videoPrompt-${scene.id}`}
                value={videoPrompt}
                maxLength={4000}
                rows={2}
                placeholder={t("episode.videoPromptPlaceholder")}
                onChange={(event) => setVideoPrompt(event.target.value)}
                references={videoReferences}
                onReferencesChange={setVideoReferences}
                assets={videoReferenceAssets}
                limits={videoReferenceLimits}
                className="field-sizing-fixed min-h-16 resize-y bg-background/80 text-xs"
              />
            </Field>
          </div>
        </div>
      ) : null}

      {/* Card bottom bar: Save button and Delete button */}
      <div className="mt-3 flex items-center justify-between border-t border-border/40 pt-2.5">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="xs"
            variant={dirty ? "default" : "outline"}
            disabled={saveMutation.isPending || !dirty}
            onClick={() => saveMutation.mutate()}
            className="cursor-pointer"
          >
            {saveMutation.isPending ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Save data-icon="inline-start" />
            )}
            {t("common.save")}
          </Button>
        </div>

        <Button
          type="button"
          size="xs"
          variant="ghost"
          disabled={busy || deleteMutation.isPending}
          onClick={() => deleteMutation.mutate()}
          className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive cursor-pointer"
        >
          <Trash2 className="mr-1 size-3.5" />
          {t("episode.deleteShot")}
        </Button>
      </div>

      {/* Preview Dialog */}
      <MediaPreviewDialog item={preview} onOpenChange={(isOpen) => !isOpen && setPreview(null)} />

      {/* Compiled Prompt Preview Dialog */}
      <Dialog open={compiledPrompt !== null} onOpenChange={(isOpen) => !isOpen && setCompiledPrompt(null)}>
        <DialogContent className="max-h-[85vh] max-w-2xl overflow-hidden">
          <DialogHeader>
            <DialogTitle className="text-sm">{t("episode.finalPromptPreview")}</DialogTitle>
          </DialogHeader>
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-3 text-xs leading-relaxed font-mono">
            {compiledPrompt}
          </pre>
          <Button size="sm" className="self-end cursor-pointer" onClick={() => setCompiledPrompt(null)}>
            {t("common.close")}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
