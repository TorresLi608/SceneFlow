import { generationRequestTimeout, httpClient } from "@/lib/http/client";

export type PromptKind = "image" | "video" | "voice" | "audio" | "character" | "prop" | "cover";

export interface OptimizePromptInput {
  kind: PromptKind;
  prompt: string;
  context?: {
    outputLanguage?: "auto" | "zh" | "en";
    aspectRatio?: string;
    quality?: string;
    duration?: number;
    fps?: number;
  };
}

export async function optimizePromptAction(payload: OptimizePromptInput, signal?: AbortSignal) {
  const response = await httpClient.post<{ prompt: string }>("/api/bff/prompts/optimize", payload, {
    timeout: generationRequestTimeout,
    signal,
  });
  return response.data;
}
