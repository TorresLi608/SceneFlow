"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { isCancel } from "axios";
import { Check, Film, ImageIcon, Loader2, Save, Trash2 } from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { deleteProjectSceneAction, updateProjectSceneAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { artifactBffUrl } from "@/lib/artifact-url";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Character, Scene } from "@/types/project";
import type { GenerationReferenceInput } from "@/types/project";
import type { ReferenceAssetOption } from "./reference-picker";
import { MentionTextarea } from "./mention-textarea";
import { MediaPreviewDialog } from "./media-preview-dialog";

export interface ShotRowProps {
  projectId: string;
  scene: Scene;
  index: number;
  characters: Character[];
  selected: boolean;
  onToggle: () => void;
  /** True while any run owns the project; per-shot actions are unavailable then. */
  busy: boolean;
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

/**
 * One shot: everything the breakdown produced for it, editable, plus the two things that
 * can be generated from it.
 *
 * The parent disables clip generation only when the selected model's declared reference
 * requirements are not met; text-to-video models do not need a storyboard frame first.
 */
export function ShotRow({
  projectId,
  scene,
  index,
  characters,
  selected,
  onToggle,
  busy,
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
  const [dialogue, setDialogue] = useState(scene.dialogue);
  const [speaker, setSpeaker] = useState(scene.speakerCharacterId ?? "");
  const [visualPrompt, setVisualPrompt] = useState(scene.visualPrompt);
  const [shotType, setShotType] = useState(scene.shotType);
  const [cameraMove, setCameraMove] = useState(scene.cameraMove);
  const [transition, setTransition] = useState(scene.transition);
  const [videoPrompt, setVideoPrompt] = useState(scene.videoPrompt);
  const [imageReferences, setImageReferences] = useState<GenerationReferenceInput[]>(scene.imageReferences ?? []);
  const [videoReferences, setVideoReferences] = useState<GenerationReferenceInput[]>(scene.videoReferences ?? []);
  const [seconds, setSeconds] = useState(scene.durationMs ? String(Math.round(scene.durationMs / 1000)) : "");
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<{ kind: "image" | "video"; url: string; title: string } | null>(null);
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

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.episode(projectId, scene.episodeId ?? "") });

  const dirty =
    narration !== scene.narration ||
    dialogue !== scene.dialogue ||
    (speaker || null) !== scene.speakerCharacterId ||
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
        dialogue,
        // "" unbinds the speaker; a JSON null would read as "leave it alone".
        speakerCharacterId: speaker,
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

  const statusTone = (status: string) =>
    status === "success" ? "default" : status === "error" ? "destructive" : "outline";

  const speakerItems = [
    { value: "", label: t("episode.speakerNone") },
    ...characters.map((character) => ({ value: character.id, label: character.name })),
  ];

  const hasImage = scene.image.status === "success" && Boolean(scene.image.url);
  const generating = imageGenerating || videoGenerating;

  const saveBeforeGenerate = (action: () => void) => {
    if (!dirty) {
      action();
      return;
    }
    saveMutation.mutate(undefined, { onSuccess: action });
  };

