"use client";

import { GripVertical, Plus, Sparkles, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n";
import type { GenerationReferenceInput, PromptPrefix } from "@/types/project";

import { MentionTextarea } from "./mention-textarea";
import type { ReferenceAssetOption } from "./reference-picker";

const keyOf = (item: GenerationReferenceInput) => `${item.kind}:${item.id}`;

/** Distinct per row and stable across renders, so editing one prefix never remounts another. */
const newPrefixId = () => `prefix-${Math.random().toString(36).slice(2, 10)}`;

/**
 * The ordered preambles above one prompt field.
 *
 * Each row is a full mention editor rather than a plain textarea because a prefix's
 * `@素材` spend real reference slots — so the limits handed down here are already net of
 * what every sibling editor in the group has taken, and a row can only offer what is
 * genuinely still free.
 */
export function PromptPrefixList({
  prefixes,
  onChange,
  assets,
  limitsFor,
  preset,
  presetDisabled,
  presetDisabledReason,
  disabled,
}: {
  prefixes: PromptPrefix[];
  onChange: (next: PromptPrefix[]) => void;
  assets: ReferenceAssetOption[];
  /** Per-media budget still available to the prefix at `index`, siblings already deducted. */
  limitsFor: (index: number) => Partial<Record<ReferenceAssetOption["media"], number>>;
  /**
   * The tone-sheet quick fill. Returns the server's own wording rather than a copy — see
   * `/api/prompts/prefix-presets`.
   */
  preset?: () => Promise<PromptPrefix | null>;
  /** Shown but inert until an anchor exists; a vanished button reads as a missing feature. */
  presetDisabled?: boolean;
  presetDisabledReason?: string;
  disabled?: boolean;
}) {
  const { t } = useI18n();

  const replace = (index: number, patch: Partial<PromptPrefix>) =>
    onChange(prefixes.map((item, position) => (position === index ? { ...item, ...patch } : item)));

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= prefixes.length) return;
    const next = [...prefixes];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  const add = (item: PromptPrefix) =>
    // Appended with a fresh id even for the preset: re-adding it after a delete must not
    // collide with an id the tone sheet will later rewrite in place.
    onChange([...prefixes, { ...item, id: prefixes.some((row) => row.id === item.id) ? newPrefixId() : item.id }]);

  return (
    <div className="flex flex-col gap-2">
      {prefixes.map((prefix, index) => (
        <div
          key={prefix.id}
          className="flex flex-col gap-1.5 rounded-lg border border-border/60 bg-background/50 p-2.5"
        >
          <div className="flex items-center gap-1.5">
            <div className="flex flex-col">
              <button
                type="button"
                aria-label={t("episode.prefixMoveUp")}
                disabled={disabled || index === 0}
                onClick={() => move(index, -1)}
                className="flex h-3 w-4 items-center justify-center text-muted-foreground/60 hover:text-foreground disabled:opacity-30 cursor-pointer disabled:cursor-not-allowed"
              >
                <GripVertical className="size-3 rotate-90" />
              </button>
            </div>
            <span className="shrink-0 rounded bg-muted/60 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {index + 1}
            </span>
            <Input
              value={prefix.name}
              maxLength={80}
              disabled={disabled}
              placeholder={t("episode.prefixNamePlaceholder")}
              onChange={(event) => replace(index, { name: event.target.value })}
              className="h-7 flex-1 bg-background/80 text-xs"
            />
            {prefix.source === "tone" ? (
              <span className="shrink-0 rounded-full border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">
                {t("episode.prefixAuto")}
              </span>
            ) : null}
            <button
              type="button"
              aria-label={t("episode.prefixDelete")}
              title={t("episode.prefixDelete")}
              disabled={disabled}
              onClick={() => onChange(prefixes.filter((_, position) => position !== index))}
              className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors cursor-pointer"
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
          <MentionTextarea
            id={`prefix-${prefix.id}`}
            value={prefix.prompt}
            maxLength={4000}
            rows={2}
            disabled={disabled}
            placeholder={t("episode.prefixPromptPlaceholder")}
            references={prefix.references}
            onReferencesChange={(references, prompt) =>
              replace(index, { references, prompt })
            }
            assets={assets}
            limits={limitsFor(index)}
            className="field-sizing-fixed min-h-14 resize-y bg-background/80 text-xs"
          />
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-1.5">
        <Button
          type="button"
          size="xs"
          variant="outline"
          disabled={disabled}
          onClick={() =>
            add({ id: newPrefixId(), name: "", prompt: "", references: [], source: "" })
          }
          className="h-6 text-[11px] cursor-pointer"
        >
          <Plus data-icon="inline-start" className="size-3" />
          {t("episode.prefixAdd")}
        </Button>
        {preset ? (
          <Button
            type="button"
            size="xs"
            variant="outline"
            disabled={disabled || presetDisabled}
            title={presetDisabled ? presetDisabledReason : t("episode.prefixPresetToneHint")}
            onClick={() => void preset().then((item) => item && add(item))}
            className="h-6 text-[11px] cursor-pointer disabled:cursor-not-allowed"
          >
            <Sparkles data-icon="inline-start" className="size-3" />
            {t("episode.prefixPresetTone")}
          </Button>
        ) : null}
        {prefixes.length ? (
          <span className="text-[10px] text-muted-foreground/80">
            {t("episode.prefixReferenceNote", {
              count: new Set(prefixes.flatMap((item) => item.references.map(keyOf))).size,
            })}
          </span>
        ) : null}
      </div>
    </div>
  );
}
