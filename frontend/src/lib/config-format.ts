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
