"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { isCancel } from "axios";
import { Check, Film, ImageIcon, Loader2, Save, Trash2 } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import { deleteProjectSceneAction, updateProjectSceneAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Character, Scene } from "@/types/project";

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
  onError: (message: string) => void;
}

/**
 * One shot: everything the breakdown produced for it, editable, plus the two things that
 * can be generated from it.
 *
 * The clip button stays disabled until the frame exists. That ordering is not a UI
 * preference — the video model takes the storyboard frame as its first-frame reference, so
 * a clip generated before the frame either fails outright or invents an unrelated opening.
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
  const [seconds, setSeconds] = useState(scene.durationMs ? String(Math.round(scene.durationMs / 1000)) : "");
  const [open, setOpen] = useState(false);

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

  return (
    <div
      className={cn(
        "grid gap-3 rounded-lg border p-3 transition-colors md:grid-cols-[auto_minmax(0,1fr)_220px]",
        selected ? "border-primary bg-primary/5" : "border-border/60"
      )}
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
        </div>

        <Textarea
          value={narration}
          maxLength={4000}
          rows={2}
          placeholder={t("episode.shotPlaceholder")}
          onChange={(event) => setNarration(event.target.value)}
          className="field-sizing-fixed min-h-16 resize-y"
        />

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
              <Textarea
                id={`visual-${scene.id}`}
                value={visualPrompt}
                maxLength={4000}
                rows={2}
                onChange={(event) => setVisualPrompt(event.target.value)}
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
              <Textarea
                id={`videoPrompt-${scene.id}`}
                value={videoPrompt}
                maxLength={4000}
                rows={2}
                placeholder={t("episode.videoPromptPlaceholder")}
                onChange={(event) => setVideoPrompt(event.target.value)}
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
            <Image src={scene.image.url} alt="" fill unoptimized sizes="220px" className="object-cover" />
          ) : (
            <ImageIcon className="size-5 text-muted-foreground" />
          )}
        </span>
        <Button type="button" size="sm" variant="outline" disabled={busy} onClick={onGenerateImage}>
          {hasImage ? t("episode.regenerateImage") : t("episode.generateImage")}
        </Button>

        {scene.video.url ? (
          <video src={scene.video.url} controls className="w-full rounded-lg border border-border/60" />
        ) : null}
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={busy || !hasImage}
          title={hasImage ? undefined : t("episode.needsImageFirst")}
          onClick={onGenerateVideo}
        >
          <Film data-icon="inline-start" />
          {scene.video.url ? t("episode.regenerateVideo") : t("episode.generateVideo")}
        </Button>
      </div>
    </div>
  );
}
