import { generationRequestTimeout, httpClient } from "@/lib/http/client";
import type { UserVoice } from "@/types/voice-generation";

export async function listUserVoicesAction() {
  const response = await httpClient.get<{ voices: UserVoice[] }>("/api/bff/voices");
  return response.data;
}

export async function saveVoiceAction(id: string) {
  const response = await httpClient.post<{ voice: UserVoice }>(`/api/bff/voices/${id}/save`);
  return response.data;
}

export async function designVoiceAction(payload: { name: string; voicePrompt: string; previewText: string; configId?: number; officialConfigId?: number }, signal?: AbortSignal) {
  const response = await httpClient.post<{ voice: UserVoice }>("/api/bff/voices/design", payload, { timeout: generationRequestTimeout, signal });
  return response.data;
}

export async function deleteVoiceAction(id: string) {
  await httpClient.delete(`/api/bff/voices/${id}`);
}
