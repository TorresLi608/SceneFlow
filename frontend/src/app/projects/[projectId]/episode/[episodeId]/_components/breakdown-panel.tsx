"use client";

import { Check, Clapperboard, Film, Layers, Mic, Package, Sparkles, Square, User } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { BreakdownDetailLevel, BreakdownTarget, Character, Prop, VoiceProfile } from "@/types/project";

export interface BreakdownSelection {
  characterIds: string[];
  propIds: string[];
  voiceProfileIds: string[];
  useCastSheet: boolean;
  usePropSheet: boolean;
  useVoiceSheet: boolean;
}

export const EMPTY_SELECTION: BreakdownSelection = {
  characterIds: [],
  propIds: [],
  voiceProfileIds: [],
  useCastSheet: false,
  usePropSheet: false,
  useVoiceSheet: false,
};

function Chip({
  label,
  hint,
  icon: Icon,
  active,
  onClick,
}: {
  label: string;
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-all cursor-pointer",
        active
          ? "border-primary/80 bg-primary/10 text-primary font-medium shadow-2xs"
          : "border-border/70 bg-background/60 text-muted-foreground hover:border-primary/50 hover:text-foreground"
      )}
    >
      {active ? (
        <Check className="size-3.5 text-primary" />
      ) : Icon ? (
        <Icon className="size-3.5 opacity-60" />
      ) : null}
      <span className="truncate">{label}</span>
      {hint ? <span className="text-[10px] opacity-70 font-mono">{hint}</span> : null}
    </button>
  );
}

/**
 * What the breakdown may look at, and what it should produce.
 */
