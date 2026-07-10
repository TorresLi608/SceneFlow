import { httpClient } from "@/lib/http/client";
import type { GenerateVideoInput, GenerateVideoResponse } from "@/types/video-generation";

const videoRequestTimeout = 15 * 60 * 1000;

export async function generateVideoAction(payload: GenerateVideoInput) {
  const response = await httpClient.post<GenerateVideoResponse>("/api/bff/videos/generate", payload, {
    timeout: videoRequestTimeout,
  });
  return response.data;
}
