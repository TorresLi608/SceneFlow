"use client";

import {
  PromptArea,
  chip,
  getChips,
  mentionTrigger,
  segmentsToPlainText,
  type ChipSegment,
  type Segment,
} from "prompt-area";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { GenerationReferenceInput, GenerationReferenceKind } from "@/types/project";

import type { ReferenceAssetOption } from "./reference-picker";

const keyOf = (item: GenerationReferenceInput) => `${item.kind}:${item.id}`;

function markerAliases(label: string, index: number, media: ReferenceAssetOption["media"]) {
  const aliases = media === "video"
    ? [`视频${index}`, `<视频${index}>`, `Video ${index}`, `<Video ${index}>`]
    : media === "audio"
      ? [`音频${index}`, `<音频${index}>`, `Audio ${index}`, `<Audio ${index}>`]
      : [`图${index}`, `图片${index}`, `<图${index}>`, `<图片${index}>`, `Image ${index}`, `<Image ${index}>`];
  return [`@${label}`, ...aliases].sort((a, b) => b.length - a.length);
}

function refsFromSegments(segments: Segment[]): GenerationReferenceInput[] {
  const seen = new Set<string>();
  return getChips(segments).flatMap((item) => {
    const data = item.data as { kind?: string; id?: string } | undefined;
    const [kind, id] = String(item.value).split(":");
    const reference = { kind: (data?.kind ?? kind) as GenerationReferenceKind, id: data?.id ?? id };
    if (!reference.kind || !reference.id || seen.has(keyOf(reference))) return [];
    seen.add(keyOf(reference));
    return [reference];
  });
}

function initialSegments(value: string, references: GenerationReferenceInput[], assets: ReferenceAssetOption[]): Segment[] {
  const mediaIndexes = new Map<ReferenceAssetOption["media"], number>();
  const matches = references
    .map((reference) => {
      const asset = assets.find((item) => keyOf(item) === keyOf(reference));
      if (!asset) return null;
      const index = (mediaIndexes.get(asset.media) ?? 0) + 1;
      mediaIndexes.set(asset.media, index);
      const marker = markerAliases(asset.label, index, asset.media)
        .map((alias) => ({ alias, index: value.indexOf(alias) }))
        .filter((item) => item.index >= 0)
        .sort((a, b) => a.index - b.index || b.alias.length - a.alias.length)[0];
      return marker ? { reference, asset, index: marker.index, length: marker.alias.length } : null;
    })
    .filter((item): item is NonNullable<typeof item> => item !== null && item.index >= 0)
    .sort((a, b) => a.index - b.index);

  const segments: Segment[] = [];
  let cursor = 0;
  for (const match of matches) {
    if (match.index < cursor) continue;
    if (match.index > cursor) segments.push({ type: "text", text: value.slice(cursor, match.index) });
    segments.push(chip({
      trigger: "@",
      value: keyOf(match.reference),
      displayText: match.asset.label,
      data: { kind: match.reference.kind, id: match.reference.id },
    }));
    cursor = match.index + match.length;
  }
  if (cursor < value.length) segments.push({ type: "text", text: value.slice(cursor) });
  for (const reference of references) {
    const asset = assets.find((item) => keyOf(item) === keyOf(reference));
    if (!asset || value.includes(`@${asset.label}`)) continue;
    segments.push({ type: "text", text: segments.length ? " " : "" });
    segments.push(chip({
      trigger: "@",
      value: keyOf(reference),
      displayText: asset.label,
      data: { kind: reference.kind, id: reference.id },
    }));
  }
  return segments.length ? segments : [{ type: "text", text: value }];
}

export function MentionTextarea({
  value,
  onChange,
  references,
  onReferencesChange,
  assets,
  limits,
  className,
  id,
  rows,
  ...props
}: Omit<React.ComponentProps<typeof PromptArea>, "value" | "onChange" | "triggers"> & {
  id?: string;
  rows?: number;
  value: string;
  onChange?: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  references: GenerationReferenceInput[];
  onReferencesChange: (next: GenerationReferenceInput[], prompt: string) => void;
  assets: ReferenceAssetOption[];
  limits: Partial<Record<ReferenceAssetOption["media"], number>>;
}) {
  const [segments, setSegments] = useState<Segment[]>(() => initialSegments(value, references, assets));
  const effectiveSegments = segmentsToPlainText(segments) === value ? segments : initialSegments(value, references, assets);
  const chips = getChips(effectiveSegments);

  const emit = (next: Segment[]) => {
    const nextPrompt = segmentsToPlainText(next);
    const nextRefs = refsFromSegments(next);
    setSegments(next);
    onReferencesChange(nextRefs, nextPrompt);
    // Call onChange only if provided — prefix editors pass references+prompt atomically
    // via onReferencesChange and skip onChange to avoid a second state update.
    onChange?.({ target: { value: nextPrompt } } as React.ChangeEvent<HTMLTextAreaElement>);
  };

  const selected = useMemo(() => new Set(refsFromSegments(effectiveSegments).map(keyOf)), [effectiveSegments]);
  const search = async (query: string) => {
    const normalized = query.trim().toLowerCase();
    const counts = new Map<ReferenceAssetOption["media"], number>();
    for (const asset of assets) {
      if (selected.has(keyOf(asset))) counts.set(asset.media, (counts.get(asset.media) ?? 0) + 1);
    }
    return assets
      .filter((asset) => asset.label.toLowerCase().includes(normalized))
      .filter((asset) => selected.has(keyOf(asset)) || (counts.get(asset.media) ?? 0) < (limits[asset.media] ?? 0))
      .map((asset) => ({ value: keyOf(asset), label: asset.label, description: asset.media, data: asset }));
  };

  const removeChip = (target: ChipSegment) => {
    let removed = false;
    const next = effectiveSegments.filter((seg) => {
      if (removed) return true;
      if (seg === target) {
        removed = true;
        return false;
      }
      if (
        seg.type === "chip" &&
        seg.value === target.value &&
        (!target.displayText || seg.displayText === target.displayText) &&
        (!target.trigger || seg.trigger === target.trigger)
      ) {
        removed = true;
        return false;
      }
      return true;
    });
    emit(next);
  };

  return (
    <div className="flex flex-col gap-1.5">
      <PromptArea
        {...props}
        data-test-id={id}
        className={cn("min-h-16 rounded-md border border-input bg-background px-3 py-2 text-sm", className)}
        minHeight={rows ? rows * 24 : undefined}
        value={effectiveSegments}
        onChange={emit}
        onChipClick={removeChip}
        triggers={[mentionTrigger({ onSearch: search, onSelect: (suggestion) => suggestion.label, chipStyle: "pill", accessibilityLabel: "素材", emptyMessage: "没有可用素材" })]}
        submitOnEnter={false}
      />
      {chips.length ? (
        <div className="flex flex-wrap gap-1">
          {chips.map((item, index) => (
            <Button
              key={`${item.value}:${item.displayText}:${index}`}
              type="button"
              size="xs"
              variant="ghost"
              className="h-6 rounded-full bg-primary/10 px-2 text-[11px] text-primary hover:bg-destructive/10 hover:text-destructive cursor-pointer transition-colors"
              onClick={() => removeChip(item)}
            >
              @{item.displayText} ×
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
