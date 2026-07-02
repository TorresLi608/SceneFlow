import { httpClient } from "@/lib/http/client";
import { useUserStore } from "@/store/user-store";
import type {
  ChatStreamEvent,
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

export async function listChatMessagesAction(sessionId: string) {
  const response = await httpClient.get<ChatMessageListResponse>(`/api/bff/chat/sessions/${sessionId}/messages`);
  return response.data;
}

export async function sendChatMessageAction(
  sessionId: string,
  payload: { content: string; configId?: number; officialConfigId?: number }
) {
  const response = await httpClient.post<SendChatMessageResponse>(
    `/api/bff/chat/sessions/${sessionId}/messages`,
    payload
  );
  return response.data;
}

export async function streamChatMessageAction(
  sessionId: string,
  payload: { content: string; configId?: number; officialConfigId?: number },
  onEvent: (event: ChatStreamEvent) => void
) {
  const token = useUserStore.getState().token;
  const response = await fetch(`/api/bff/chat/sessions/${sessionId}/messages/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.error || "stream request failed");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim()) {
        onEvent(JSON.parse(line) as ChatStreamEvent);
      }
    }
  }

  if (buffer.trim()) {
    onEvent(JSON.parse(buffer) as ChatStreamEvent);
  }
}
