import { providerLabelMap } from "@/lib/model-providers";
import type { UserConfig } from "@/types/auth";

export function configName(config: UserConfig) {
  const source = config.source === "official" ? "官方" : "自定义";
  return config.name?.trim()
    ? `${source} · ${config.name}`
    : `${source} · ${providerLabelMap[config.provider] ?? config.provider} · ${config.modelSeries}`;
}
