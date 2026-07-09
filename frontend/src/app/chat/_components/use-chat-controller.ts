"use client";

import { useChat } from "@ai-sdk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DefaultChatTransport, type UIMessage } from "ai";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createChatSessionAction,
  deleteChatSessionAction,
  listChatMessagesAction,
  listChatSessionsAction,
} from "@/actions/chat-actions";
import { queryKeys } from "@/actions/query-keys";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/store/user-store";
import type { UserConfig } from "@/types/auth";
import type { ChatAgentStep, ChatAttachment, ChatMessage } from "@/types/chat";

type ChatMessageMetadata = {
  attachments?: ChatAttachment[];
  chatMessage?: ChatMessage;
  createdAt?: string;
  model?: string;
  provider?: string;
  sessionId?: string;
};

type ChatMessageData = {
  agent_step: ChatAgentStep;
};

type SceneFlowUIMessage = UIMessage<ChatMessageMetadata, ChatMessageData>;

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
  return ["general", "script"].includes(config.purpose) && config.isEnabled && config.isVerified && config.modelSeries.trim();
}

function upsertAgentStep(current: ChatAgentStep[], next: ChatAgentStep) {
  return current.some((step) => step.id === next.id)
    ? current.map((step) => (step.id === next.id ? next : step))
    : [...current, next];
}

function uiMessageText(message: SceneFlowUIMessage) {
  return message.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");
}

function uiMessageReasoning(message: SceneFlowUIMessage) {
  return message.parts
    .filter((part) => part.type === "reasoning")
    .map((part) => part.text)
    .join("");
}

