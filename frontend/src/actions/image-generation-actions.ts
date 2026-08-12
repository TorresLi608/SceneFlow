import { generationRequestTimeout, httpClient } from "@/lib/http/client";
import type { GenerateImageInput, GenerateImageResponse } from "@/types/image-generation";

export async function generateImageAction(payload: GenerateImageInput) {
  const response = await httpClient.post<GenerateImageResponse>("/api/bff/images/generate", payload, {
    timeout: generationRequestTimeout,
  });
  return response.data;
}
