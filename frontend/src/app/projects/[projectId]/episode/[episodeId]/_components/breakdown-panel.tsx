"use client";

import { Check, Sparkles, Square } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { BreakdownTarget, Character, Prop, VoiceProfile } from "@/types/project";

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
  active,
  onClick,
}: {
  label: string;
  hint?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors cursor-pointer",
        active
          ? "border-primary bg-primary/10 text-primary"
          : "border-border/70 text-muted-foreground hover:border-primary/40 hover:text-foreground"
      )}
    >
      {active ? <Check className="size-3" /> : null}
      <span className="truncate">{label}</span>
      {hint ? <span className="text-[10px] opacity-70">{hint}</span> : null}
    </button>
  );
}

/**
 * What the breakdown may look at, and what it should produce.
 *
 * Selecting nothing is a first-class choice rather than an unfinished form: it tells the
 * model to work out the whole cast from the script. What ticking a character buys is a
 * prompt that says "参照《林小满》三面图" instead of re-describing a face the renderer
 * already holds a reference for — so the entries show whether they have an image, since
 * that is the difference between the two behaviours.
 */
export function BreakdownPanel({
  characters,
  props,
  voices,
  selection,
  onSelectionChange,
  target,
  onTargetChange,
  running,
  disabled,
  disabledReason,
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
  running: boolean;
  disabled: boolean;
  disabledReason?: string;
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

  const targets: { value: BreakdownTarget; label: string }[] = [
    { value: "shots", label: t("episode.targetShots") },
    { value: "video", label: t("episode.targetVideo") },
    { value: "both", label: t("episode.targetBoth") },
  ];

  const nothingToPick = characters.length === 0 && props.length === 0 && voices.length === 0;

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-border/70 bg-card/40 p-4">
      <div>
        <h2 className="text-sm font-semibold">{t("episode.breakdownSection")}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{t("episode.referencesHint")}</p>
      </div>

      <Field>
        <FieldLabel>{t("episode.breakdownTarget")}</FieldLabel>
        <div className="flex flex-wrap gap-2">
          {targets.map((item) => (
            <Chip
              key={item.value}
              label={item.label}
              active={target === item.value}
              onClick={() => onTargetChange(item.value)}
            />
          ))}
        </div>
        <FieldDescription>{t("episode.targetHint")}</FieldDescription>
      </Field>

      {nothingToPick ? (
        <p className="rounded-md border border-dashed border-border/70 p-4 text-center text-xs text-muted-foreground">
          {t("episode.noReferences")}
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t("episode.references")}
          </p>

          {characters.length > 0 ? (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium">{t("episode.refCharacters")}</span>
                <Badge variant="outline" className="text-[10px]">
                  {selection.characterIds.length}/{characters.length}
                </Badge>
                <Field orientation="horizontal" className="ml-auto">
                  <Switch
                    id="useCastSheet"
                    checked={selection.useCastSheet}
                    onCheckedChange={(checked) => onSelectionChange({ ...selection, useCastSheet: checked })}
                  />
                  <FieldLabel htmlFor="useCastSheet" className="text-xs">
                    {t("episode.useCastSheet")}
                  </FieldLabel>
                </Field>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {characters.map((character) => (
                  <Chip
                    key={character.id}
                    label={character.name}
                    hint={character.states.some((state) => state.referenceImageUrl) ? "◉" : undefined}
                    active={selection.characterIds.includes(character.id)}
                    onClick={() => toggle("characterIds", character.id)}
                  />
                ))}
              </div>
            </div>
          ) : null}

          {props.length > 0 ? (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium">{t("episode.refProps")}</span>
                <Badge variant="outline" className="text-[10px]">
                  {selection.propIds.length}/{props.length}
                </Badge>
                <Field orientation="horizontal" className="ml-auto">
                  <Switch
                    id="usePropSheet"
                    checked={selection.usePropSheet}
                    onCheckedChange={(checked) => onSelectionChange({ ...selection, usePropSheet: checked })}
                  />
                  <FieldLabel htmlFor="usePropSheet" className="text-xs">
                    {t("episode.usePropSheet")}
                  </FieldLabel>
                </Field>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {props.map((prop) => (
                  <Chip
                    key={prop.id}
                    label={prop.name}
                    hint={prop.imageUrl ? "◉" : undefined}
                    active={selection.propIds.includes(prop.id)}
                    onClick={() => toggle("propIds", prop.id)}
                  />
                ))}
              </div>
            </div>
          ) : null}

          {voices.length > 0 ? (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium">{t("episode.refVoices")}</span>
                <Badge variant="outline" className="text-[10px]">
                  {selection.voiceProfileIds.length}/{voices.length}
                </Badge>
                <Field orientation="horizontal" className="ml-auto">
                  <Switch
                    id="useVoiceSheet"
                    checked={selection.useVoiceSheet}
                    onCheckedChange={(checked) => onSelectionChange({ ...selection, useVoiceSheet: checked })}
                  />
                  <FieldLabel htmlFor="useVoiceSheet" className="text-xs">
                    {t("episode.useVoiceSheet")}
                  </FieldLabel>
                </Field>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {voices.map((voice) => (
                  <Chip
                    key={voice.id}
                    label={voice.name}
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
          // Stopping stays available while it runs; only starting can be blocked.
          disabled={running ? false : disabled}
          title={disabled ? disabledReason : undefined}
          onClick={running ? onStop : onStart}
          className={cn("cursor-pointer transition-colors", running && "animate-pulse font-medium")}
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
