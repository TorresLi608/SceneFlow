import { generationRequestTimeout, httpClient } from "@/lib/http/client";
import type { GenerationReferenceInput } from "@/types/project";

export type PromptKind = "image" | "video" | "voice" | "audio" | "character" | "prop" | "cover";

/** One reference as the provider will be given it: `图1`, `视频1`, `音频1`. */
export interface CompiledPromptMedia {
  type: "reference_image" | "reference_video" | "reference_audio";
  index: number;
  kind: string;
  id: string | null;
  label: string;
}

export interface CompiledPromptResponse {
  prompt: string;
  media: CompiledPromptMedia[];
  provider: string;
  model: string;
  replacements: Record<string, string>;
}

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

/**
 * Rewrites the editor's `@素材` labels into the provider's positional references.
 *
 * `sceneId` is what lets the backend account for the storyboard frame a video render
 * prepends — without it the preview numbers the references one lower than the model
 * will see them.
 */
export async function compilePromptAction(
  payload: {
    projectId: string;
    sceneId?: string;
    kind: "image" | "video";
    prompt: string;
    dialogue?: string;
    references?: GenerationReferenceInput[];
  },
  signal?: AbortSignal,
) {
  const response = await httpClient.post<CompiledPromptResponse>("/api/bff/prompts/compile", payload, { signal });
  return response.data;
}
