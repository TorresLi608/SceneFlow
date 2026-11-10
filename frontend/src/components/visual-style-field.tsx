"use client";

import { Toggle } from "@base-ui/react/toggle";
import { ToggleGroup } from "@base-ui/react/toggle-group";
import { useId } from "react";

import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { useI18n } from "@/lib/i18n";
import type { VisualStyle } from "@/types/project";

const styles = ["cinematic", "anime", "realistic", "3d"] as const;

export function VisualStyleField({ value, onChange, disabled = false }: {
  value: VisualStyle;
  onChange: (style: VisualStyle) => void;
  disabled?: boolean;
}) {
  const { t } = useI18n();
  const id = useId();

  return (
    <Field data-disabled={disabled || undefined}>
      <FieldLabel id={`${id}-label`}>{t("home.visualStyle")}</FieldLabel>
      <ToggleGroup
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-hint`}
        value={value ? [value] : []}
        disabled={disabled}
        onValueChange={(values) => {
          // Keep one selection: pressing the active choice must not clear the style.
          if (values[0]) onChange(values[0]);
        }}
        className="grid grid-cols-2 gap-2 sm:grid-cols-4"
      >
        {styles.map((style) => (
          <Toggle
            key={style}
            value={style}
            type="button"
            className="min-h-12 rounded-xl border border-border bg-muted/30 px-3 py-2 text-sm font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 data-pressed:border-primary data-pressed:bg-primary/10 data-pressed:text-primary"
          >
            {t(`home.visualStyle.${style}`)}
          </Toggle>
        ))}
      </ToggleGroup>
      <FieldDescription id={`${id}-hint`}>
        {t(value ? "home.visualStyleHint" : "home.visualStyleLegacyHint")}
      </FieldDescription>
    </Field>
  );
}
