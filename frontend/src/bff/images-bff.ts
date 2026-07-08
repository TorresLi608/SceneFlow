import { authConfig, backendClient } from "@/lib/http/backend-client";
import type { GenerateImageInput, GenerateImageResponse } from "@/types/image-generation";

export async function generateImageByBff(payload: GenerateImageInput, authorization?: string) {
  const response = await backendClient.post<GenerateImageResponse>("/api/images/generate", payload, authConfig(authorization));
  return response.data;
}
