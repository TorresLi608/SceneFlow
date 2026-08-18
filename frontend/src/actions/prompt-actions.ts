import { generationRequestTimeout, httpClient } from "@/lib/http/client";

export interface OptimizePromptInput {
  kind: "image" | "video" | "audio";
  prompt: string;
  context?: {
    outputLanguage?: "auto" | "zh" | "en";
    aspectRatio?: string;
    quality?: string;
    duration?: number;
    fps?: number;
    voice?: string;
    speechRate?: number;
    pitchRate?: number;
    instruction?: string;
    language?: string;
  };
}

export async function optimizePromptAction(payload: OptimizePromptInput) {
  const response = await httpClient.post<{ prompt: string }>("/api/bff/prompts/optimize", payload, {
    timeout: generationRequestTimeout,
  });
  return response.data;
}
