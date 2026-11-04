import type { UIMessage } from "ai";

import type { UserConfig } from "@/types/auth";
import type { ChatAgentStep, ChatAttachment, ChatMessage } from "@/types/chat";

export type ChatMessageMetadata = {
  attachments?: ChatAttachment[];
  chatMessage?: ChatMessage;
  createdAt?: string;
  model?: string;
  provider?: string;
  sessionId?: string;
};

export type ChatMessageData = {
  agent_step: ChatAgentStep;
};

export type SceneFlowUIMessage = UIMessage<ChatMessageMetadata, ChatMessageData>;

export function uiMessageText(message: SceneFlowUIMessage) {
  return message.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");
}

export function uiMessageReasoning(message: SceneFlowUIMessage) {
  return message.parts
    .filter((part) => part.type === "reasoning")
    .map((part) => part.text)
    .join("");
}

export function toUiMessage(message: ChatMessage): SceneFlowUIMessage {
  return {
    id: message.id,
    role: message.role,
    metadata: { chatMessage: message },
    parts: [
      ...(message.reasoning ? [{ type: "reasoning" as const, text: message.reasoning, state: "done" as const }] : []),
      { type: "text", text: message.content, state: "done" },
    ],
  };
}

export function toChatMessage(message: SceneFlowUIMessage, sessionId: string | null, config: UserConfig | undefined): ChatMessage {
  const saved = message.metadata?.chatMessage;
  return {
    id: saved?.id ?? message.id,
    sessionId: saved?.sessionId ?? message.metadata?.sessionId ?? sessionId ?? "",
    role: message.role,
    content: uiMessageText(message) || saved?.content || "",
    attachments: saved?.attachments ?? message.metadata?.attachments ?? [],
    reasoning: uiMessageReasoning(message) || saved?.reasoning || "",
    provider: saved?.provider ?? message.metadata?.provider ?? config?.provider ?? "",
    model: saved?.model ?? message.metadata?.model ?? config?.modelSeries ?? "",
    createdAt: saved?.createdAt ?? message.metadata?.createdAt ?? new Date().toISOString(),
  };
}

export function messageKey(messages: SceneFlowUIMessage[]) {
  return messages.map((message) => message.id).join("|");
}

export function chatRequestBody(message: SceneFlowUIMessage | undefined, body: Record<string, unknown> | undefined) {
  return {
    content: message ? uiMessageText(message).trim() : "",
    attachments: message?.metadata?.attachments ?? [],
    configId: body?.configId,
    officialConfigId: body?.officialConfigId,
  };
}
