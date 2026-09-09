"use client";

import { Check, Film, ImageIcon, Search, Volume2, X } from "lucide-react";
import Image from "next/image";
import {
  PromptArea,
  chip,
  getChips,
  mentionTrigger,
  segmentsToPlainText,
  type ChipSegment,
  type Segment,
  type TriggerSuggestion,
} from "prompt-area";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { matchesResource } from "@/lib/project-resources";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { GenerationReferenceInput, GenerationReferenceKind } from "@/types/project";

import type { ReferenceAssetOption } from "./reference-picker";

type ReferenceMedia = ReferenceAssetOption["media"];

const keyOf = (item: GenerationReferenceInput) => `${item.kind}:${item.id}`;

/** Display order for media types in the picker's type filter. */
const MEDIA_ORDER: ReferenceMedia[] = ["image", "video", "audio"];
const MEDIA_ICONS = { image: ImageIcon, video: Film, audio: Volume2 } as const;
/** One tone per media type so the badge is readable at a glance beside the asset name. */
const MEDIA_TONE: Record<ReferenceMedia, string> = {
  image: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  video: "border-violet-500/40 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  audio: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
};
const SPACE: Segment = { type: "text", text: " " };

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
      const marker = [...markerAliases(asset.label, index, asset.media), ...(asset.aliases ?? []).map((alias) => `@${alias}`)]
        .map((alias) => ({ alias, index: value.indexOf(alias) }))
        .filter((item) => item.index >= 0)
        .sort((a, b) => a.index - b.index || b.alias.length - a.alias.length)[0];
      return marker ? { reference, asset, index: marker.index, length: marker.alias.length } : null;
    })
    .filter((item): item is NonNullable<typeof item> => item !== null && item.index >= 0)
    .sort((a, b) => a.index - b.index);

  const segments: Segment[] = [];
  const matched = new Set<string>();
  let cursor = 0;
  for (const match of matches) {
    if (match.index < cursor) continue;
    matched.add(keyOf(match.reference));
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
    if (!asset || matched.has(keyOf(reference))) continue;
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

/** Image thumbnail, or the media icon for video and audio; shared by the dropdown, the picker and the chip list. */
function ReferenceThumb({ asset, className }: { asset: ReferenceAssetOption; className?: string }) {
  const Icon = MEDIA_ICONS[asset.media];
  return (
    <span className={cn("relative flex size-7 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border/40 bg-muted", className)}>
      {asset.media === "image" && asset.url ? (
        <Image src={asset.url} alt="" fill unoptimized sizes="28px" className="object-cover" />
      ) : (
        <Icon aria-hidden className="size-3.5 text-muted-foreground" />
      )}
    </span>
  );
}

function MediaBadge({ media, label }: { media: ReferenceMedia; label: string }) {
  const Icon = MEDIA_ICONS[media];
  return (
    <Badge variant="outline" className={cn("h-4 gap-1 px-1.5 text-[10px] font-medium", MEDIA_TONE[media])}>
      <Icon aria-hidden className="size-3" />
      {label}
    </Badge>
  );
}

const filterClass = (active: boolean) =>
  cn(
    "flex cursor-pointer items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors",
    active ? "border-primary/40 bg-primary/10 text-primary" : "border-border/60 text-muted-foreground hover:bg-muted/60 hover:text-foreground"
  );

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
  const { t } = useI18n();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [referenceSearch, setReferenceSearch] = useState("");
  const [mediaFilter, setMediaFilter] = useState<ReferenceMedia | "all">("all");
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
  const assetByKey = useMemo(() => new Map(assets.map((asset) => [keyOf(asset), asset])), [assets]);

  const mediaLabel = (media: ReferenceMedia) => t(`assets.media.${media}`);
  const kindLabel = (asset: ReferenceAssetOption) => t(`assets.kind.${asset.kind}`);
  const sourceLabel = (asset: ReferenceAssetOption) => asset.episodeTitle || t("assets.shared");
  const describe = (asset: ReferenceAssetOption) => `${mediaLabel(asset.media)} · ${kindLabel(asset)} · ${sourceLabel(asset)}`;
  // The type words shown beside each asset are searchable too, so "@视频" or "@image" narrows by type.
  const matches = (asset: ReferenceAssetOption, query: string) =>
    matchesResource(asset, query, [mediaLabel(asset.media), t(`episode.referenceType.${asset.media}`), kindLabel(asset)]);
  const usedCount = (media: ReferenceMedia) => assets.filter((asset) => asset.media === media && selected.has(keyOf(asset))).length;
  const hasBudget = (media: ReferenceMedia) => usedCount(media) < (limits[media] ?? 0);
  const budgetLabel = (media: ReferenceMedia) =>
    t("episode.referenceLimit", { type: t(`episode.referenceType.${media}`), count: usedCount(media), limit: limits[media] ?? 0 });

  const allowedMedia = MEDIA_ORDER.filter((media) => (limits[media] ?? 0) > 0);
  // A stale filter (for example after the video model stops accepting audio) falls back to "all".
  const activeFilter = mediaFilter !== "all" && allowedMedia.includes(mediaFilter) ? mediaFilter : "all";
  const pickerAssets = assets.filter((asset) => (limits[asset.media] ?? 0) > 0);
  const visibleAssets = pickerAssets.filter(
    (asset) => (activeFilter === "all" || asset.media === activeFilter) && matches(asset, referenceSearch)
  );

  const search = async (query: string): Promise<TriggerSuggestion[]> =>
    assets
      .filter((asset) => matches(asset, query))
      .filter((asset) => selected.has(keyOf(asset)) || hasBudget(asset.media))
      .map((asset) => ({
        value: keyOf(asset),
        label: asset.label,
        description: describe(asset),
        icon: <ReferenceThumb asset={asset} className="size-5 rounded" />,
        data: asset,
      }));

  const appendReference = (asset: ReferenceAssetOption) => {
    const last = effectiveSegments[effectiveSegments.length - 1];
    const needsSpace = last !== undefined && !(last.type === "text" && (last.text === "" || /\s$/.test(last.text)));
    emit([
      ...effectiveSegments,
      ...(needsSpace ? [SPACE] : []),
      chip({ trigger: "@", value: keyOf(asset), displayText: asset.label, data: { kind: asset.kind, id: asset.id } }),
    ]);
  };

  const removeReference = (asset: ReferenceAssetOption) =>
    emit(effectiveSegments.filter((segment) => !(segment.type === "chip" && segment.value === keyOf(asset))));

  const closePicker = () => {
    setPickerOpen(false);
    setReferenceSearch("");
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
      <Button
        type="button"
        size="xs"
        variant="ghost"
        className="self-start cursor-pointer"
        aria-expanded={pickerOpen}
        onClick={() => (pickerOpen ? closePicker() : setPickerOpen(true))}
        disabled={props.disabled}
      >
        @ {t("assets.chooseReference")}
      </Button>
      {pickerOpen ? (
        <div role="group" aria-label={t("assets.chooseReference")} className="flex flex-col gap-2 rounded-lg border border-border/70 bg-background p-2 shadow-xs">
          <div className="flex items-center gap-1.5">
            <div className="relative min-w-0 flex-1">
              <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="search"
                autoFocus
                aria-label={t("assets.searchReferences")}
                placeholder={t("assets.searchReferences")}
                value={referenceSearch}
                onChange={(event) => setReferenceSearch(event.target.value)}
                className="h-8 pl-7 text-xs"
              />
            </div>
            <Button type="button" size="icon-xs" variant="ghost" aria-label={t("common.close")} title={t("common.close")} onClick={closePicker} className="cursor-pointer">
              <X className="size-3.5" />
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {allowedMedia.length > 1 ? (
              <button type="button" aria-pressed={activeFilter === "all"} onClick={() => setMediaFilter("all")} className={filterClass(activeFilter === "all")}>
                {t("common.all")}
                <span className="font-mono text-[10px] opacity-70">{pickerAssets.length}</span>
              </button>
            ) : null}
            {allowedMedia.map((media) => {
              const Icon = MEDIA_ICONS[media];
              return (
                <button
                  key={media}
                  type="button"
                  aria-pressed={activeFilter === media}
                  title={budgetLabel(media)}
                  onClick={() => setMediaFilter(media)}
                  className={filterClass(activeFilter === media)}
                >
                  <Icon aria-hidden className="size-3" />
                  {t(`episode.referenceType.${media}`)}
                  <span className="font-mono text-[10px] opacity-70">{usedCount(media)}/{limits[media] ?? 0}</span>
                </button>
              );
            })}
          </div>
          <div className="flex max-h-56 flex-col gap-0.5 overflow-y-auto chat-message-list-scrollbar">
            {visibleAssets.map((asset) => {
              const active = selected.has(keyOf(asset));
              const disabled = !active && !hasBudget(asset.media);
              return (
                <button
                  key={keyOf(asset)}
                  type="button"
                  aria-pressed={active}
                  disabled={disabled}
                  title={disabled ? budgetLabel(asset.media) : describe(asset)}
                  onClick={() => (active ? removeReference(asset) : appendReference(asset))}
                  className={cn(
                    "flex w-full cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs transition-colors",
                    active ? "bg-primary/10 text-primary" : "hover:bg-muted/70",
                    disabled && "cursor-not-allowed opacity-40"
                  )}
                >
                  <ReferenceThumb asset={asset} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{asset.label}</span>
                    <span className="mt-0.5 flex min-w-0 items-center gap-1 text-[10px] text-muted-foreground">
                      <MediaBadge media={asset.media} label={mediaLabel(asset.media)} />
                      <span className="truncate">{kindLabel(asset)} · {sourceLabel(asset)}</span>
                    </span>
                  </span>
                  {active ? <Check aria-hidden className="size-3.5 shrink-0" /> : null}
                </button>
              );
            })}
            {visibleAssets.length === 0 ? <p className="p-2 text-xs text-muted-foreground">{t("assets.noMatches")}</p> : null}
          </div>
        </div>
      ) : null}
      <PromptArea
        {...props}
        data-test-id={id}
        className={cn("min-h-16 rounded-md border border-input bg-background px-3 py-2 text-sm", className)}
        minHeight={rows ? rows * 24 : undefined}
        value={effectiveSegments}
        onChange={emit}
        onChipClick={removeChip}
        triggers={[mentionTrigger({ onSearch: search, onSelect: (suggestion) => suggestion.label, chipStyle: "pill", accessibilityLabel: t("episode.mentionAssetsAccessibility"), emptyMessage: t("episode.mentionAssetsEmpty") })]}
        submitOnEnter={false}
      />
      {chips.length ? (
        <div className="flex flex-wrap gap-1">
          {chips.map((item, index) => {
            const asset = assetByKey.get(String(item.value));
            const Icon = asset ? MEDIA_ICONS[asset.media] : null;
            return (
              <Button
                key={`${item.value}:${item.displayText}:${index}`}
                type="button"
                size="xs"
                variant="ghost"
                title={asset ? describe(asset) : undefined}
                className="h-6 rounded-full bg-primary/10 px-2 text-[11px] text-primary hover:bg-destructive/10 hover:text-destructive cursor-pointer transition-colors"
                onClick={() => removeChip(item)}
              >
                {Icon ? <Icon aria-hidden className="size-3" /> : null}
                @{item.displayText} ×
              </Button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
