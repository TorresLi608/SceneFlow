import { providerLabel } from "@/lib/model-providers";
import type { UserConfig } from "@/types/auth";

type Translate = (key: string, params?: Record<string, string | number>) => string;

export function configName(config: UserConfig, t?: Translate) {
  const source = config.source === "official"
    ? t?.("config.source.official") ?? "Official"
    : t?.("config.source.custom") ?? "Custom";
  return config.name?.trim()
    ? `${source} · ${config.name}`
    : `${source} · ${providerLabel(config.provider, t)} · ${config.modelSeries}`;
}

/**
 * "Provider · model" for a stored generation result, as the history panels show it.
 *
 * Rows written before the provider/model columns existed carry empty strings, so either
 * half may be missing; the label drops what it does not have instead of printing " · ".
 */
export function generationModelLabel(provider: string, model: string, t?: Translate) {
  const providerName = provider.trim() ? providerLabel(provider.trim(), t) : "";
  return [providerName, model.trim()].filter(Boolean).join(" · ");
}
