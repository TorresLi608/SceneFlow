import { httpClient } from "@/lib/http/client";
import type {
  SendChatMessageInput,
  ChatMessageListResponse,
  ChatSessionItemResponse,
  ChatSessionListResponse,
  SendChatMessageResponse,
} from "@/types/chat";

export async function listChatSessionsAction() {
  const response = await httpClient.get<ChatSessionListResponse>("/api/bff/chat/sessions");
  return response.data;
}

export async function createChatSessionAction(payload: { title?: string; configId?: number; officialConfigId?: number }) {
  const response = await httpClient.post<ChatSessionItemResponse>("/api/bff/chat/sessions", payload);
  return response.data;
}

export async function deleteChatSessionAction(sessionId: string) {
  const response = await httpClient.delete<{ ok: boolean }>(`/api/bff/chat/sessions/${sessionId}`);
  return response.data;
}

export async function listChatMessagesAction(sessionId: string) {
  const response = await httpClient.get<ChatMessageListResponse>(`/api/bff/chat/sessions/${sessionId}/messages`);
  return response.data;
}

export async function sendChatMessageAction(
  sessionId: string,
  payload: SendChatMessageInput
) {
  const response = await httpClient.post<SendChatMessageResponse>(
    `/api/bff/chat/sessions/${sessionId}/messages`,
    payload
  );
  return response.data;
}
