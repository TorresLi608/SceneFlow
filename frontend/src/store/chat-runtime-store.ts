"use client";

import { create } from "zustand";

import { upsertAgentStep } from "@/lib/chat-runtime";
import type { ChatAgentStep } from "@/types/chat";

/** Runtime key for the composer shown before a session exists. */
export const NEW_CHAT_ID = "new-chat";

export type ChatRuntimeErrorKind = "send" | "create" | "delete";

export interface ChatSessionRuntime {
  /** Transient execution-trace steps of the current turn; never persisted into messages. */
  agentSteps: ChatAgentStep[];
  /** Raw failure of the last action on this session; the controller renders it with i18n. */
  error: { cause: unknown; kind: ChatRuntimeErrorKind } | null;
  /** True from submitting a turn until the final history refresh completes. */
  isSending: boolean;
  /** Set by an explicit stop so late `running` steps from the aborted stream are ignored. */
  stopped: boolean;
}

export const EMPTY_SESSION_RUNTIME: ChatSessionRuntime = Object.freeze({
  agentSteps: [],
  error: null,
  isSending: false,
  stopped: false,
}) as ChatSessionRuntime;

type RuntimePatch = Partial<ChatSessionRuntime> | ((current: ChatSessionRuntime) => Partial<ChatSessionRuntime>);

interface ChatRuntimeStoreState {
  /** Per-session run state keyed by session id (or `NEW_CHAT_ID`). In memory only; cleared with the auth token. */
  sessions: Record<string, ChatSessionRuntime>;
  patchSession: (id: string, patch: RuntimePatch) => void;
  pushAgentStep: (id: string, step: ChatAgentStep) => void;
  removeSession: (id: string) => void;
  reset: () => void;
}

/**
 * Chat run flags live outside the page so a streaming answer keeps its execution trace and busy
 * state per session: switching sessions, opening a new one, or leaving the chat menu no longer
 * resets or blocks it. Message/stream state itself stays with the AI SDK `Chat` instances in the
 * chat session registry.
 */
export const useChatRuntimeStore = create<ChatRuntimeStoreState>()((set) => ({
  sessions: {},
  patchSession: (id, patch) =>
    set((state) => {
      const current = state.sessions[id] ?? EMPTY_SESSION_RUNTIME;
      const next = typeof patch === "function" ? patch(current) : patch;
      return { sessions: { ...state.sessions, [id]: { ...current, ...next } } };
    }),
  pushAgentStep: (id, step) =>
    set((state) => {
      const current = state.sessions[id] ?? EMPTY_SESSION_RUNTIME;
      return { sessions: { ...state.sessions, [id]: { ...current, agentSteps: upsertAgentStep(current.agentSteps, step) } } };
    }),
  removeSession: (id) =>
    set((state) => {
      if (!(id in state.sessions)) {
        return state;
      }
      const sessions = { ...state.sessions };
      delete sessions[id];
      return { sessions };
    }),
  reset: () => set({ sessions: {} }),
}));