function toUiMessage(message: ChatMessage): SceneFlowUIMessage {
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

function toChatMessage(message: SceneFlowUIMessage, sessionId: string | null, config: UserConfig | undefined): ChatMessage {
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

function messageKey(messages: SceneFlowUIMessage[]) {
  return messages.map((message) => message.id).join("|");
}

function chatRequestBody(message: SceneFlowUIMessage | undefined, body: Record<string, unknown> | undefined) {
  return {
    content: message ? uiMessageText(message).trim() : "",
    attachments: message?.metadata?.attachments ?? [],
    configId: body?.configId,
    officialConfigId: body?.officialConfigId,
  };
}

export function useChatController(configs: UserConfig[], officialConfigs: UserConfig[]) {
  const { t } = useI18n();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const router = useRouter();
  const token = useUserStore((state) => state.token);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(() =>
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("chat")
  );
  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [input, setInput] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [agentSteps, setAgentSteps] = useState<ChatAgentStep[]>([]);
  const setRouteSessionId = useCallback((sessionId: string | null) => {
    const params = new URLSearchParams(window.location.search);
    if (sessionId) {
      params.set("chat", sessionId);
    } else {
      params.delete("chat");
    }
    const query = params.toString();
    router.replace(`${pathname}${query ? `?${query}` : ""}${window.location.hash}`, { scroll: false });
  }, [pathname, router]);

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
  const transport = useMemo(
    () =>
      new DefaultChatTransport<SceneFlowUIMessage>({
        api: "/api/bff/chat/sessions/_/messages/stream",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        prepareSendMessagesRequest: ({ messages, body, headers }) => {
          const sessionId = typeof body?.sessionId === "string" ? body.sessionId : "_";
          return {
            api: `/api/bff/chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`,
            headers,
            body: chatRequestBody(messages.at(-1), body),
          };
        },
      }),
    [token]
  );
  const chat = useChat<SceneFlowUIMessage>({
    id: effectiveSessionId ?? "new-chat",
    messages: serverMessages,
    transport,
    onData: (part) => {
      if (part.type === "data-agent_step") {
        setAgentSteps((current) => upsertAgentStep(current, part.data));
      }
    },
    onError: (error) => {
      setErrorMessage(resolveRequestError(error, t("chat.sendFailed")));
    },
  });
  const {
    messages: aiMessages,
    sendMessage: sendAiMessage,
    setMessages: setAiMessages,
    status: chatStatus,
  } = chat;
  const isStreaming = chatStatus === "submitted" || chatStatus === "streaming";
  const chatMessageKey = useMemo(() => messageKey(aiMessages), [aiMessages]);

  useEffect(() => {
    if (!selectedSessionId && !sessionsQuery.data) {
      return;
    }
    setRouteSessionId(effectiveSessionId);
  }, [effectiveSessionId, selectedSessionId, sessionsQuery.data, setRouteSessionId]);

  useEffect(() => {
    if (chatStatus === "ready" && serverMessageKey !== chatMessageKey && serverMessages.length >= aiMessages.length) {
      setAiMessages(serverMessages);
    }
  }, [aiMessages.length, chatMessageKey, chatStatus, serverMessageKey, serverMessages, setAiMessages]);

  const createSessionMutation = useMutation({
    mutationFn: createChatSessionAction,
    onSuccess: async (response) => {
      setSelectedSessionId(response.session.id);
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions });
    },
    onError: (error) => {
      setErrorMessage(resolveRequestError(error, t("chat.createSessionFailed")));
    },
  });

  const deleteSessionMutation = useMutation({
    mutationFn: deleteChatSessionAction,
    onSuccess: async (_, deletedId) => {
      if (effectiveSessionId === deletedId) {
        setSelectedSessionId(sessionsQuery.data?.sessions.find((session) => session.id !== deletedId)?.id ?? null);
      }
      setAgentSteps([]);
      setErrorMessage(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chatMessages(deletedId) }),
      ]);
    },
    onError: (error) => {
      setErrorMessage(resolveRequestError(error, t("chat.deleteSessionFailed")));
    },
  });

  const isBusy = createSessionMutation.isPending || deleteSessionMutation.isPending || isStreaming;

  const createSession = () => {
    createSessionMutation.mutate({
      title: input.trim().slice(0, 40) || t("chat.newSession"),
      ...selectedConfigPayload(selectedConfig),
    });
  };

  const selectSession = (id: string) => {
    setSelectedSessionId(id);
    setAgentSteps([]);
  };

  const deleteSession = (id: string) => {
    if (isStreaming) {
      return;
    }
    deleteSessionMutation.mutate(id);
  };

  const streamToSession = async (sessionId: string, content: string, attachments: ChatAttachment[] = []) => {
    if (!selectedConfig) {
      return;
    }

    setErrorMessage(null);
    setAgentSteps([]);
    await sendAiMessage(
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
  };

  const sendMessage = async (nextContent?: string, attachments: ChatAttachment[] = []) => {
    const content = (nextContent ?? input).trim();
    if ((!content && attachments.length === 0) || isBusy || !selectedConfig) {
      return;
    }
    if (!effectiveSessionId) {
      try {
        const response = await createChatSessionAction({
          title: content.slice(0, 40) || attachments[0]?.name?.slice(0, 40) || t("chat.newSession"),
          ...selectedConfigPayload(selectedConfig),
        });
        await queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions });
        await streamToSession(response.session.id, content, attachments);
        setSelectedSessionId(response.session.id);
      } catch (error) {
        setErrorMessage(resolveRequestError(error, t("chat.createSessionFailed")));
      }
      return;
    }

    try {
      await streamToSession(effectiveSessionId, content, attachments);
    } catch (error) {
      setErrorMessage(resolveRequestError(error, t("chat.sendFailed")));
    }
  };

  return {
    chatConfigs,
    effectiveConfigId,
    effectiveSessionId,
    selectedConfig,
    sessions: sessionsQuery.data?.sessions ?? [],
    sessionsLoading: sessionsQuery.isLoading,
    messages: aiMessages.map((message) => toChatMessage(message, effectiveSessionId, selectedConfig)),
    agentSteps,
    messagesLoading: messagesQuery.isLoading,
    input,
    setInput,
    errorMessage,
    isBusy,
    isStreaming,
    createSession,
    selectSession,
    deleteSession,
    sendMessage,
    setSelectedConfigId,
  };
}
