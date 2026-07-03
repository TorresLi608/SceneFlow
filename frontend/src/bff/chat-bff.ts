import { backendClient } from "@/lib/http/backend-client";
import type {
  ChatMessageListResponse,
  ChatSessionItemResponse,
  ChatSessionListResponse,
  SendChatMessageResponse,
} from "@/types/chat";

export async function listChatSessionsByBff(authorization?: string) {
  const response = await backendClient.get<ChatSessionListResponse>("/api/chat/sessions", {
    headers: { Authorization: authorization },
  });
  return response.data;
}

export async function createChatSessionByBff(
  payload: { title?: string; configId?: number; officialConfigId?: number },
  authorization?: string
) {
  const response = await backendClient.post<ChatSessionItemResponse>("/api/chat/sessions", payload, {
    headers: { Authorization: authorization },
  });
  return response.data;
}

export async function deleteChatSessionByBff(sessionId: string, authorization?: string) {
  const response = await backendClient.delete<{ ok: boolean }>(`/api/chat/sessions/${sessionId}`, {
    headers: { Authorization: authorization },
  });
  return response.data;
}

export async function listChatMessagesByBff(sessionId: string, authorization?: string) {
  const response = await backendClient.get<ChatMessageListResponse>(`/api/chat/sessions/${sessionId}/messages`, {
    headers: { Authorization: authorization },
  });
  return response.data;
}

export async function sendChatMessageByBff(
  sessionId: string,
  payload: { content: string; configId?: number; officialConfigId?: number },
  authorization?: string
) {
  const response = await backendClient.post<SendChatMessageResponse>(
    `/api/chat/sessions/${sessionId}/messages`,
    payload,
    { headers: { Authorization: authorization } }
  );
  return response.data;
}
