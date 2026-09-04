"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { isCancel } from "axios";
import {
  Camera,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
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
import { compilePromptAction, listPromptPrefixPresetsAction } from "@/actions/prompt-actions";
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
import { remainingBudget, type MediaLimits } from "@/lib/reference-budget";
import { cn } from "@/lib/utils";
import type { Scene } from "@/types/project";
import type { GenerationReferenceInput, PromptPrefix } from "@/types/project";
import type { ReferenceAssetOption } from "./reference-picker";
import { MentionTextarea } from "./mention-textarea";
import { PromptPrefixList } from "./prompt-prefix-list";
import { MediaPreviewDialog } from "./media-preview-dialog";


const referenceKey = (item: GenerationReferenceInput) => `${item.kind}:${item.id}`;

/**
 * Per-media budget left for one editor once its siblings in the prompt group are deducted.
 *
 * A shot's prefixes and its own prompt share one pool of provider reference slots, so each
 * editor is offered what is still free rather than the full cap — see `lib/reference-budget`
 * for why an asset held by both sides is one slot, not two.
 */
const budgetFor = (
  own: GenerationReferenceInput[],
  siblings: GenerationReferenceInput[][],
  assets: ReferenceAssetOption[],
  limits: MediaLimits,
) =>
  remainingBudget(
    own,
    siblings,
    (key) => assets.find((asset) => referenceKey(asset) === key)?.media,
    limits,
  );
/**
 * A frame slot is not a reference: the render passes it as `first_frame`/`last_frame` and
 * strips it back out of the reference list, so it is never one of the numbered `图N` the
 * prompt can talk about. Picking one therefore adds no chip and no `@mention`.
 */
const parseFrameValue = (value: string): GenerationReferenceInput | null => {
  if (!value) return null;
  const separator = value.indexOf(":");
  return {
    kind: value.slice(0, separator) as GenerationReferenceInput["kind"],
    id: value.slice(separator + 1),
  };
};
const withDefaultMentions = (
  prompt: string,
  references: GenerationReferenceInput[],
  assets: ReferenceAssetOption[]
) =>
  references.reduce((value, reference) => {
    const asset = assets.find((item) => referenceKey(item) === referenceKey(reference));
    return asset && !value.includes(`@${asset.label}`) ? `${value.trim()} @${asset.label}`.trim() : value;
  }, prompt.trim());

const effectiveReferences = (
  saved: GenerationReferenceInput[],
  defaults: GenerationReferenceInput[],
) => saved.length ? saved : defaults;

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
  supportsStartEndFrames?: boolean;
  supportsFirstFrame?: boolean;
  supportsLastFrame?: boolean;
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
  supportsStartEndFrames = false,
  supportsFirstFrame = supportsStartEndFrames,
  supportsLastFrame = supportsStartEndFrames,
  onError,
}: ShotRowProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [narration, setNarration] = useState(scene.narration);
  const [visualPrompt, setVisualPrompt] = useState(() =>
    withDefaultMentions(
      scene.visualPrompt,
      effectiveReferences(scene.imageReferences, scene.imageReferencesExplicit ? [] : defaultImageReferences),
      imageReferenceAssets
    )
  );
  const [shotType, setShotType] = useState(scene.shotType);
  const [cameraMove, setCameraMove] = useState(scene.cameraMove);
  const [transition, setTransition] = useState(scene.transition);
  const [videoPrompt, setVideoPrompt] = useState(() =>
    withDefaultMentions(
      scene.videoPrompt,
      effectiveReferences(scene.videoReferences, scene.videoReferencesExplicit ? [] : defaultVideoReferences),
      videoReferenceAssets
    )
  );
  const [imageReferences, setImageReferences] = useState<GenerationReferenceInput[]>(
    effectiveReferences(scene.imageReferences, scene.imageReferencesExplicit ? [] : defaultImageReferences)
  );
  const [videoReferences, setVideoReferences] = useState<GenerationReferenceInput[]>(
    effectiveReferences(scene.videoReferences, scene.videoReferencesExplicit ? [] : defaultVideoReferences)
  );
  const [imagePrefixes, setImagePrefixes] = useState<PromptPrefix[]>(scene.imagePromptPrefixes ?? []);
  const [videoPrefixes, setVideoPrefixes] = useState<PromptPrefix[]>(scene.videoPromptPrefixes ?? []);
  // Just the stored value. The "use this shot's own render" suggestion lives in
  // `effectiveFirstFrame` alone, so there is one place that decides it.
  const [videoFirstFrame, setVideoFirstFrame] = useState<GenerationReferenceInput | null>(scene.videoFirstFrame ?? null);
  const [firstFrameTouched, setFirstFrameTouched] = useState(false);
  const [videoLastFrame, setVideoLastFrame] = useState<GenerationReferenceInput | null>(scene.videoLastFrame ?? null);
  const [seconds, setSeconds] = useState(scene.durationMs ? String(Math.round(scene.durationMs / 1000)) : "");
  const [open, setOpen] = useState(false);
  const [userMediaTab, setUserMediaTab] = useState<"image" | "video" | null>(null);
  const activeMediaTab =
    userMediaTab ??
    (videoGenerating ? "video" : imageGenerating ? "image" : scene.video.url && !scene.image.url ? "video" : "image");
  const setActiveMediaTab = (tab: "image" | "video") => setUserMediaTab(tab);
  const [preview, setPreview] = useState<{ kind: "image" | "video"; url: string; title: string } | null>(null);
  const [compiledPrompt, setCompiledPrompt] = useState<string | null>(null);
  const [promptCopied, setPromptCopied] = useState(false);

  const handleCopyPrompt = async () => {
    if (!compiledPrompt) return;
    try {
      await navigator.clipboard.writeText(compiledPrompt);
      setPromptCopied(true);
      window.setTimeout(() => setPromptCopied(false), 2000);
    } catch {
      // 降级使用 textarea 复制
      const textarea = document.createElement("textarea");
      textarea.value = compiledPrompt;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setPromptCopied(true);
      window.setTimeout(() => setPromptCopied(false), 2000);
    }
  };
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
    if (imageDefaultsApplied.current || scene.imageReferences.length || scene.imageReferencesExplicit || !resolvedDefaults.length) return;
    imageDefaultsApplied.current = true;
    setImageReferences(resolvedDefaults);
    setVisualPrompt((current) => withDefaultMentions(current, resolvedDefaults, imageReferenceAssets));
  }, [defaultImageReferences, imageReferenceAssets, scene.imageReferences, scene.imageReferencesExplicit]);

  const effectiveFirstFrame = videoFirstFrame ?? (
    // Only suggest the shot's own render while nobody has decided. Once the user has
    // saved a choice — including "不使用" — the slot is theirs and the suggestion stops.
    !firstFrameTouched && !scene.videoFirstFrameExplicit && supportsFirstFrame && !scene.videoFirstFrame && scene.image.url
      ? { kind: "sceneImage" as const, id: scene.id }
      : null
  );

  useEffect(() => {
    const resolvedDefaults = defaultVideoReferences.filter((reference) =>
      videoReferenceAssets.some((asset) => referenceKey(asset) === referenceKey(reference))
    );
    if (videoDefaultsApplied.current || scene.videoReferences.length || scene.videoReferencesExplicit || !resolvedDefaults.length) return;
    videoDefaultsApplied.current = true;
    setVideoReferences(resolvedDefaults);
    setVideoPrompt((current) => withDefaultMentions(current, resolvedDefaults, videoReferenceAssets));
  }, [defaultVideoReferences, videoReferenceAssets, scene.videoReferences, scene.videoReferencesExplicit]);

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
      // Re-seeded with everything else: a tone-sheet run rewrites these server-side, so a
      // row holding the pre-anchor list would silently save the old preamble back.
      setImagePrefixes(scene.imagePromptPrefixes ?? []);
      setVideoPrefixes(scene.videoPromptPrefixes ?? []);
      // Re-seed the frame slots too, or a saved "不使用首帧" reads back as the old value
      // and the row keeps showing what the user just cleared.
      setVideoFirstFrame(scene.videoFirstFrame ?? null);
      setVideoLastFrame(scene.videoLastFrame ?? null);
      setFirstFrameTouched(false);
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
    scene.imagePromptPrefixes,
    scene.videoPromptPrefixes,
    scene.videoFirstFrame,
    scene.videoLastFrame,
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
    JSON.stringify(imagePrefixes) !== JSON.stringify(scene.imagePromptPrefixes ?? []) ||
    JSON.stringify(videoPrefixes) !== JSON.stringify(scene.videoPromptPrefixes ?? []) ||
    JSON.stringify(effectiveFirstFrame) !== JSON.stringify(scene.videoFirstFrame ?? null) ||
    JSON.stringify(videoLastFrame) !== JSON.stringify(scene.videoLastFrame ?? null) ||
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
        imagePromptPrefixes: imagePrefixes,
        videoPromptPrefixes: videoPrefixes,
        // "" rather than null: the backend reads an absent key and a null alike as
        // "leave alone", so null could never clear a frame the user turned off.
        videoFirstFrame: effectiveFirstFrame ?? "",
        videoLastFrame: videoLastFrame ?? "",
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
        prefixes: kind === "image" ? imagePrefixes : videoPrefixes,
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

  // What the shot actually spends, prefixes included: the pills report the number the
  // backend enforces, not just the references picked beside the main prompt.
  const imageGroup = [...imagePrefixes.map((item) => item.references), imageReferences];
  const videoGroup = [...videoPrefixes.map((item) => item.references), videoReferences];
  const imageSpend = new Set(imageGroup.flat().map(referenceKey)).size;
  const videoSpendByMedia = (media: ReferenceAssetOption["media"]) =>
    new Set(
      videoGroup
        .flat()
        .filter(
          (item) =>
            videoReferenceAssets.find((asset) => asset.kind === item.kind && asset.id === item.id)?.media === media
        )
        .map(referenceKey)
    ).size;

  const videoRefCounts = {
    image: videoSpendByMedia("image"),
    video: videoSpendByMedia("video"),
    audio: videoSpendByMedia("audio"),
  };

  // The quick-fill bar is always shown, disabled with a reason until an anchor exists —
  // a button that simply is not there reads as a missing feature rather than a prerequisite.
  const prefixPreset = () =>
    listPromptPrefixPresetsAction(projectId, scene.id).then((result) => result.presets[0] ?? null);

  // Frame slots take a still, whatever its source.
  const frameOptions = videoReferenceAssets.filter((asset) => asset.media === "image");

  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-xl border bg-card/75 p-4 transition-all duration-200 shadow-xs",
        "before:absolute before:left-0 before:top-0 before:bottom-0 before:w-1 before:transition-colors",
        selected
          ? "border-primary/60 bg-primary/[0.03] ring-1 ring-primary/25 before:bg-primary shadow-sm"
          : dirty
          ? "border-amber-500/40 before:bg-amber-500 hover:border-amber-500/60 hover:shadow-md"
          : "border-border/70 hover:border-border/90 hover:shadow-md before:bg-transparent",
        generating && "border-primary/70 bg-primary/[0.04] ring-2 ring-primary/30 before:bg-primary"
      )}
      aria-busy={generating}
    >
      {/* Top row: Checkbox, Number badge, Status badges, and Details Toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/40 pb-3 mb-3.5">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-pressed={selected}
            aria-label={t("episode.selectAll")}
            onClick={onToggle}
            className={cn(
              "flex size-5 shrink-0 items-center justify-center rounded-md border transition-all cursor-pointer shadow-xs",
              selected
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border/80 hover:border-primary/60 bg-background/90"
            )}
          >
            {selected ? <Check className="size-3.5 stroke-[2.5]" /> : null}
          </button>

          <div className="flex items-center gap-1 rounded-md bg-muted/60 px-2 py-0.5 text-xs font-mono font-bold text-foreground border border-border/50">
            <span className="text-[10px] text-muted-foreground font-normal">#</span>
            <span>{String(index + 1).padStart(2, "0")}</span>
          </div>

          {/* Quick status chips with status dot */}
          <div className="flex items-center gap-1.5">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium border transition-colors",
                scene.image.status === "success"
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : scene.image.status === "error"
                  ? "border-destructive/40 bg-destructive/10 text-destructive"
                  : "border-border/60 bg-muted/40 text-muted-foreground"
              )}
            >
              <span
                className={cn(
                  "size-1.5 rounded-full shrink-0",
                  scene.image.status === "success"
                    ? "bg-emerald-500"
                    : scene.image.status === "error"
                    ? "bg-destructive"
                    : "bg-muted-foreground/40"
                )}
              />
              <ImageIcon className="size-3" />
              {scene.image.status === "success" ? t("episode.imageStatusReady") : scene.image.status === "error" ? t("episode.imageStatusError") : scene.image.status}
            </span>

            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium border transition-colors",
                scene.video.status === "success"
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : scene.video.status === "error"
                  ? "border-destructive/40 bg-destructive/10 text-destructive"
                  : "border-border/60 bg-muted/40 text-muted-foreground"
              )}
            >
              <span
                className={cn(
                  "size-1.5 rounded-full shrink-0",
                  scene.video.status === "success"
                    ? "bg-emerald-500"
                    : scene.video.status === "error"
                    ? "bg-destructive"
                    : "bg-muted-foreground/40"
                )}
              />
              <Film className="size-3" />
              {scene.video.status === "success" ? t("episode.videoStatusReady") : scene.video.status === "error" ? t("episode.videoStatusError") : scene.video.status}
            </span>
          </div>

          {/* Shot metadata badges */}
          {scene.shotType ? (
            <Badge variant="outline" className="text-[11px] text-muted-foreground bg-muted/30 border-border/50 font-normal">
              {scene.shotType}
            </Badge>
          ) : null}
          {scene.cameraMove ? (
            <Badge variant="outline" className="text-[11px] text-muted-foreground bg-muted/30 border-border/50 font-normal">
              <Camera className="mr-1 size-2.5 text-muted-foreground/70" />
              {scene.cameraMove}
            </Badge>
          ) : null}
          {scene.transition ? (
            <Badge variant="outline" className="text-[11px] text-muted-foreground bg-muted/30 border-border/50 font-normal">
              {scene.transition}
            </Badge>
          ) : null}
          {scene.durationMs ? (
            <Badge variant="outline" className="text-[11px] text-muted-foreground bg-muted/30 border-border/50 font-normal">
              <Clock className="mr-1 size-2.5 text-muted-foreground/70" />
              {Math.round(scene.durationMs / 1000)}s
            </Badge>
          ) : null}

          {dirty ? (
            <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px] gap-1 animate-in fade-in">
              <span className="size-1 rounded-full bg-amber-500 animate-pulse" />
              {t("episode.unsavedChanges")}
            </Badge>
          ) : null}

          {generating ? (
            <Badge variant="secondary" className="border-primary/30 bg-primary/10 text-primary text-[11px] gap-1.5 animate-pulse">
              <Loader2 className="size-3 animate-spin" />
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
            className="text-xs gap-1 text-muted-foreground hover:text-foreground cursor-pointer transition-colors"
          >
            <span>{t("episode.shotDetails")}</span>
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
              className="field-sizing-fixed min-h-20 resize-y bg-background/70 leading-relaxed text-sm focus-visible:ring-1 focus-visible:ring-primary shadow-xs"
            />
          </div>

          {/* Reference asset counts pills */}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            {imageReferenceLimit > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-muted/40 px-2 py-0.5 border border-border/40">
                <ImageIcon className="size-3 text-muted-foreground/70" />
                {t("episode.shotImageReferences", { count: imageSpend, limit: imageReferenceLimit })}
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
            <p className="rounded-md bg-destructive/10 border border-destructive/20 px-2.5 py-1.5 text-xs text-destructive flex items-center gap-1.5">
              <span className="size-1.5 rounded-full bg-destructive shrink-0" />
              {scene.errorMessage}
            </p>
          ) : null}
        </div>

        {/* Right column: Compact Media Switcher Box (Image & Video Tab) */}
        <div className="flex flex-col gap-2 rounded-xl border border-border/60 bg-muted/30 p-2.5 shadow-xs">
          {/* Media Tab Header */}
          <div className="flex items-center justify-between rounded-lg bg-muted/70 p-0.5 border border-border/40">
            <button
              type="button"
              onClick={() => setActiveMediaTab("image")}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-md py-1 text-xs font-medium transition-all cursor-pointer",
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
                "flex flex-1 items-center justify-center gap-1.5 rounded-md py-1 text-xs font-medium transition-all cursor-pointer",
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
          <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-border/60 bg-background/80 flex items-center justify-center group/media shadow-inner">
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
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/media:opacity-100 transition-opacity flex items-center justify-center gap-2 backdrop-blur-xs">
                    <Button
                      type="button"
                      size="icon-xs"
                      variant="secondary"
                      className="rounded-full shadow-md cursor-pointer hover:scale-110 transition-transform"
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
                  <div className="flex size-9 items-center justify-center rounded-full bg-muted/60 border border-border/50">
                    <ImageIcon className="size-4 opacity-50" />
                  </div>
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
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/media:opacity-100 transition-opacity flex items-center justify-center gap-2 backdrop-blur-xs">
                    <Button
                      type="button"
                      size="icon-xs"
                      variant="secondary"
                      className="rounded-full shadow-md cursor-pointer hover:scale-110 transition-transform"
                      title={t("episode.openPreview")}
                      onClick={() =>
                        setPreview({
                          kind: "video",
                          url: artifactBffUrl(scene.video.url!),
                          title: t("episode.shotVideoTitle", { number: index + 1 }),
                        })
                      }
                    >
                      <Play className="size-3.5 fill-current" />
                    </Button>
                  </div>
                </>
              ) : (
                <div className="flex flex-col items-center justify-center gap-1.5 p-3 text-center text-muted-foreground">
                  <div className="flex size-9 items-center justify-center rounded-full bg-muted/60 border border-border/50">
                    <Film className="size-4 opacity-50" />
                  </div>
                  <span className="text-[11px] opacity-70">{t("episode.noVideoGenerated")}</span>
                </div>
              )
            )}

            {/* Active generation overlay */}
            {((activeMediaTab === "image" && imageGenerating) || (activeMediaTab === "video" && videoGenerating)) ? (
              <div className="absolute inset-0 bg-background/85 backdrop-blur-xs flex flex-col items-center justify-center gap-2 text-primary">
                <Loader2 className="size-6 animate-spin" />
                <span className="text-xs font-semibold font-mono">{elapsedSeconds}s</span>
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
              className="w-full text-xs cursor-pointer justify-center shadow-xs"
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
              className="w-full text-xs cursor-pointer justify-center shadow-xs"
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
        <div className="mt-4 flex flex-col gap-4 rounded-xl border border-border/50 bg-muted/20 p-4 text-xs animate-in fade-in-50 duration-200">
          {/* Visual Settings Card */}
          <div className="flex flex-col gap-3 rounded-lg border border-border/40 bg-card/50 p-3.5 shadow-xs">
            <div className="flex items-center justify-between pb-1 border-b border-border/30">
              <span className="font-semibold text-foreground flex items-center gap-1.5 text-xs">
                <ImageIcon className="size-3.5 text-primary" />
                {t("episode.frameSettings")}
              </span>
              <Button
                type="button"
                size="xs"
                variant="ghost"
                className="h-6 text-[11px] text-muted-foreground hover:text-foreground cursor-pointer"
                disabled={compileMutation.isPending}
                onClick={() => compileMutation.mutate("image")}
              >
                <Eye className="mr-1 size-3" />
                {t("episode.finalPromptPreview")}
              </Button>
            </div>

            <Field>
              <FieldLabel className="text-xs text-muted-foreground font-medium">
                {t("episode.imagePromptPrefixes")}
              </FieldLabel>
              <PromptPrefixList
                prefixes={imagePrefixes}
                onChange={setImagePrefixes}
                assets={imageReferenceAssets}
                limitsFor={(index) =>
                  budgetFor(
                    imagePrefixes[index]?.references ?? [],
                    imageGroup.filter((_, position) => position !== index),
                    imageReferenceAssets,
                    { image: imageReferenceLimit }
                  )
                }
                preset={prefixPreset}
                presetDisabled={!toneReady}
                presetDisabledReason={t("episode.needsToneSheetFirst")}
                disabled={busy}
              />
            </Field>

            <Field>
              <FieldLabel htmlFor={`visual-${scene.id}`} className="text-xs text-muted-foreground font-medium">
                {t("episode.visualPrompt")}
              </FieldLabel>
              <MentionTextarea
                id={`visual-${scene.id}`}
                value={visualPrompt}
                maxLength={4000}
                rows={2}
                onChange={(event) => setVisualPrompt(event.target.value)}
                references={imageReferences}
                onReferencesChange={(refs) => setImageReferences(refs)}
                assets={imageReferenceAssets}
                limits={budgetFor(imageReferences, imageGroup.slice(0, -1), imageReferenceAssets, {
                  image: imageReferenceLimit,
                })}
                className="field-sizing-fixed min-h-16 resize-y bg-background/80 text-xs shadow-xs"
              />
            </Field>
          </div>

          {/* Motion & Video Settings Card */}
          <div className="flex flex-col gap-3 rounded-lg border border-border/40 bg-card/50 p-3.5 shadow-xs">
            <div className="flex items-center justify-between pb-1 border-b border-border/30">
              <span className="font-semibold text-foreground flex items-center gap-1.5 text-xs">
                <Film className="size-3.5 text-primary" />
                {t("episode.motionSettings")}
              </span>
              <Button
                type="button"
                size="xs"
                variant="ghost"
                className="h-6 text-[11px] text-muted-foreground hover:text-foreground cursor-pointer"
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
                  className="h-8 text-xs bg-background/80 shadow-xs"
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
                  className="h-8 text-xs bg-background/80 shadow-xs"
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
                  className="h-8 text-xs bg-background/80 shadow-xs"
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
                  className="h-8 text-xs bg-background/80 shadow-xs"
                  onChange={(event) => setSeconds(event.target.value)}
                />
              </Field>
            </div>

            <Field>
              <FieldLabel className="text-[11px] text-muted-foreground font-medium">
                {t("episode.videoPromptPrefixes")}
              </FieldLabel>
              <PromptPrefixList
                prefixes={videoPrefixes}
                onChange={setVideoPrefixes}
                assets={videoReferenceAssets}
                limitsFor={(index) =>
                  budgetFor(
                    videoPrefixes[index]?.references ?? [],
                    videoGroup.filter((_, position) => position !== index),
                    videoReferenceAssets,
                    videoReferenceLimits
                  )
                }
                preset={prefixPreset}
                presetDisabled={!toneReady}
                presetDisabledReason={t("episode.needsToneSheetFirst")}
                disabled={busy}
              />
            </Field>

            <Field>
              <FieldLabel htmlFor={`videoPrompt-${scene.id}`} className="text-[11px] text-muted-foreground font-medium">
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
                onReferencesChange={(refs) => setVideoReferences(refs)}
                assets={videoReferenceAssets}
                limits={budgetFor(videoReferences, videoGroup.slice(0, -1), videoReferenceAssets, videoReferenceLimits)}
                className="field-sizing-fixed min-h-16 resize-y bg-background/80 text-xs shadow-xs"
              />
              {supportsFirstFrame || supportsLastFrame ? (
                <div className="flex flex-wrap gap-3 pt-1 text-xs">
                  {supportsFirstFrame ? (
                    <label className="flex items-center gap-1.5 text-muted-foreground">
                      <span>{t("episode.useFirstFrame")}</span>
                      <select
                        className="h-7.5 rounded-md border border-border/60 bg-background px-2 text-foreground text-xs shadow-xs focus:ring-1 focus:ring-primary outline-none"
                        value={effectiveFirstFrame ? referenceKey(effectiveFirstFrame) : ""}
                        onChange={(event) => {
                          setFirstFrameTouched(true);
                          setVideoFirstFrame(parseFrameValue(event.target.value));
                        }}
                      >
                        <option value="">{t("episode.frameNone")}</option>
                        {frameOptions.map((asset) => (
                          <option key={`first-${referenceKey(asset)}`} value={referenceKey(asset)}>
                            {asset.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                  {supportsLastFrame ? (
                    <label className="flex items-center gap-1.5 text-muted-foreground">
                      <span>{t("episode.useLastFrame")}</span>
                      <select
                        className="h-7.5 rounded-md border border-border/60 bg-background px-2 text-foreground text-xs shadow-xs focus:ring-1 focus:ring-primary outline-none"
                        value={videoLastFrame ? referenceKey(videoLastFrame) : ""}
                        onChange={(event) => setVideoLastFrame(parseFrameValue(event.target.value))}
                      >
                        <option value="">{t("episode.frameNone")}</option>
                        {frameOptions.map((asset) => (
                          <option key={`last-${referenceKey(asset)}`} value={referenceKey(asset)}>
                            {asset.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                </div>
              ) : null}
            </Field>
          </div>
        </div>
      ) : null}

      {/* Card bottom bar: Save button and Delete button */}
      <div className="mt-3.5 flex items-center justify-between border-t border-border/40 pt-2.5">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="xs"
            variant={dirty ? "default" : "outline"}
            disabled={saveMutation.isPending || !dirty}
            onClick={() => saveMutation.mutate()}
            className="cursor-pointer shadow-xs transition-all"
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
          className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive cursor-pointer transition-colors"
        >
          <Trash2 className="mr-1 size-3.5" />
          {t("episode.deleteShot")}
        </Button>
      </div>

      {/* Preview Dialog */}
      <MediaPreviewDialog item={preview} onOpenChange={(isOpen) => !isOpen && setPreview(null)} />

      {/* Compiled Prompt Preview Dialog */}
      <Dialog open={compiledPrompt !== null} onOpenChange={(isOpen) => !isOpen && setCompiledPrompt(null)}>
        <DialogContent className="max-h-[85vh] max-w-2xl overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold">{t("episode.finalPromptPreview")}</DialogTitle>
          </DialogHeader>
          <pre className="max-h-[55vh] flex-1 overflow-auto whitespace-pre-wrap rounded-lg bg-muted/50 p-3.5 text-xs leading-relaxed font-mono border border-border/50 select-text">
            {compiledPrompt}
          </pre>
          <div className="flex items-center justify-between border-t border-border/40 pt-3 mt-1">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={handleCopyPrompt}
              className="gap-1.5 cursor-pointer"
            >
              {promptCopied ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
              <span>{promptCopied ? t("episode.copiedPrompt") : t("episode.copyPrompt")}</span>
            </Button>
            <Button size="sm" className="cursor-pointer" onClick={() => setCompiledPrompt(null)}>
              {t("common.close")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
