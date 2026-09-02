"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { isCancel } from "axios";
import { Sparkles, Square, Wand2 } from "lucide-react";
import { useRef, useState } from "react";

import { listPromptPresetsAction } from "@/actions/projects-actions";
import { optimizePromptAction, type PromptKind } from "@/actions/prompt-actions";
import { queryKeys } from "@/actions/query-keys";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type OutputLanguage = "auto" | "zh" | "en";
export type PresetKind = "character" | "prop" | "cover";

/**
 * Options for a prompt-language `Select`, in the shape base-ui's `items` prop wants.
 *
 * Passing this to `Select.Root` is not optional: base-ui resolves the trigger's text from
 * `items`, not from the `label` prop on each `Select.Item` (which only feeds typeahead).
 * Without it `Select.Value` renders the raw value, so picking 中文 left "zh" on screen.
 */
export const promptLanguageItems = (t: (key: string) => string) => [
  { value: "auto", label: t("common.promptLanguageAuto") },
  { value: "zh", label: t("common.promptLanguageZh") },
  { value: "en", label: t("common.promptLanguageEn") },
];

interface PromptFieldProps {
  id: string;
  label: string;
  /** Which optimiser wording to use. Also decides what the model is told to preserve. */
  kind: PromptKind;
  value: string;
  onChange: (value: string) => void;
  /** Omit to hide the preset dropdown — voice prompts have no templates worth offering. */
  presetKind?: PresetKind;
  /**
   * The chosen preset's key. Lifted out of this component because the caller has to send it
   * with "draft it for me": the backend falls back to the *first* preset for an unknown key,
   * so a dropped key silently drafts a turnaround sheet no matter what the user picked.
   */
  preset?: string;
  onPresetChange?: (key: string) => void;
  placeholder?: string;
  /** Rendered to the right of the preset dropdown; where a "draft it for me" button goes. */
  actions?: React.ReactNode;
  /** True while some other request on the same form is running. */
  busy?: boolean;
  onError: (message: string) => void;
  className?: string;
  maxLength?: number;
}

/**
 * A prompt textarea with the three controls every prompt in this app turned out to need:
 * a preset to start from, a language to optimise into, and a stop button.
 *
 * Shared rather than copied because there are five of these — cover, character, prop,
 * voice, and the generation panels — and the stop behaviour in particular is easy to get
 * subtly wrong: the controller has to be created *before* the mutation fires, cleared in
 * `onSettled` so a later run gets a fresh one, and an abort must not surface as an error,
 * because the user asking to stop is not a failure.
 */