  return (
    <div
      className={cn(
        "grid gap-3 rounded-lg border p-3 transition-colors md:grid-cols-[auto_minmax(0,1fr)_220px]",
        selected ? "border-primary bg-primary/5" : "border-border/60",
        generating && "border-primary/70 bg-primary/5 ring-1 ring-primary/30"
      )}
      aria-busy={generating}
    >
      <button
        type="button"
        aria-pressed={selected}
        aria-label={t("episode.selectAll")}
        onClick={onToggle}
        className={cn(
          "mt-1 flex size-5 shrink-0 items-center justify-center rounded border transition-colors cursor-pointer",
          selected ? "border-primary bg-primary text-primary-foreground" : "border-border hover:border-primary/50"
        )}
      >
        {selected ? <Check className="size-3.5" /> : null}
      </button>

      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{index + 1}</Badge>
          <Badge variant={statusTone(scene.image.status)}>{scene.image.status}</Badge>
          <Badge variant={statusTone(scene.video.status)}>
            <Film className="mr-1 size-3" />
            {scene.video.status}
          </Badge>
          {scene.cameraMove ? <Badge variant="secondary">{scene.cameraMove}</Badge> : null}
          {scene.transition ? <Badge variant="secondary">{scene.transition}</Badge> : null}
          {scene.durationMs ? (
            <Badge variant="secondary">{Math.round(scene.durationMs / 1000)}s</Badge>
          ) : null}
          {scene.errorMessage ? <span className="text-xs text-destructive">{scene.errorMessage}</span> : null}
          {generating ? (
            <Badge variant="secondary" className="text-primary">
              <Loader2 className="mr-1 size-3 animate-spin" />
              {t("episode.generatingSeconds", { seconds: elapsedSeconds })}
            </Badge>
          ) : null}
        </div>

        <Textarea
          value={narration}
          maxLength={4000}
          rows={2}
          placeholder={t("episode.shotPlaceholder")}
          onChange={(event) => setNarration(event.target.value)}
          className="field-sizing-fixed min-h-16 resize-y"
        />

        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          {imageReferenceLimit > 0 ? <span>{t("episode.shotImageReferences", { count: imageReferences.length, limit: imageReferenceLimit })}</span> : null}
          {videoReferenceLimits.image > 0 ? <span>{t("episode.shotVideoReferences", { count: videoReferences.filter((item) => videoReferenceAssets.find((asset) => asset.kind === item.kind && asset.id === item.id)?.media === "image").length, limit: videoReferenceLimits.image })}</span> : null}
          {videoReferenceLimits.video > 0 ? <span>{t("episode.shotVideoReferencesVideo", { count: videoReferences.filter((item) => videoReferenceAssets.find((asset) => asset.kind === item.kind && asset.id === item.id)?.media === "video").length, limit: videoReferenceLimits.video })}</span> : null}
          {videoReferenceLimits.audio > 0 ? <span>{t("episode.shotVideoReferencesAudio", { count: videoReferences.filter((item) => videoReferenceAssets.find((asset) => asset.kind === item.kind && asset.id === item.id)?.media === "audio").length, limit: videoReferenceLimits.audio })}</span> : null}
        </div>

        <button
          type="button"
          onClick={() => setOpen((current) => !current)}
          className="self-start text-xs text-muted-foreground underline-offset-2 hover:underline cursor-pointer"
        >
          {t("episode.shotDetails")}
          {open ? " ▲" : " ▼"}
        </button>

        {open ? (
          <div className="flex flex-col gap-3 rounded-md border border-border/50 bg-muted/20 p-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor={`dialogue-${scene.id}`}>{t("episode.dialogue")}</FieldLabel>
                <Textarea
                  id={`dialogue-${scene.id}`}
                  value={dialogue}
                  maxLength={4000}
                  rows={2}
                  placeholder={t("episode.dialoguePlaceholder")}
                  onChange={(event) => setDialogue(event.target.value)}
                  className="field-sizing-fixed min-h-14 resize-y"
                />
              </Field>
              <Field>
                <FieldLabel htmlFor={`speaker-${scene.id}`}>{t("episode.speaker")}</FieldLabel>
                <Select items={speakerItems} value={speaker} onValueChange={(value) => setSpeaker(value ?? "")}>
                  <SelectTrigger id={`speaker-${scene.id}`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {speakerItems.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
            </div>

            <Field>
              <FieldLabel htmlFor={`visual-${scene.id}`}>{t("episode.visualPrompt")}</FieldLabel>
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
                className="field-sizing-fixed min-h-16 resize-y"
              />
            </Field>

            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("episode.videoDetails")}
            </p>
            <div className="grid gap-3 sm:grid-cols-4">
              <Field>
                <FieldLabel htmlFor={`shotType-${scene.id}`}>{t("episode.shotType")}</FieldLabel>
                <Input
                  id={`shotType-${scene.id}`}
                  value={shotType}
                  maxLength={80}
                  onChange={(event) => setShotType(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor={`cameraMove-${scene.id}`}>{t("episode.cameraMove")}</FieldLabel>
                <Input
                  id={`cameraMove-${scene.id}`}
                  value={cameraMove}
                  maxLength={80}
                  onChange={(event) => setCameraMove(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor={`transition-${scene.id}`}>{t("episode.transition")}</FieldLabel>
                <Input
                  id={`transition-${scene.id}`}
                  value={transition}
                  maxLength={80}
                  onChange={(event) => setTransition(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor={`seconds-${scene.id}`}>{t("episode.durationSeconds")}</FieldLabel>
                <Input
                  id={`seconds-${scene.id}`}
                  type="number"
                  min={0}
                  max={60}
                  value={seconds}
                  onChange={(event) => setSeconds(event.target.value)}
                />
              </Field>
            </div>

            <Field>
              <FieldLabel htmlFor={`videoPrompt-${scene.id}`}>{t("episode.videoPrompt")}</FieldLabel>
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
                className="field-sizing-fixed min-h-16 resize-y"
              />
            </Field>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={saveMutation.isPending || !dirty}
            onClick={() => saveMutation.mutate()}
          >
            {saveMutation.isPending ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Save data-icon="inline-start" />
            )}
            {t("common.save")}
          </Button>
          <Button type="button" size="sm" variant="ghost" disabled={busy || deleteMutation.isPending} onClick={() => deleteMutation.mutate()}>
            <Trash2 data-icon="inline-start" />
            {t("episode.deleteShot")}
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <span className="relative flex aspect-video w-full items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-muted">
          {scene.image.url ? (
            <button
              type="button"
              className="absolute inset-0 cursor-zoom-in"
              aria-label={t("episode.openPreview")}
              onClick={() => setPreview({ kind: "image", url: artifactBffUrl(scene.image.url!), title: t("episode.shotImageTitle", { number: index + 1 }) })}
            >
              <Image src={artifactBffUrl(scene.image.url)} alt="" fill unoptimized sizes="220px" className="object-cover" />
            </button>
          ) : (
            <ImageIcon className="size-5 text-muted-foreground" />
          )}
        </span>
        <Button type="button" size="sm" variant="outline" disabled={busy || saveMutation.isPending} onClick={() => saveBeforeGenerate(onGenerateImage)}>
          {imageGenerating ? <Loader2 data-icon="inline-start" className="animate-spin" /> : null}
          {hasImage ? t("episode.regenerateImage") : t("episode.generateImage")}
        </Button>

        {scene.video.url ? (
          <video
            src={artifactBffUrl(scene.video.url)}
            preload="metadata"
            title={t("episode.openPreview")}
            onClick={() => setPreview({ kind: "video", url: artifactBffUrl(scene.video.url!), title: t("episode.shotVideoTitle", { number: index + 1 }) })}
            className="w-full cursor-zoom-in rounded-lg border border-border/60"
          />
        ) : null}
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={busy || videoDisabled || saveMutation.isPending}
          title={videoDisabled ? t("episode.requiredReferencesMissing") : undefined}
          onClick={() => saveBeforeGenerate(onGenerateVideo)}
        >
          {videoGenerating ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Film data-icon="inline-start" />}
          {scene.video.url ? t("episode.regenerateVideo") : t("episode.generateVideo")}
        </Button>
      </div>
      <MediaPreviewDialog item={preview} onOpenChange={(open) => !open && setPreview(null)} />
    </div>
  );
}
