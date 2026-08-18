import { generationRequestTimeout, httpClient } from "@/lib/http/client";
import type { GenerateAudioInput, GenerateAudioResponse } from "@/types/audio-generation";

export async function generateAudioAction(payload: GenerateAudioInput) {
  const response = await httpClient.post<GenerateAudioResponse>("/api/bff/audio/generate", payload, {
    timeout: generationRequestTimeout,
  });
  return response.data;
}
