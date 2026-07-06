export interface ChatSession {
  id: string;
  title: string;
  configId: number | null;
  officialConfigId: number | null;
  provider: string;
  model: string;
  createdAt: string;
  updatedAt: string;
}

export type ChatRole = "user" | "assistant" | "system";

export type ChatAttachmentPart =
  | { type: "text"; text: string }
  | { type: "image"; image: string; filename?: string }
  | { type: "file"; data: string; mimeType: string; filename?: string };

export interface ChatAttachment {
  id: string;
  type: string;
  name: string;
  contentType?: string;
  content: ChatAttachmentPart[];
}

export interface ChatMessage {
  id: string;
  sessionId: string;
  role: ChatRole;
  content: string;
  attachments: ChatAttachment[];
  reasoning: string;
  provider: string;
  model: string;
  createdAt: string;
}

export interface ChatAgentStep {
  id: string;
  label: string;
  status: "running" | "done" | "error";
  detail?: string;
}

export interface ChatSessionListResponse {
  sessions: ChatSession[];
}

export interface ChatSessionItemResponse {
  session: ChatSession;
}

export interface ChatMessageListResponse {
  messages: ChatMessage[];
}

export interface SendChatMessageResponse {
  userMessage: ChatMessage;
  assistantMessage: ChatMessage;
}

export interface SendChatMessageInput {
  content: string;
  attachments?: ChatAttachment[];
  configId?: number;
  officialConfigId?: number;
}

export type ChatStreamEvent =
  | { type: "userMessage"; message: ChatMessage }
  | { type: "agent_step"; step: ChatAgentStep }
  | { type: "reasoning_delta"; content: string }
  | { type: "content_delta"; content: string }
  | { type: "assistantMessage"; message: ChatMessage }
  | { type: "error"; error: string };
