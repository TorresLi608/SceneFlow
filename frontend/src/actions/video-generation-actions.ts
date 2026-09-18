import { generationRequestTimeout, httpClient } from "@/lib/http/client";
import type { GenerationHistoryListResponse } from "@/types/generation-history";
import type { GenerateVideoInput, GenerateVideoResponse } from "@/types/video-generation";

export async function generateVideoAction(payload: GenerateVideoInput, signal?: AbortSignal) {
  const response = await httpClient.post<GenerateVideoResponse>("/api/bff/videos/generate", payload, {
    timeout: generationRequestTimeout,
    signal,
  });
  return response.data;
}

export async function listVideoHistoryAction() {
  const response = await httpClient.get<GenerationHistoryListResponse>("/api/bff/videos/history");
  return response.data;
}

export async function deleteVideoHistoryAction(id: string) {
  await httpClient.delete(`/api/bff/videos/history/${encodeURIComponent(id)}`);
}
