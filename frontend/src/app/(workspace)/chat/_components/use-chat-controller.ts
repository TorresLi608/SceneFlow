"use client";

import { useChat } from "@ai-sdk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createChatSessionAction,
  deleteChatSessionAction,
  listChatMessagesAction,
  listChatSessionsAction,
} from "@/actions/chat-actions";
import { queryKeys } from "@/actions/query-keys";
import { markRunningStepsStopped, runningSessionIds } from "@/lib/chat-runtime";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import {
  EMPTY_SESSION_RUNTIME,
  NEW_CHAT_ID,
  useChatRuntimeStore,
  type ChatRuntimeErrorKind,
} from "@/store/chat-runtime-store";
import type { UserConfig } from "@/types/auth";
import type { ChatAttachment } from "@/types/chat";

import { chatSessionRegistry } from "./chat-session-registry";
import { messageKey, toChatMessage, toUiMessage, type SceneFlowUIMessage } from "./chat-ui-messages";

const CHAT_ROUTE = "/chat";

const ERROR_FALLBACK_KEYS: Record<ChatRuntimeErrorKind, string> = {
  send: "chat.sendFailed",
  create: "chat.createSessionFailed",
  delete: "chat.deleteSessionFailed",
};

function configSelectValue(config: UserConfig) {
  return `${config.source}:${config.id}`;
}

function selectedConfigPayload(config: UserConfig | undefined) {
  if (!config) {
    return {};
  }
  return config.source === "official" ? { officialConfigId: config.id } : { configId: config.id };
}

function isChatConfig(config: UserConfig) {
  return ["general", "script"].includes(config.purpose) && config.isEnabled && config.modelSeries.trim();
}