export function PromptField({
  id,
  label,
  kind,
  value,
  onChange,
  presetKind,
  preset,
  onPresetChange,
  placeholder,
  actions,
  busy = false,
  onError,
  className,
  maxLength = 4000,
}: PromptFieldProps) {
  const { t } = useI18n();
  const [language, setLanguage] = useState<OutputLanguage>("auto");
  const controller = useRef<AbortController | null>(null);

  const presetsQuery = useQuery({
    queryKey: queryKeys.promptPresets(presetKind ?? ""),
    queryFn: () => listPromptPresetsAction(presetKind as PresetKind),
    enabled: Boolean(presetKind),
    // Static templates compiled into the backend; they do not change between requests.
    staleTime: Infinity,
  });

  const optimizeMutation = useMutation({
    mutationFn: () =>
      optimizePromptAction(
        { kind, prompt: value.trim(), context: { outputLanguage: language } },
        controller.current?.signal
      ),
    onSuccess: (response) => onChange(response.prompt),
    onError: (error) => {
      if (isCancel(error)) return;
      onError(resolveRequestError(error, t("common.optimizePromptFailed")));
    },
    onSettled: () => {
      controller.current = null;
    },
  });

  const stop = () => {
    controller.current?.abort();
    controller.current = null;
    optimizeMutation.reset();
  };

  const start = () => {
    controller.current = new AbortController();
    optimizeMutation.mutate();
  };

  const presets = presetsQuery.data?.presets ?? [];
  const optimizing = optimizeMutation.isPending;
  // base-ui resolves the trigger's text from `items` on the root, not from the `label` prop
  // on each item — without it `Select.Value` renders the raw value ("zh", "expressions").
  const presetItems = presets.map((item) => ({ value: item.key, label: item.label }));
  const languageItems = promptLanguageItems(t);

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label htmlFor={id} className="text-xs font-semibold text-foreground/90">
          {label}
        </label>
        <div className="flex flex-wrap items-center gap-1.5">
          {actions}
          {presetKind && presets.length > 0 ? (
            <Select
              items={presetItems}
              value={preset ?? ""}
              onValueChange={(next) => {
                const chosen = presets.find((item) => item.key === next);
                if (!chosen) return;
                onPresetChange?.(chosen.key);
                onChange(chosen.template);
              }}
            >
              <SelectTrigger size="sm" className="h-7 min-w-28 text-[11px]" aria-label={t("prompt.presets")}>
                <SelectValue placeholder={t("prompt.presets")} />
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {presets.map((item) => (
                  <SelectItem key={item.key} value={item.key} label={item.label} className="text-xs">
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
          <Select items={languageItems} value={language} onValueChange={(next) => setLanguage((next ?? "auto") as OutputLanguage)}>
            <SelectTrigger size="sm" className="h-7 min-w-20 text-[11px]" aria-label={t("common.promptLanguageAuto")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent alignItemWithTrigger={false}>
              <SelectItem value="auto" label={t("common.promptLanguageAuto")} className="text-xs">
                {t("common.promptLanguageAuto")}
              </SelectItem>
              <SelectItem value="zh" label={t("common.promptLanguageZh")} className="text-xs">
                {t("common.promptLanguageZh")}
              </SelectItem>
              <SelectItem value="en" label={t("common.promptLanguageEn")} className="text-xs">
                {t("common.promptLanguageEn")}
              </SelectItem>
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant={optimizing ? "destructive" : "outline"}
            size="xs"
            // Stopping stays available while it runs, which is the whole point; only the
            // start path needs something to optimise.
            disabled={optimizing ? false : busy || !value.trim()}
            onClick={optimizing ? stop : start}
            className={cn("h-7 gap-1 text-[11px] cursor-pointer transition-colors", optimizing && "animate-pulse font-medium")}
            title={optimizing ? t("common.stopOptimizePrompt") : t("common.optimizePrompt")}
          >
            {optimizing ? (
              <Square data-icon="inline-start" className="size-2.5 fill-current" />
            ) : (
              <Sparkles data-icon="inline-start" className="size-3 text-primary" />
            )}
            {optimizing ? t("common.stopOptimizePrompt") : t("common.optimizePrompt")}
          </Button>
        </div>
      </div>
      <Textarea
        id={id}
        value={value}
        maxLength={maxLength}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="field-sizing-fixed min-h-28 resize-y rounded-xl text-xs leading-relaxed"
      />
    </div>
  );
}

/** The "draft it for me" button that sits beside a prompt field, with its own stop state. */
export function DraftPromptButton({
  drafting,
  disabled,
  onStart,
  onStop,
}: {
  drafting: boolean;
  disabled?: boolean;
  onStart: () => void;
  onStop: () => void;
}) {
  const { t } = useI18n();
  return (
    <Button
      type="button"
      variant={drafting ? "destructive" : "outline"}
      size="xs"
      disabled={drafting ? false : disabled}
      onClick={drafting ? onStop : onStart}
      className={cn("h-7 gap-1 text-[11px] cursor-pointer transition-colors", drafting && "animate-pulse font-medium")}
    >
      {drafting ? (
        <Square data-icon="inline-start" className="size-2.5 fill-current" />
      ) : (
        <Wand2 data-icon="inline-start" className="size-3 text-primary" />
      )}
      {drafting ? t("common.stopGeneration") : t("character.draftPrompt")}
    </Button>
  );
}
