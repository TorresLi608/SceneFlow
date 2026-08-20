import { generationRequestTimeout, httpClient } from "@/lib/http/client";
import type { GenerateVideoInput, GenerateVideoResponse } from "@/types/video-generation";

export async function generateVideoAction(payload: GenerateVideoInput, signal?: AbortSignal) {
  const response = await httpClient.post<GenerateVideoResponse>("/api/bff/videos/generate", payload, {
    timeout: generationRequestTimeout,
    signal,
  });
  return response.data;
}
