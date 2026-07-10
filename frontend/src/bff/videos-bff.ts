import { authConfig, backendClient } from "@/lib/http/backend-client";
import type { GenerateVideoInput, GenerateVideoResponse } from "@/types/video-generation";

const videoRequestTimeout = 15 * 60 * 1000;

export async function generateVideoByBff(payload: GenerateVideoInput, authorization?: string) {
  const response = await backendClient.post<GenerateVideoResponse>("/api/videos/generate", payload, {
    ...(authConfig(authorization) ?? {}),
    timeout: videoRequestTimeout,
  });
  return response.data;
}
