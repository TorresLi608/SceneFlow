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

export interface ChatMessage {
  id: string;
  sessionId: string;
  role: ChatRole;
  content: string;
  reasoning: string;
  provider: string;
  model: string;
  createdAt: string;
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

export type ChatStreamEvent =
  | { type: "userMessage"; message: ChatMessage }
  | { type: "reasoning_delta"; content: string }
  | { type: "content_delta"; content: string }
  | { type: "assistantMessage"; message: ChatMessage }
  | { type: "error"; error: string };
