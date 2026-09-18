import { generationRequestTimeout, httpClient } from "@/lib/http/client";
import type { GenerationHistoryListResponse } from "@/types/generation-history";
import type { GenerateImageInput, GenerateImageResponse } from "@/types/image-generation";

export async function generateImageAction(payload: GenerateImageInput, signal?: AbortSignal) {
  const response = await httpClient.post<GenerateImageResponse>("/api/bff/images/generate", payload, {
    timeout: generationRequestTimeout,
    signal,
  });
  return response.data;
}

export async function listImageHistoryAction() {
  const response = await httpClient.get<GenerationHistoryListResponse>("/api/bff/images/history");
  return response.data;
}

export async function deleteImageHistoryAction(id: string) {
  await httpClient.delete(`/api/bff/images/history/${encodeURIComponent(id)}`);
}
