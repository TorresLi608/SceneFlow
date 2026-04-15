"use client";

import { CSS } from "@dnd-kit/utilities";
import { useSortable } from "@dnd-kit/sortable";
import { GripVertical, Image as ImageIcon, Mic } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { Scene } from "@/types/project";

interface SceneCardProps {
  scene: Scene;
  onNarrationChange: (value: string) => void;
  onPromptChange: (value: string) => void;
}

const statusLabel: Record<Scene["image"]["status"], string> = {
  idle: "待生成",
  generating: "生成中",
  success: "成功",
  error: "失败",
};

export function SceneCard({ scene, onNarrationChange, onPromptChange }: SceneCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: scene.id,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
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
          <CardTitle className="text-base font-semibold">Scene {scene.order}</CardTitle>
          <button
            type="button"
            aria-label="拖拽排序"
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
            图像: {statusLabel[scene.image.status]}
          </Badge>
          <Badge variant="secondary" className="gap-1">
            <Mic className="size-3.5" />
            音频: {statusLabel[scene.audio.status]}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>图像进度</span>
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
            <div className="rounded-md border border-border/70 bg-muted/30 px-2 py-1 text-xs text-muted-foreground">
              图片已生成 {scene.image.url ? "(URL ready)" : ""}
            </div>
          ) : null}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>音频进度</span>
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
              音频已生成 · 时长 {scene.audio.duration.toFixed(1)}s
            </div>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor={`narration_${scene.id}`}>旁白</Label>
          <Textarea
            id={`narration_${scene.id}`}
            value={scene.narration}
            onChange={(event) => onNarrationChange(event.target.value)}
            className="min-h-20"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor={`prompt_${scene.id}`}>画面 Prompt</Label>
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
