"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  createChatSessionAction,
  listChatMessagesAction,
  listChatSessionsAction,
  streamChatMessageAction,
} from "@/actions/chat-actions";
import { queryKeys } from "@/actions/query-keys";
import { resolveRequestError } from "@/lib/http/errors";
import type { UserConfig } from "@/types/auth";
import type { ChatAgentStep, ChatMessage } from "@/types/chat";

function configSelectValue(config: UserConfig) {
  return `${config.source}:${config.id}`;
}

function selectedConfigPayload(config: UserConfig | undefined) {
  if (!config) {
    return {};
  }
  return config.source === "official" ? { officialConfigId: config.id } : { configId: config.id };
}

export function useChatController(configs: UserConfig[], officialConfigs: UserConfig[]) {
  const queryClient = useQueryClient();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [input, setInput] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [streamMessages, setStreamMessages] = useState<ChatMessage[] | null>(null);
  const [agentSteps, setAgentSteps] = useState<ChatAgentStep[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const userChatConfigs = useMemo(
    () => configs.filter((config) => config.purpose === "script" && config.isVerified && config.modelSeries.trim()),
    [configs]
  );
  const officialChatConfigs = useMemo(
    () => officialConfigs.filter((config) => config.purpose === "script" && config.isVerified && config.modelSeries.trim()),
    [officialConfigs]
  );
  const chatConfigs = useMemo(() => [...officialChatConfigs, ...userChatConfigs], [officialChatConfigs, userChatConfigs]);
  const defaultConfigId = useMemo(
    () => {
      const config =
        userChatConfigs.find((item) => item.isActive) ??
        officialChatConfigs.find((item) => item.isActive) ??
        userChatConfigs[0] ??
        officialChatConfigs[0];
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

  const createSessionMutation = useMutation({
    mutationFn: createChatSessionAction,
    onSuccess: async (response) => {
      setSelectedSessionId(response.session.id);
      setStreamMessages(null);
      setErrorMessage(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions });
    },
    onError: (error) => {
      setErrorMessage(resolveRequestError(error, "新建对话失败"));
    },
  });

  const effectiveConfigId = selectedConfigId || defaultConfigId;
  const selectedConfig = chatConfigs.find((config) => configSelectValue(config) === effectiveConfigId);
  const messages = messagesQuery.data?.messages ?? [];
  const isBusy = createSessionMutation.isPending || isStreaming;

  const createSession = () => {
    createSessionMutation.mutate({
      title: input.trim().slice(0, 40) || "新对话",
      ...selectedConfigPayload(selectedConfig),
    });
  };

  const selectSession = (id: string) => {
    setSelectedSessionId(id);
    setStreamMessages(null);
    setAgentSteps([]);
  };

  const streamToSession = async (sessionId: string, content: string) => {
    if (!selectedConfig) {
      return;
    }
    const assistantId = `stream-${Date.now()}`;
    setIsStreaming(true);
    setErrorMessage(null);
    setAgentSteps([]);
    setStreamMessages(messages);
    try {
      await streamChatMessageAction(sessionId, { content, ...selectedConfigPayload(selectedConfig) }, (event) => {
        if (event.type === "error") {
          throw new Error(event.error);
        }
        if (event.type === "agent_step") {
          setAgentSteps((current) => {
            const existing = current.find((step) => step.id === event.step.id);
            return existing
              ? current.map((step) => (step.id === event.step.id ? event.step : step))
              : [...current, event.step];
          });
          return;
        }
        if (event.type === "userMessage") {
          setStreamMessages((current) => [...(current ?? messages), event.message]);
          return;
        }
        if (event.type === "reasoning_delta" || event.type === "content_delta") {
          setStreamMessages((current) => {
            const list = current ?? messages;
            const existing = list.find((message) => message.id === assistantId);
            const patch =
              event.type === "reasoning_delta"
                ? { reasoning: (existing?.reasoning ?? "") + event.content }
                : { content: (existing?.content ?? "") + event.content };
            if (existing) {
              return list.map((message) => (message.id === assistantId ? { ...message, ...patch } : message));
            }
            return [
              ...list,
              {
                id: assistantId,
                sessionId,
                role: "assistant",
                content: patch.content ?? "",
                reasoning: patch.reasoning ?? "",
                provider: selectedConfig.provider,
                model: selectedConfig.modelSeries,
                createdAt: new Date().toISOString(),
              },
            ];
          });
          return;
        }
        if (event.type === "assistantMessage") {
          setStreamMessages((current) => {
            const list = current ?? messages;
            return list.some((message) => message.id === assistantId)
              ? list.map((message) => (message.id === assistantId ? event.message : message))
              : [...list, event.message];
          });
        }
      });
      setInput("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chatMessages(sessionId) }),
      ]);
    } catch (error) {
      setErrorMessage(resolveRequestError(error, "发送失败，请检查模型配置"));
    } finally {
      setIsStreaming(false);
    }
  };

  const sendMessage = async (nextContent?: string) => {
    const content = (nextContent ?? input).trim();
    if (!content || isBusy || !selectedConfig) {
      return;
    }
    if (!effectiveSessionId) {
      try {
        const response = await createChatSessionAction({
          title: content.slice(0, 40),
          ...selectedConfigPayload(selectedConfig),
        });
        setSelectedSessionId(response.session.id);
        await queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions });
        await streamToSession(response.session.id, content);
      } catch (error) {
        setErrorMessage(resolveRequestError(error, "新建对话失败"));
      }
      return;
    }
    await streamToSession(effectiveSessionId, content);
  };

  return {
    chatConfigs,
    effectiveConfigId,
    effectiveSessionId,
    selectedConfig,
    sessions: sessionsQuery.data?.sessions ?? [],
    sessionsLoading: sessionsQuery.isLoading,
    messages: streamMessages ?? messages,
    agentSteps,
    messagesLoading: messagesQuery.isLoading,
    input,
    setInput,
    errorMessage,
    isBusy,
    createSession,
    selectSession,
    sendMessage,
    setSelectedConfigId,
  };
}
