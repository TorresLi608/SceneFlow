"use client";

import { CSS } from "@dnd-kit/utilities";
import { useSortable } from "@dnd-kit/sortable";
import { GripVertical, Image as ImageIcon, Mic } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
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
