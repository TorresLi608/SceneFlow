"use client";

import { generationModelLabel } from "@/lib/config-format";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface GeneratedModelLineProps {
  /** Provider id of the config that produced the item; omitted for voices, which only keep the model. */
  provider?: string;
  model: string;
  className?: string;
}

/**
 * "生成模型：provider · model" under a history item.
 *
 * Renders nothing for rows written before the provider/model columns existed, so an old
 * history list does not fill up with empty labels.
 */
export function GeneratedModelLine({ provider = "", model, className }: GeneratedModelLineProps) {
  const { t } = useI18n();
  const label = generationModelLabel(provider, model, t);
  if (!label) return null;
  return (
    <span className={cn("block truncate text-[10px]", className)} title={label}>
      {t("common.generatedWith", { model: label })}
    </span>
  );
}
