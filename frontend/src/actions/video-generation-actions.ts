import { generationRequestTimeout, httpClient } from "@/lib/http/client";
import type { GenerateVideoInput, GenerateVideoResponse } from "@/types/video-generation";

export async function generateVideoAction(payload: GenerateVideoInput) {
  const response = await httpClient.post<GenerateVideoResponse>("/api/bff/videos/generate", payload, {
    timeout: generationRequestTimeout,
  });
  return response.data;
}
