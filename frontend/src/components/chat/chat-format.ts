import type { UserConfig } from "@/types/auth";
import type { ChatMessage } from "@/types/chat";

export const providerLabelMap: Record<string, string> = {
  qwen: "Qwen",
  deepseek: "DeepSeek",
  doubao: "Doubao",
  openai: "OpenAI",
  custom: "Custom relay",
  "seedance2.0": "Seedance 2.0",
};

export function configName(config: UserConfig) {
  const source = config.source === "official" ? "官方" : "自定义";
  return config.name?.trim()
    ? `${source} · ${config.name}`
    : `${source} · ${providerLabelMap[config.provider] ?? config.provider} · ${config.modelSeries}`;
}

export function messageClass(role: ChatMessage["role"]) {
  return role === "user" ? "ml-auto bg-primary text-primary-foreground" : "mr-auto bg-muted text-foreground";
}