export function useChatController(configs: UserConfig[], officialConfigs: UserConfig[]) {
  const { t } = useI18n();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const router = useRouter();
  const routeSessionId = searchParams.get("chat");
  const [selection, setSelection] = useState({ routeSessionId, sessionId: routeSessionId });
  if (pathname === CHAT_ROUTE && routeSessionId !== selection.routeSessionId) {
    // A history/deep-link navigation wins; the bare menu URL restores the last viewed session.
    setSelection({ routeSessionId, sessionId: routeSessionId ?? selection.sessionId });
  }
  const selectedSessionId = selection.sessionId;
  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [input, setInput] = useState("");
  // The chat surface stays mounted while other workspace menus are shown; only touch the URL on /chat.
  const isChatRouteActive = pathname === CHAT_ROUTE;
  const setRouteSessionId = useCallback((sessionId: string | null) => {
    if (window.location.pathname !== CHAT_ROUTE) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("chat") === sessionId) return;
    if (sessionId) {
      params.set("chat", sessionId);
    } else {
      params.delete("chat");
    }
    const query = params.toString();
    router.replace(`${CHAT_ROUTE}${query ? `?${query}` : ""}${window.location.hash}`, { scroll: false });
  }, [router]);
  const setSelectedSessionId = useCallback((sessionId: string | null) => {
    setSelection((current) => ({ ...current, sessionId }));
    setRouteSessionId(sessionId);
  }, [setRouteSessionId]);

  const userChatConfigs = useMemo(
    () => configs.filter(isChatConfig),
    [configs]
  );
  const officialChatConfigs = useMemo(
    () => officialConfigs.filter(isChatConfig),
    [officialConfigs]
  );
  const chatConfigs = useMemo(() => [...officialChatConfigs, ...userChatConfigs], [officialChatConfigs, userChatConfigs]);
  const defaultConfigId = useMemo(
    () => {
      const config =
        userChatConfigs.find((item) => item.isActive) ??
        officialChatConfigs.find((item) => item.isActive) ??
        officialChatConfigs[0] ??
        userChatConfigs[0];
      return config ? configSelectValue(config) : "";
    },
    [officialChatConfigs, userChatConfigs]
  );
  const sessionsQuery = useQuery({
    queryKey: queryKeys.chatSessions,
    queryFn: listChatSessionsAction,
  });
  const effectiveSessionId = selectedSessionId ?? sessionsQuery.data?.sessions[0]?.id ?? null;
  const runtimeKey = effectiveSessionId ?? NEW_CHAT_ID;
  const messagesQuery = useQuery({
    queryKey: queryKeys.chatMessages(effectiveSessionId),
    queryFn: () => listChatMessagesAction(effectiveSessionId || ""),
    enabled: Boolean(effectiveSessionId),
  });

  const effectiveConfigId = selectedConfigId || defaultConfigId;
  const selectedConfig = chatConfigs.find((config) => configSelectValue(config) === effectiveConfigId);
  const loadedMessages = messagesQuery.data?.messages;
  const serverMessages = useMemo(() => (loadedMessages ?? []).map(toUiMessage), [loadedMessages]);
  const serverMessageKey = useMemo(() => messageKey(serverMessages), [serverMessages]);

  // Each session owns its AI SDK instance; viewing another session swaps the subscription instead of
  // discarding a running stream, and a stream that finished while hidden is still there on return.
  const chatInstance = useMemo(() => chatSessionRegistry.ensure(runtimeKey), [runtimeKey]);
  const {
    messages: aiMessages,
    setMessages: setAiMessages,
    status: chatStatus,
  } = useChat<SceneFlowUIMessage>({ chat: chatInstance });
  const runtime = useChatRuntimeStore((state) => state.sessions[runtimeKey] ?? EMPTY_SESSION_RUNTIME);
  const runtimeSessions = useChatRuntimeStore((state) => state.sessions);
  const patchSession = useChatRuntimeStore((state) => state.patchSession);
  const runningIds = useMemo(() => runningSessionIds(runtimeSessions, NEW_CHAT_ID), [runtimeSessions]);

  const isStreaming = chatStatus === "submitted" || chatStatus === "streaming";
  const chatMessageKey = useMemo(() => messageKey(aiMessages), [aiMessages]);

  useEffect(() => {
    if (!isChatRouteActive || (!selectedSessionId && !sessionsQuery.data)) {
      return;
    }
    setRouteSessionId(effectiveSessionId);
  }, [effectiveSessionId, isChatRouteActive, selectedSessionId, sessionsQuery.data, setRouteSessionId]);

  useEffect(() => {
    if (chatStatus === "ready" && serverMessageKey !== chatMessageKey && serverMessages.length >= aiMessages.length) {
      setAiMessages(serverMessages);
    }
  }, [aiMessages.length, chatMessageKey, chatStatus, serverMessageKey, serverMessages, setAiMessages]);

  const createSessionMutation = useMutation({
    mutationFn: createChatSessionAction,
    onSuccess: async (response) => {
      setSelectedSessionId(response.session.id);
      patchSession(runtimeKey, { error: null });
      await queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions });
    },
    onError: (error) => {
      patchSession(runtimeKey, { error: { cause: error, kind: "create" } });
    },
  });

  const deleteSessionMutation = useMutation({
    mutationFn: deleteChatSessionAction,
    onSuccess: async (_, deletedId) => {
      chatSessionRegistry.remove(deletedId);
      if (effectiveSessionId === deletedId) {
        setSelectedSessionId(sessionsQuery.data?.sessions.find((session) => session.id !== deletedId)?.id ?? null);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chatMessages(deletedId) }),
      ]);
    },
    onError: (error) => {
      patchSession(runtimeKey, { error: { cause: error, kind: "delete" } });
    },
  });

  const isCreatingSession = createSessionMutation.isPending;
  // Busy is scoped to the viewed session: other sessions stay usable while this one is answering.
  const isBusy = isCreatingSession || runtime.isSending || isStreaming;
  const errorMessage = runtime.error
    ? resolveRequestError(runtime.error.cause, t(ERROR_FALLBACK_KEYS[runtime.error.kind]))
    : null;

  const createSession = () => {
    if (isCreatingSession) {
      return;
    }
    createSessionMutation.mutate({
      title: input.trim().slice(0, 40) || t("chat.newSession"),
      ...selectedConfigPayload(selectedConfig),
    });
  };

  const selectSession = (id: string) => {
    setSelectedSessionId(id);
  };

  const isSessionRunning = (id: string) => Boolean(runtimeSessions[id]?.isSending) || chatSessionRegistry.isRunning(id);

  const deleteSession = (id: string) => {
    if (isSessionRunning(id)) {
      return;
    }
    deleteSessionMutation.mutate(id);
  };

  const streamToSession = async (sessionId: string, content: string, attachments: ChatAttachment[] = []) => {
    if (!selectedConfig) {
      return;
    }

    const target = chatSessionRegistry.ensure(sessionId);
    patchSession(sessionId, { agentSteps: [], error: null, isSending: true, stopped: false });
    try {
      await target.sendMessage(
        {
          text: content,
          metadata: {
            attachments,
            createdAt: new Date().toISOString(),
            model: selectedConfig.modelSeries,
            provider: selectedConfig.provider,
            sessionId,
          },
        },
        { body: { sessionId, ...selectedConfigPayload(selectedConfig) } }
      );
      setInput("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chatMessages(sessionId) }),
      ]);
    } finally {
      patchSession(sessionId, { isSending: false });
    }
  };

  const sendMessage = async (nextContent?: string, attachments: ChatAttachment[] = []) => {
    const content = (nextContent ?? input).trim();
    if ((!content && attachments.length === 0) || isBusy || !selectedConfig) {
      return;
    }

    if (effectiveSessionId) {
      try {
        await streamToSession(effectiveSessionId, content, attachments);
      } catch (error) {
        patchSession(effectiveSessionId, { agentSteps: [], error: { cause: error, kind: "send" } });
      }
      return;
    }

    patchSession(NEW_CHAT_ID, { error: null, isSending: true });
    let sessionId: string | null = null;
    try {
      const response = await createChatSessionAction({
        title: content.slice(0, 40) || attachments[0]?.name?.slice(0, 40) || t("chat.newSession"),
        ...selectedConfigPayload(selectedConfig),
      });
      sessionId = response.session.id;
      // View the new session's own instance before its first turn starts: the optimistic user
      // message lands in that instance, so nothing is lost to a discarded runtime.
      setSelectedSessionId(sessionId);
      patchSession(NEW_CHAT_ID, { isSending: false });
      void queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions });
      await streamToSession(sessionId, content, attachments);
    } catch (error) {
      patchSession(sessionId ?? NEW_CHAT_ID, {
        agentSteps: [],
        isSending: false,
        error: { cause: error, kind: sessionId ? "send" : "create" },
      });
    }
  };

  const stop = () => {
    patchSession(runtimeKey, (current) => ({
      stopped: true,
      agentSteps: markRunningStepsStopped(current.agentSteps, t("chat.stopped")),
    }));
    void chatInstance.stop();
    if (effectiveSessionId) {
      const sessionId = effectiveSessionId;
      window.setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.chatMessages(sessionId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions });
      }, 300);
    }
  };

  return {
    chatConfigs,
    effectiveConfigId,
    effectiveSessionId,
    selectedConfig,
    sessions: sessionsQuery.data?.sessions ?? [],
    sessionsLoading: sessionsQuery.isLoading,
    // Admin retention window for chat; 0 (or not loaded yet) means nothing expires and no notice is shown.
    sessionRetentionDays: sessionsQuery.data?.retentionDays ?? 0,
    messages: aiMessages.map((message) => toChatMessage(message, effectiveSessionId, selectedConfig)),
    agentSteps: runtime.agentSteps,
    messagesLoading: messagesQuery.isLoading,
    input,
    setInput,
    errorMessage,
    isBusy,
    isStreaming,
    isCreatingSession,
    /** Sessions with a turn in flight, including ones the user is not currently viewing. */
    runningSessionIds: runningIds,
    createSession,
    selectSession,
    deleteSession,
    sendMessage,
    stop,
    setSelectedConfigId,
  };
}
