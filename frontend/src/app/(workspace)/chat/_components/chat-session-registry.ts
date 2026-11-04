"use client";

import { Chat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";

import { useChatRuntimeStore } from "@/store/chat-runtime-store";
import { useUserStore } from "@/store/user-store";

import { clearFailedReasoning } from "./chat-message-state";
import { chatRequestBody, type SceneFlowUIMessage } from "./chat-ui-messages";

/**
 * One AI SDK `Chat` instance per chat session, kept outside React.
 *
 * `useChat` subscribes to whichever instance the controller hands it, so switching sessions swaps
 * the viewed instance instead of discarding the running one. An answer streaming into session A
 * keeps running (and is visible again when the user returns) while session B is used or a new
 * session is created. Instances are created lazily and dropped when the session is deleted or the
 * auth token changes.
 */
const transport = new DefaultChatTransport<SceneFlowUIMessage>({
  api: "/api/bff/chat/sessions/_/messages/stream",
  // Resolved per request so a token refresh or re-login never sends a stale credential.
  headers: (): Record<string, string> => {
    const token = useUserStore.getState().token;
    return token ? { Authorization: `Bearer ${token}` } : {};
  },
  prepareSendMessagesRequest: ({ messages, body, headers }) => {
    const sessionId = typeof body?.sessionId === "string" ? body.sessionId : "_";
    return {
      api: `/api/bff/chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`,
      headers,
      body: chatRequestBody(messages.at(-1), body),
    };
  },
});

const instances = new Map<string, Chat<SceneFlowUIMessage>>();

function createChat(sessionId: string) {
  const chat: Chat<SceneFlowUIMessage> = new Chat<SceneFlowUIMessage>({
    id: sessionId,
    transport,
    onData: (part) => {
      if (part.type !== "data-agent_step") {
        return;
      }
      const runtime = useChatRuntimeStore.getState();
      if (runtime.sessions[sessionId]?.stopped && part.data.status === "running") {
        return;
      }
      runtime.pushAgentStep(sessionId, part.data);
    },
    onError: (error) => {
      useChatRuntimeStore.getState().patchSession(sessionId, { agentSteps: [], error: { cause: error, kind: "send" } });
      chat.messages = clearFailedReasoning(chat.messages);
    },
  });
  return chat;
}

function isRunningStatus(status: Chat<SceneFlowUIMessage>["status"] | undefined) {
  return status === "submitted" || status === "streaming";
}

export const chatSessionRegistry = {
  get(sessionId: string) {
    return instances.get(sessionId);
  },
  /** Returns the session's instance, creating it on first use. Server renders never cache instances. */
  ensure(sessionId: string) {
    const existing = instances.get(sessionId);
    if (existing) {
      return existing;
    }
    const chat = createChat(sessionId);
    if (typeof window !== "undefined") {
      instances.set(sessionId, chat);
    }
    return chat;
  },
  isRunning(sessionId: string) {
    return isRunningStatus(instances.get(sessionId)?.status);
  },
  remove(sessionId: string) {
    const chat = instances.get(sessionId);
    if (chat) {
      void chat.stop();
      instances.delete(sessionId);
    }
    useChatRuntimeStore.getState().removeSession(sessionId);
  },
  clear() {
    for (const chat of instances.values()) {
      void chat.stop();
    }
    instances.clear();
    useChatRuntimeStore.getState().reset();
  },
};

// A different account must never see, or keep streaming into, the previous account's sessions.
useUserStore.subscribe((state, previous) => {
  if (state.token !== previous.token) {
    chatSessionRegistry.clear();
  }
});
