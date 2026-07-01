"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, MessageSquarePlus, Send, User } from "lucide-react";
import { useMemo, useState } from "react";

import {
  createChatSessionAction,
  listChatMessagesAction,
  listChatSessionsAction,
  streamChatMessageAction,
} from "@/actions/chat-actions";
import { queryKeys } from "@/actions/query-keys";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequestError } from "@/lib/http/errors";
import { cn } from "@/lib/utils";
import type { UserConfig } from "@/types/auth";
import type { ChatMessage } from "@/types/chat";

interface ChatPanelProps {
  configs: UserConfig[];
  formatDateTime: (value: Date | string | number) => string;
}

const providerLabelMap: Record<string, string> = {
  qwen: "Qwen",
  deepseek: "DeepSeek",
  doubao: "Doubao",
  openai: "OpenAI",
};

function configName(config: UserConfig) {
  return config.name?.trim() || `${providerLabelMap[config.provider] ?? config.provider} · ${config.modelSeries}`;
}

function messageClass(role: ChatMessage["role"]) {
  return role === "user" ? "ml-auto bg-primary text-primary-foreground" : "mr-auto bg-muted text-foreground";
}

export function ChatPanel({ configs, formatDateTime }: ChatPanelProps) {
  const queryClient = useQueryClient();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedConfigId, setSelectedConfigId] = useState<string>("");
  const [input, setInput] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [streamMessages, setStreamMessages] = useState<ChatMessage[] | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  const chatConfigs = useMemo(
    () => configs.filter((config) => config.purpose === "script" && config.isVerified && config.modelSeries.trim()),
    [configs]
  );

  const defaultConfigId = useMemo(
    () => String((chatConfigs.find((config) => config.isActive) ?? chatConfigs[0])?.id ?? ""),
    [chatConfigs]
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
  const selectedConfig = chatConfigs.find((config) => String(config.id) === effectiveConfigId);
  const messages = messagesQuery.data?.messages ?? [];
  const displayMessages = streamMessages ?? messages;
  const isBusy = createSessionMutation.isPending || isStreaming;

  const createSession = () => {
    createSessionMutation.mutate({
      title: input.trim().slice(0, 40) || "新对话",
      configId: selectedConfig ? selectedConfig.id : undefined,
    });
  };

  const streamToSession = async (sessionId: string, content: string) => {
    if (!selectedConfig) {
      return;
    }
    const assistantId = `stream-${Date.now()}`;
    setIsStreaming(true);
    setErrorMessage(null);
    setStreamMessages(messages);
    try {
      await streamChatMessageAction(
        sessionId,
        { content, configId: selectedConfig.id },
        (event) => {
          if (event.type === "error") {
            throw new Error(event.error);
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
        }
      );
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

  const sendMessage = async () => {
    const content = input.trim();
    if (!content || isBusy || !selectedConfig) {
      return;
    }

    if (!effectiveSessionId) {
      try {
        const response = await createChatSessionAction({
          title: content.slice(0, 40),
          configId: selectedConfig.id,
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

  return (
    <div className="grid flex-1 gap-4 p-4 md:grid-cols-[280px_minmax(0,1fr)] md:p-6">
      <Card className="min-h-[360px] border-border/80">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            智能问答
            <Button size="icon" variant="outline" onClick={createSession} disabled={isBusy || !selectedConfig}>
              <MessageSquarePlus className="size-4" />
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Select value={effectiveConfigId} onValueChange={(value) => setSelectedConfigId(value ?? "")}>
            <SelectTrigger>
              <SelectValue placeholder="选择模型" />
            </SelectTrigger>
            <SelectContent>
              {chatConfigs.map((config) => (
                <SelectItem key={config.id} value={String(config.id)}>
                  {configName(config)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {chatConfigs.length === 0 ? (
            <p className="text-sm text-amber-600">请先在设置里保存并校验一个剧本/提示词模型。</p>
          ) : null}

          <div className="space-y-2">
            {sessionsQuery.isLoading ? <Skeleton className="h-12 w-full" /> : null}
            {(sessionsQuery.data?.sessions ?? []).map((session) => (
              <button
                key={session.id}
                type="button"
                onClick={() => {
                  setSelectedSessionId(session.id);
                  setStreamMessages(null);
                }}
                className={cn(
                  "w-full rounded-md border px-3 py-2 text-left text-sm transition",
                  effectiveSessionId === session.id ? "border-primary/40 bg-primary/10" : "border-border/70 hover:bg-muted"
                )}
              >
                <p className="truncate font-medium">{session.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(session.updatedAt)}</p>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="min-h-[640px] border-border/80">
        <CardHeader>
          <CardTitle className="text-base">{selectedConfig ? configName(selectedConfig) : "选择模型开始对话"}</CardTitle>
        </CardHeader>
        <CardContent className="flex min-h-[560px] flex-col gap-3">
          <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-border/70 bg-background p-3">
            {messagesQuery.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-16 w-4/5" />
                <Skeleton className="ml-auto h-16 w-3/5" />
              </div>
            ) : null}

            {!messagesQuery.isLoading && displayMessages.length === 0 ? (
              <p className="py-20 text-center text-sm text-muted-foreground">暂无消息，直接提问即可。</p>
            ) : null}

            {displayMessages.map((message) => (
              <div key={message.id} className={cn("max-w-[82%] rounded-lg px-3 py-2 text-sm leading-6 whitespace-pre-wrap", messageClass(message.role))}>
                <div className="mb-1 flex items-center gap-1 text-xs opacity-80">
                  {message.role === "user" ? <User className="size-3" /> : <Bot className="size-3" />}
                  {message.role === "user" ? "你" : message.model || "Assistant"}
                </div>
                {message.reasoning ? (
                  <details className="mb-2 rounded-md bg-background/30 px-2 py-1 text-xs">
                    <summary className="cursor-pointer opacity-80">模型思考</summary>
                    <div className="mt-1 opacity-80">{message.reasoning}</div>
                  </details>
                ) : null}
                {message.content}
              </div>
            ))}
          </div>

          {errorMessage ? <p className="text-sm text-amber-600">{errorMessage}</p> : null}

          <div className="flex gap-2">
            <Textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="输入问题..."
              className="min-h-20"
              disabled={!selectedConfig || isBusy}
            />
            <Button className="h-20 px-4" onClick={sendMessage} disabled={!input.trim() || !selectedConfig || isBusy}>
              <Send className="size-4" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
