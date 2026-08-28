"use client";

import { CSS } from "@dnd-kit/utilities";
import { useSortable } from "@dnd-kit/sortable";
import { Film, GripVertical, Image as ImageIcon, Lock, LockOpen, Mic, Trash2 } from "lucide-react";
import Image from "next/image";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n";
import { backendBaseURL } from "@/lib/http/backend-client";
import { cn } from "@/lib/utils";
import type { SceneEdit } from "@/store/project-store";
import type { Character, Scene } from "@/types/project";

interface SceneCardProps {
  scene: Scene;
  /** The series bible, so a shot can carry its cast into generation. */
  characters: Character[];
  onNarrationChange: (value: string) => void;
  onPromptChange: (value: string) => void;
  /** The storyboard fields beyond narration and prompt: dialogue, framing, timing, lock. */
  onFieldChange: (patch: SceneEdit) => void;
  onCastChange: (characterIds: string[]) => void;
  selected: boolean;
  disabled: boolean;
  onSelectedChange: (selected: boolean) => void;
  onGenerate: (media: "image" | "video") => void;
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
        "overflow-hidden rounded-2xl border border-border/70 bg-card/75 shadow-sm backdrop-blur-md transition-all duration-200 hover:border-primary/30 hover:shadow-md",
        isDragging ? "opacity-60 ring-2 ring-primary/40 shadow-xl" : "opacity-100",
        selected && "border-primary/50 bg-primary/[0.02]"
      )}
    >
      <CardHeader className="border-b border-border/50 bg-muted/20 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          <div className="flex items-center gap-2.5">
            <input
              type="checkbox"
              checked={selected}
              onChange={(event) => onSelectedChange(event.target.checked)}
              aria-label={t("scene.select", { order: scene.order })}
              className="size-4 rounded accent-primary cursor-pointer"
            />
            <div className="flex items-center gap-1.5">
              <span className="flex size-6 items-center justify-center rounded-lg bg-primary/10 text-xs font-bold text-primary">
                #{scene.order}
              </span>
              <CardTitle className="text-sm font-bold tracking-tight text-foreground">
                {t("scene.sceneLabel", { order: scene.order })}
              </CardTitle>
            </div>
            {scene.isLocked ? (
              <Badge variant="outline" className="h-5 gap-1 rounded-md px-1.5 text-[10px] text-amber-600 dark:text-amber-400 border-amber-500/30 bg-amber-500/10">
                <Lock className="size-2.5" />
                {t("scene.locked")}
              </Badge>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <Badge variant="secondary" className="h-6 gap-1 rounded-lg px-2 text-[10px] font-medium bg-muted/60">
              <ImageIcon className="size-3 text-muted-foreground" />
              {statusLabel[scene.image.status]}
            </Badge>
            <Badge variant="secondary" className="h-6 gap-1 rounded-lg px-2 text-[10px] font-medium bg-muted/60">
              <Mic className="size-3 text-muted-foreground" />
              {statusLabel[scene.audio.status]}
            </Badge>
            <Badge variant="secondary" className="h-6 gap-1 rounded-lg px-2 text-[10px] font-medium bg-muted/60">
              <Film className="size-3 text-muted-foreground" />
              {statusLabel[scene.video.status]}
            </Badge>

            <div className="mx-1 h-3.5 w-px bg-border/80" />

            <Button
              type="button"
              size="xs"
              variant="outline"
              className="h-6 rounded-lg px-2 text-[11px] gap-1 cursor-pointer"
              onClick={() => onGenerate("image")}
              disabled={disabled || scene.isLocked}
            >
              <ImageIcon className="size-3 text-primary" />
              {scene.image.status === "error" ? t("scene.retryImage") : t("scene.generateImage")}
            </Button>
            <Button
              type="button"
              size="xs"
              variant="outline"
              className="h-6 rounded-lg px-2 text-[11px] gap-1 cursor-pointer"
              onClick={() => onGenerate("video")}
              disabled={disabled || scene.isLocked}
            >
              <Film className="size-3 text-primary" />
              {scene.video.status === "error" ? t("scene.retryVideo") : t("scene.generateVideo")}
            </Button>

            <Button
              type="button"
              size="xs"
              variant="ghost"
              className="h-6 rounded-lg px-1.5 text-[11px] text-muted-foreground hover:bg-muted cursor-pointer"
              onClick={() => onFieldChange({ isLocked: !scene.isLocked })}
              title={scene.isLocked ? t("scene.unlock") : t("scene.lock")}
            >
              {scene.isLocked ? <LockOpen className="size-3 text-amber-500" /> : <Lock className="size-3" />}
            </Button>

            <Button
              type="button"
              size="xs"
              variant="ghost"
              onClick={onDelete}
              disabled={disabled}
              title={t("scene.delete")}
              className="h-6 rounded-lg px-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive cursor-pointer"
            >
              <Trash2 className="size-3" />
            </Button>

            <button
              type="button"
              aria-label={t("scene.dragSort")}
              className="rounded-lg p-1 text-muted-foreground hover:bg-muted/80 hover:text-foreground cursor-grab active:cursor-grabbing"
              {...attributes}
              {...listeners}
            >
              <GripVertical className="size-4" />
            </button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 p-4">
        {scene.errorMessage ? (
          <p className="rounded-xl border border-destructive/40 bg-destructive/10 p-2.5 text-xs text-destructive">
            {scene.errorMessage}
          </p>
        ) : null}

        {/* 媒体展示与进度区域 */}
        <div className="grid gap-3 sm:grid-cols-2">
          {/* 图片区域 */}
          <div className="space-y-1.5 rounded-xl border border-border/50 bg-muted/20 p-2.5">
            <div className="flex items-center justify-between text-[11px] text-muted-foreground font-medium">
              <span className="flex items-center gap-1">
                <ImageIcon className="size-3 text-primary" />
                {t("scene.imageProgress")}
              </span>
              <span>{scene.image.progress}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted/60">
              <div
                className={cn("h-full transition-all duration-500", scene.image.status === "success" ? "bg-emerald-500" : "bg-primary")}
                style={{ width: `${scene.image.progress}%` }}
              />
            </div>

            {scene.image.status === "generating" ? (
              <Skeleton className="aspect-video w-full rounded-lg" />
            ) : null}

            {scene.image.status === "success" && resolvedImageURL ? (
              <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-border/60 bg-black/40 shadow-xs">
                <Image
                  src={resolvedImageURL}
                  alt={`Scene ${scene.order}`}
                  fill
                  unoptimized
                  className="object-cover"
                />
              </div>
            ) : null}
          </div>

          {/* 视频区域 */}
          <div className="space-y-1.5 rounded-xl border border-border/50 bg-muted/20 p-2.5">
            <div className="flex items-center justify-between text-[11px] text-muted-foreground font-medium">
              <span className="flex items-center gap-1">
                <Film className="size-3 text-primary" />
                {t("scene.videoProgress")}
              </span>
              <span>{scene.video.progress}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted/60">
              <div
                className="h-full bg-cyan-500 transition-all duration-500"
                style={{ width: `${scene.video.progress}%` }}
              />
            </div>

            {scene.video.status === "generating" ? (
              <Skeleton className="aspect-video w-full rounded-lg" />
            ) : null}

            {scene.video.status === "success" && resolvedVideoURL ? (
              <video
                src={resolvedVideoURL}
                controls
                className="aspect-video w-full rounded-lg border border-border/60 bg-black"
              />
            ) : null}
          </div>
        </div>

        {/* 文本输入区域 */}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor={`narration_${scene.id}`} className="text-xs font-medium text-foreground">
              {t("scene.narration")}
            </Label>
            <Textarea
              id={`narration_${scene.id}`}
              value={scene.narration}
              onChange={(event) => onNarrationChange(event.target.value)}
              className="min-h-20 resize-none rounded-xl text-xs bg-muted/20 focus-visible:bg-background leading-relaxed"
              placeholder="镜头旁白解说词..."
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor={`prompt_${scene.id}`} className="text-xs font-medium text-foreground">
              {t("scene.prompt")}
            </Label>
            <Textarea
              id={`prompt_${scene.id}`}
              value={scene.visualPrompt}
              onChange={(event) => onPromptChange(event.target.value)}
              className="min-h-20 resize-none rounded-xl text-xs bg-muted/20 focus-visible:bg-background leading-relaxed"
              placeholder="画面视觉与画面构图提示词..."
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor={`dialogue_${scene.id}`} className="text-xs font-medium text-foreground">
            {t("scene.dialogue")}
          </Label>
          <Textarea
            id={`dialogue_${scene.id}`}
            value={scene.dialogue}
            onChange={(event) => onFieldChange({ dialogue: event.target.value })}
            className="min-h-16 resize-none rounded-xl text-xs bg-muted/20 focus-visible:bg-background leading-relaxed"
            placeholder={t("scene.dialoguePlaceholder")}
          />
        </div>

        {/* 出场角色；台词角色在生成时从台词文本自动识别。 */}
        {characters.length > 0 ? (
          <div className="rounded-xl border border-border/50 bg-muted/20 p-3">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-foreground">{t("scene.cast")}</Label>
              <div className="flex flex-wrap gap-1.5">
                {characters.map((character) => {
                  const cast = scene.characterIds.includes(character.id);
                  return (
                    <Button
                      key={character.id}
                      type="button"
                      size="xs"
                      variant={cast ? "default" : "outline"}
                      onClick={() =>
                        onCastChange(
                          cast
                            ? scene.characterIds.filter((id) => id !== character.id)
                            : [...scene.characterIds, character.id]
                        )
                      }
                      className="h-6 rounded-lg text-[11px] cursor-pointer"
                    >
                      {character.name}
                    </Button>
                  );
                })}
              </div>
            </div>

          </div>
        ) : null}

        {/* 镜头参数 */}
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor={`shot_${scene.id}`} className="text-xs font-medium text-foreground">{t("scene.shotType")}</Label>
            <Input
              id={`shot_${scene.id}`}
              value={scene.shotType}
              onChange={(event) => onFieldChange({ shotType: event.target.value })}
              placeholder={t("scene.shotTypePlaceholder")}
              className="h-8 rounded-lg text-xs bg-muted/20"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`camera_${scene.id}`} className="text-xs font-medium text-foreground">{t("scene.cameraMove")}</Label>
            <Input
              id={`camera_${scene.id}`}
              value={scene.cameraMove}
              onChange={(event) => onFieldChange({ cameraMove: event.target.value })}
              placeholder={t("scene.cameraMovePlaceholder")}
              className="h-8 rounded-lg text-xs bg-muted/20"
            />
          </div>
          <div className="space-y-1.5 col-span-2 sm:col-span-1">
            <Label htmlFor={`duration_${scene.id}`} className="text-xs font-medium text-foreground">{t("scene.durationMs")}</Label>
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
              className="h-8 rounded-lg text-xs bg-muted/20"
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor={`subtitle_${scene.id}`} className="text-xs font-medium text-foreground">{t("scene.subtitleText")}</Label>
          <Textarea
            id={`subtitle_${scene.id}`}
            value={scene.subtitleText}
            onChange={(event) => onFieldChange({ subtitleText: event.target.value })}
            className="min-h-14 resize-none rounded-xl text-xs bg-muted/20 focus-visible:bg-background leading-relaxed"
            placeholder={t("scene.subtitlePlaceholder")}
          />
        </div>
      </CardContent>
    </Card>
  );
}
