"use client";

import { CSS } from "@dnd-kit/utilities";
import { useSortable } from "@dnd-kit/sortable";
import { GripVertical, Image as ImageIcon, Mic } from "lucide-react";
import Image from "next/image";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n";
import { backendBaseURL } from "@/lib/http/backend-client";
import { cn } from "@/lib/utils";
import type { Scene } from "@/types/project";

interface SceneCardProps {
  scene: Scene;
  onNarrationChange: (value: string) => void;
  onPromptChange: (value: string) => void;
}

export function SceneCard({ scene, onNarrationChange, onPromptChange }: SceneCardProps) {
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
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold">{t("scene.sceneLabel", { order: scene.order })}</CardTitle>
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
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{t("scene.imageProgress")}</span>
            <span>{scene.image.progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-primary transition-all duration-500"
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
      </CardContent>
    </Card>
  );
}