export function BreakdownPanel({
  characters,
  props,
  voices,
  selection,
  onSelectionChange,
  target,
  onTargetChange,
  detailLevel,
  onDetailLevelChange,
  detailPrompt,
  onDetailPromptChange,
  running,
  disabled,
  disabledReason,
  targetDisabled = false,
  onStart,
  onStop,
}: {
  characters: Character[];
  props: Prop[];
  voices: VoiceProfile[];
  selection: BreakdownSelection;
  onSelectionChange: (next: BreakdownSelection) => void;
  target: BreakdownTarget;
  onTargetChange: (next: BreakdownTarget) => void;
  detailLevel: BreakdownDetailLevel;
  onDetailLevelChange: (next: BreakdownDetailLevel) => void;
  detailPrompt: string;
  onDetailPromptChange: (next: string) => void;
  running: boolean;
  disabled: boolean;
  disabledReason?: string;
  targetDisabled?: boolean;
  onStart: () => void;
  onStop: () => void;
}) {
  const { t } = useI18n();

  const toggle = (key: "characterIds" | "propIds" | "voiceProfileIds", id: string) => {
    const current = selection[key];
    onSelectionChange({
      ...selection,
      [key]: current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    });
  };

  const targets: { value: BreakdownTarget; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { value: "shots", label: t("episode.targetShots"), icon: Layers },
    { value: "video", label: t("episode.targetVideo"), icon: Film },
    { value: "both", label: t("episode.targetBoth"), icon: Clapperboard },
  ];
  const detailLevels: { value: BreakdownDetailLevel; label: string }[] = [
    { value: "concise", label: t("episode.detailConcise") },
    { value: "standard", label: t("episode.detailStandard") },
    { value: "detailed", label: t("episode.detailDetailed") },
    { value: "custom", label: t("episode.detailCustom") },
  ];

  const nothingToPick = characters.length === 0 && props.length === 0 && voices.length === 0;
  const cannotStart = disabled || (detailLevel === "custom" && !detailPrompt.trim());

  return (
    <section className="flex flex-col gap-4 rounded-xl border border-border/70 bg-card/50 p-4.5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Sparkles className="size-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold">{t("episode.breakdownSection")}</h2>
            <p className="text-xs text-muted-foreground">{t("episode.referencesHint")}</p>
          </div>
        </div>
      </div>

      <Field>
        <FieldLabel className="text-xs text-muted-foreground">{t("episode.breakdownTarget")}</FieldLabel>
        <div className="flex flex-wrap gap-2">
          {targets.map((item) => {
            const Icon = item.icon;
            const active = target === item.value;
            return (
              <button
                key={item.value}
                type="button"
                aria-pressed={active}
                disabled={targetDisabled}
                onClick={() => onTargetChange(item.value)}
                className={cn(
                  "flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-all cursor-pointer",
                  active
                    ? "border-primary bg-primary/10 text-primary shadow-xs ring-1 ring-primary/30"
                    : "border-border/70 bg-background/60 text-muted-foreground hover:border-primary/40 hover:text-foreground",
                  targetDisabled && "cursor-not-allowed opacity-50 hover:border-border/70 hover:text-muted-foreground"
                )}
              >
                <Icon className={cn("size-3.5", active ? "text-primary" : "text-muted-foreground")} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
        <FieldDescription className="text-xs text-muted-foreground/80">{t("episode.targetHint")}</FieldDescription>
      </Field>

      <Field>
        <FieldLabel className="text-xs text-muted-foreground">{t("episode.breakdownDetail")}</FieldLabel>
        <div className="flex flex-wrap gap-2">
          {detailLevels.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={detailLevel === item.value}
              disabled={disabled || running}
              onClick={() => onDetailLevelChange(item.value)}
              className={cn(
                "rounded-lg border px-3 py-1.5 text-xs font-medium transition-all cursor-pointer",
                detailLevel === item.value
                  ? "border-primary bg-primary/10 text-primary shadow-xs ring-1 ring-primary/30"
                  : "border-border/70 bg-background/60 text-muted-foreground hover:border-primary/40 hover:text-foreground",
                (disabled || running) && "cursor-not-allowed opacity-50"
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <FieldDescription className="text-xs text-muted-foreground/80">{t("episode.breakdownDetailHint")}</FieldDescription>
        {detailLevel === "custom" ? (
          <Textarea
            value={detailPrompt}
            onChange={(event) => onDetailPromptChange(event.target.value)}
            placeholder={t("episode.detailCustomPlaceholder")}
            maxLength={6000}
            rows={4}
            disabled={disabled || running}
            className="mt-2 min-h-24 resize-y bg-background/70 text-sm leading-relaxed"
          />
        ) : null}
      </Field>

      {nothingToPick ? (
        <p className="rounded-lg border border-dashed border-border/70 p-4 text-center text-xs text-muted-foreground">
          {t("episode.noReferences")}
        </p>
      ) : (
        <div className="flex flex-col gap-3 rounded-lg border border-border/50 bg-muted/20 p-3.5">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {t("episode.references")}
          </p>

          {characters.length > 0 ? (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium flex items-center gap-1.5 text-foreground">
                  <User className="size-3.5 text-muted-foreground" />
                  {t("episode.refCharacters")}
                </span>
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0 font-mono">
                  {selection.characterIds.length}/{characters.length}
                </Badge>
                <Field orientation="horizontal" className="ml-auto flex items-center gap-2">
                  <Switch
                    id="useCastSheet"
                    checked={selection.useCastSheet}
                    onCheckedChange={(checked) => onSelectionChange({ ...selection, useCastSheet: checked })}
                  />
                  <FieldLabel htmlFor="useCastSheet" className="text-xs text-muted-foreground cursor-pointer">
                    {t("episode.useCastSheet")}
                  </FieldLabel>
                </Field>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {characters.map((character) => (
                  <Chip
                    key={character.id}
                    label={character.name}
                    icon={User}
                    hint={character.states.some((state) => state.referenceImageUrl) ? "◉" : undefined}
                    active={selection.characterIds.includes(character.id)}
                    onClick={() => toggle("characterIds", character.id)}
                  />
                ))}
              </div>
            </div>
          ) : null}

          {props.length > 0 ? (
            <div className="flex flex-col gap-2 border-t border-border/40 pt-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium flex items-center gap-1.5 text-foreground">
                  <Package className="size-3.5 text-muted-foreground" />
                  {t("episode.refProps")}
                </span>
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0 font-mono">
                  {selection.propIds.length}/{props.length}
                </Badge>
                <Field orientation="horizontal" className="ml-auto flex items-center gap-2">
                  <Switch
                    id="usePropSheet"
                    checked={selection.usePropSheet}
                    onCheckedChange={(checked) => onSelectionChange({ ...selection, usePropSheet: checked })}
                  />
                  <FieldLabel htmlFor="usePropSheet" className="text-xs text-muted-foreground cursor-pointer">
                    {t("episode.usePropSheet")}
                  </FieldLabel>
                </Field>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {props.map((prop) => (
                  <Chip
                    key={prop.id}
                    label={prop.name}
                    icon={Package}
                    hint={prop.imageUrl ? "◉" : undefined}
                    active={selection.propIds.includes(prop.id)}
                    onClick={() => toggle("propIds", prop.id)}
                  />
                ))}
              </div>
            </div>
          ) : null}

          {voices.length > 0 ? (
            <div className="flex flex-col gap-2 border-t border-border/40 pt-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium flex items-center gap-1.5 text-foreground">
                  <Mic className="size-3.5 text-muted-foreground" />
                  {t("episode.refVoices")}
                </span>
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0 font-mono">
                  {selection.voiceProfileIds.length}/{voices.length}
                </Badge>
                <Field orientation="horizontal" className="ml-auto flex items-center gap-2">
                  <Switch
                    id="useVoiceSheet"
                    checked={selection.useVoiceSheet}
                    onCheckedChange={(checked) => onSelectionChange({ ...selection, useVoiceSheet: checked })}
                  />
                  <FieldLabel htmlFor="useVoiceSheet" className="text-xs text-muted-foreground cursor-pointer">
                    {t("episode.useVoiceSheet")}
                  </FieldLabel>
                </Field>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {voices.map((voice) => (
                  <Chip
                    key={voice.id}
                    label={voice.name}
                    icon={Mic}
                    active={selection.voiceProfileIds.includes(voice.id)}
                    onClick={() => toggle("voiceProfileIds", voice.id)}
                  />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}

      <div>
        <Button
          type="button"
          variant={running ? "destructive" : "default"}
          disabled={running ? false : cannotStart}
          title={disabled ? disabledReason : detailLevel === "custom" && !detailPrompt.trim() ? t("episode.detailCustomRequired") : undefined}
          onClick={running ? onStop : onStart}
          className={cn(
            "cursor-pointer transition-all",
            running && "animate-pulse font-medium shadow-md shadow-destructive/20"
          )}
        >
          {running ? (
            <Square data-icon="inline-start" className="size-3 fill-current" />
          ) : (
            <Sparkles data-icon="inline-start" />
          )}
          {running ? t("common.stopGeneration") : t("episode.splitShots")}
        </Button>
      </div>
    </section>
  );
}
