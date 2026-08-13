"use client";

import { CSS } from "@dnd-kit/utilities";
import { useSortable } from "@dnd-kit/sortable";
import { Film, GripVertical, Image as ImageIcon, Lock, LockOpen, Mic, RefreshCw, Trash2 } from "lucide-react";
import Image from "next/image";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n";
import { backendBaseURL } from "@/lib/http/backend-client";
import { cn } from "@/lib/utils";
import type { SceneEdit } from "@/store/project-store";
import type { Character, Scene } from "@/types/project";

/** Stands in for "nobody speaks": Select cannot carry an empty string as a value. */
const NO_SPEAKER = "__none__";

interface SceneCardProps {
  scene: Scene;
  /** The series bible, so a shot can be cast and given a speaker. */
  characters: Character[];
  onNarrationChange: (value: string) => void;
  onPromptChange: (value: string) => void;
  /** The storyboard fields beyond narration and prompt: dialogue, framing, timing, lock. */
  onFieldChange: (patch: SceneEdit) => void;
  onCastChange: (characterIds: string[]) => void;
  selected: boolean;
  disabled: boolean;
  onSelectedChange: (selected: boolean) => void;
  onGenerate: (media: "image" | "audio" | "video") => void;
  onDelete: () => void;
}

export function SceneCard({
  scene,
  characters,
  onNarrationChange,
  onPromptChange,
  onFieldChange,
  onCastChange,
  selected,
  disabled,
  onSelectedChange,
  onGenerate,
  onDelete,
}: SceneCardProps) {
  const { t } = useI18n();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: scene.id,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const resolvedImageURL =
    scene.image.url && scene.image.url.startsWith("/")
      ? `${backendBaseURL}${scene.image.url}`
      : scene.image.url;
  const resolvedVideoURL =
    scene.video.url && scene.video.url.startsWith("/")
      ? `${backendBaseURL}${scene.video.url}`
      : scene.video.url;

  const statusLabel: Record<Scene["image"]["status"], string> = {
    idle: t("scene.status.idle"),
    generating: t("scene.status.generating"),
    success: t("scene.status.success"),
    error: t("scene.status.error"),
  };

  return (
    <Card
      ref={setNodeRef}
      style={style}
      className={cn(
        "border-border/80 bg-card/80 backdrop-blur-sm",
        isDragging ? "opacity-60 ring-1 ring-primary/40" : "opacity-100"
      )}
    >
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={selected}
              onChange={(event) => onSelectedChange(event.target.checked)}
              aria-label={t("scene.select", { order: scene.order })}
              className="size-4 accent-primary"
            />
            <CardTitle className="text-base font-semibold">{t("scene.sceneLabel", { order: scene.order })}</CardTitle>
          </label>
          <button
            type="button"
            aria-label={t("scene.dragSort")}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted"
            {...attributes}
            {...listeners}
          >
            <GripVertical className="size-4" />
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant="secondary" className="gap-1">
            <ImageIcon className="size-3.5" />
            {t("scene.imageStatus", { status: statusLabel[scene.image.status] })}
          </Badge>
          <Badge variant="secondary" className="gap-1">
            <Mic className="size-3.5" />
            {t("scene.audioStatus", { status: statusLabel[scene.audio.status] })}
          </Badge>
          <Badge variant="secondary" className="gap-1">
            <Film className="size-3.5" />
            {t("scene.videoStatus", { status: statusLabel[scene.video.status] })}
          </Badge>
          {scene.isLocked ? (
            <Badge variant="outline" className="gap-1">
              <Lock className="size-3.5" />
              {t("scene.locked")}
            </Badge>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="ml-auto h-7 px-2 text-xs text-muted-foreground"
            onClick={() => onFieldChange({ isLocked: !scene.isLocked })}
          >
            {scene.isLocked ? <LockOpen className="mr-1 size-3.5" /> : <Lock className="mr-1 size-3.5" />}
            {scene.isLocked ? t("scene.unlock") : t("scene.lock")}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => onGenerate("image")} disabled={disabled || scene.isLocked}>
            <ImageIcon />
            {scene.image.status === "error" ? t("scene.retryImage") : t("scene.generateImage")}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => onGenerate("audio")} disabled={disabled || scene.isLocked}>
            <Mic />
            {scene.audio.status === "error" ? t("scene.retryAudio") : t("scene.generateAudio")}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => onGenerate("video")} disabled={disabled || scene.isLocked}>
            <Film />
            {scene.video.status === "error" ? t("scene.retryVideo") : t("scene.generateVideo")}
          </Button>
          {(scene.image.status === "error" || scene.audio.status === "error" || scene.video.status === "error") ? (
            <RefreshCw className="size-3.5 text-destructive" aria-hidden="true" />
          ) : null}
          <Button type="button" size="icon-sm" variant="ghost" onClick={onDelete} disabled={disabled} title={t("scene.delete")}>
            <Trash2 className="text-destructive" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {scene.errorMessage ? (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1.5 text-xs text-destructive">
            {scene.errorMessage}
          </p>
        ) : null}

        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{t("scene.imageProgress")}</span>
            <span>{scene.image.progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className={cn("h-full transition-all duration-500", scene.image.status === "success" ? "bg-emerald-500" : "bg-primary")}
              style={{ width: `${scene.image.progress}%` }}
            />
          </div>

          {scene.image.status === "generating" ? <Skeleton className="h-20 w-full" /> : null}
          {scene.image.status === "success" ? (
            <div className="space-y-2">
              {resolvedImageURL ? (
                <Image
                  src={resolvedImageURL}
                  alt={`Scene ${scene.order}`}
                  width={1536}
                  height={1024}
                  unoptimized
                  className="h-auto w-full rounded-md border border-border/70 object-cover"
                />
              ) : null}
              <div className="rounded-md border border-border/70 bg-muted/30 px-2 py-1 text-xs text-muted-foreground">
                {t("scene.imageReady")} {resolvedImageURL ? "(AI ready)" : ""}
              </div>
            </div>
          ) : null}
        </div>

        {scene.video.status !== "idle" ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{t("scene.videoProgress")}</span>
              <span>{scene.video.progress}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-cyan-500 transition-all duration-500" style={{ width: `${scene.video.progress}%` }} />
            </div>
            {resolvedVideoURL ? <video src={resolvedVideoURL} controls className="aspect-video w-full rounded-md border border-border/70 bg-black" /> : null}
          </div>
        ) : null}

        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{t("scene.audioProgress")}</span>
            <span>{scene.audio.progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-emerald-500 transition-all duration-500"
              style={{ width: `${scene.audio.progress}%` }}
            />
          </div>

          {scene.audio.status === "success" ? (
            <div className="rounded-md border border-border/70 bg-muted/30 px-2 py-1 text-xs text-muted-foreground">
              {t("scene.audioReady", { duration: scene.audio.duration.toFixed(1) })}
            </div>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor={`narration_${scene.id}`}>{t("scene.narration")}</Label>
          <Textarea
            id={`narration_${scene.id}`}
            value={scene.narration}
            onChange={(event) => onNarrationChange(event.target.value)}
            className="min-h-20"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor={`prompt_${scene.id}`}>{t("scene.prompt")}</Label>
          <Textarea
            id={`prompt_${scene.id}`}
            value={scene.visualPrompt}
            onChange={(event) => onPromptChange(event.target.value)}
            className="min-h-24"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor={`dialogue_${scene.id}`}>{t("scene.dialogue")}</Label>
          <Textarea
            id={`dialogue_${scene.id}`}
            value={scene.dialogue}
            onChange={(event) => onFieldChange({ dialogue: event.target.value })}
            className="min-h-16"
            placeholder={t("scene.dialoguePlaceholder")}
          />
        </div>

        {characters.length > 0 ? (
          <div className="space-y-3">
            <div className="space-y-2">
              <Label>{t("scene.cast")}</Label>
              {/* Toggles rather than a combobox: a cast is short, and seeing every card at
                  once is what makes a missing character obvious. */}
              <div className="flex flex-wrap gap-2">
                {characters.map((character) => {
                  const cast = scene.characterIds.includes(character.id);
                  return (
                    <Button
                      key={character.id}
                      type="button"
                      size="sm"
                      variant={cast ? "default" : "outline"}
                      onClick={() =>
                        onCastChange(
                          cast
                            ? scene.characterIds.filter((id) => id !== character.id)
                            : [...scene.characterIds, character.id]
                        )
                      }
                    >
                      {character.name}
                    </Button>
                  );
                })}
              </div>
              <p className="text-xs text-muted-foreground">{t("scene.castHint")}</p>
            </div>

            <div className="space-y-2">
              <Label>{t("scene.speaker")}</Label>
              <Select
                value={scene.speakerCharacterId ?? NO_SPEAKER}
                onValueChange={(value) =>
                  // "" clears it; the Select can also hand back null when nothing is picked.
                  onFieldChange({ speakerCharacterId: !value || value === NO_SPEAKER ? "" : value })
                }
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_SPEAKER}>{t("scene.speakerNone")}</SelectItem>
                  {characters.map((character) => (
                    <SelectItem key={character.id} value={character.id}>
                      {character.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">{t("scene.speakerHint")}</p>
            </div>
          </div>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-2">
            <Label htmlFor={`shot_${scene.id}`}>{t("scene.shotType")}</Label>
            <Input
              id={`shot_${scene.id}`}
              value={scene.shotType}
              onChange={(event) => onFieldChange({ shotType: event.target.value })}
              placeholder={t("scene.shotTypePlaceholder")}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`camera_${scene.id}`}>{t("scene.cameraMove")}</Label>
            <Input
              id={`camera_${scene.id}`}
              value={scene.cameraMove}
              onChange={(event) => onFieldChange({ cameraMove: event.target.value })}
              placeholder={t("scene.cameraMovePlaceholder")}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`duration_${scene.id}`}>{t("scene.durationMs")}</Label>
            <Input
              id={`duration_${scene.id}`}
              type="number"
              min={0}
              max={600000}
              step={100}
              value={scene.durationMs}
              onChange={(event) => {
                const parsed = Number(event.target.value);
                onFieldChange({ durationMs: Number.isFinite(parsed) && parsed >= 0 ? parsed : 0 });
              }}
            />
            {/* 0 is not "no length" — it hands the shot back to its voice track. */}
            <p className="text-xs text-muted-foreground">{t("scene.durationHint")}</p>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor={`subtitle_${scene.id}`}>{t("scene.subtitleText")}</Label>
          <Textarea
            id={`subtitle_${scene.id}`}
            value={scene.subtitleText}
            onChange={(event) => onFieldChange({ subtitleText: event.target.value })}
            className="min-h-16"
            placeholder={t("scene.subtitlePlaceholder")}
          />
        </div>
      </CardContent>
    </Card>
  );
}
