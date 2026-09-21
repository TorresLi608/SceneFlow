"use client";

import { History } from "lucide-react";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { configName } from "@/lib/config-format";
import { useI18n } from "@/lib/i18n";
import type { UserConfig } from "@/types/auth";

import { AssistantComposer } from "./assistant-composer";
import { ChatMessageList } from "./chat-message-list";
import { ChatSidebar } from "./chat-sidebar";
import { useChatController } from "./use-chat-controller";

interface ChatPanelProps {
  configs: UserConfig[];
  officialConfigs: UserConfig[];
  formatDateTime: (value: Date | string | number) => string;
}

export function ChatPanel({ configs, officialConfigs, formatDateTime }: ChatPanelProps) {
  const { t } = useI18n();
  const chat = useChatController(configs, officialConfigs);
  const [historyOpen, setHistoryOpen] = useState(false);
  const lastMessage = chat.messages.at(-1);
  const autoScrollKey = `${chat.effectiveSessionId ?? "new-chat"}:${chat.messages.length}:${lastMessage?.id ?? ""}`;
  const isEmpty = chat.messages.length === 0 && !chat.messagesLoading;

  const handleRegenerate = useCallback(() => {
    if (chat.isBusy || chat.isStreaming) {
      return;
    }
    const lastUserMessage = [...chat.messages].reverse().find((m) => m.role === "user");
    if (!lastUserMessage) {
      return;
    }
    void chat.sendMessage(lastUserMessage.content, lastUserMessage.attachments);
  }, [chat]);

  const suggestions = [
    { text: t("chat.suggestion1"), prompt: "构思一部微短剧大纲，包含主角人设、核心冲突与前三集悬念反转。" },
    { text: t("chat.suggestion2"), prompt: "设定一名悬疑短剧主角的视觉概念特征，并描述开场关键分镜画面。" },
    { text: t("chat.suggestion3"), prompt: "检索今天有哪些实时热点资讯与最新发生的重要事件？" },
    { text: t("chat.suggestion4"), prompt: "帮我起草一份微短剧项目的策划案框架，包括题材定位、受众分析与拍摄预算。" },
  ];

  const sidebar = (
    <ChatSidebar
      chatConfigs={chat.chatConfigs}
      effectiveConfigId={chat.effectiveConfigId}
      effectiveSessionId={chat.effectiveSessionId}
      sessions={chat.sessions}
      sessionsLoading={chat.sessionsLoading}
      sessionRetentionDays={chat.sessionRetentionDays}
      isBusy={chat.isBusy}
      formatDateTime={formatDateTime}
      onConfigChange={chat.setSelectedConfigId}
      onCreateSession={() => {
        chat.createSession();
        setHistoryOpen(false);
      }}
      onDeleteSession={chat.deleteSession}
      onSelectSession={(id) => {
        chat.selectSession(id);
        setHistoryOpen(false);
      }}
    />
  );

  return (
    <div className="grid min-h-0 min-w-0 flex-1 grid-cols-1 gap-0 bg-background md:grid-cols-[292px_minmax(0,1fr)]">
      <div className="hidden min-h-0 md:flex">{sidebar}</div>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex shrink-0 items-center gap-3 border-b border-border/60 px-3 py-2 sm:px-5 sm:py-3.5 bg-background/80 backdrop-blur-xs">
          <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
            <DialogTrigger render={<Button variant="outline" size="sm" className="shrink-0 md:hidden" />}>
              <History data-icon="inline-start" />
              {t("chat.history")}
            </DialogTrigger>
            <DialogContent className="h-[min(40rem,calc(100dvh-2rem))] max-w-sm gap-0 p-0" aria-describedby={undefined}>
              <DialogTitle className="sr-only">{t("chat.history")}</DialogTitle>
              {sidebar}
            </DialogContent>
          </Dialog>
          <div className="min-w-0 flex items-center gap-2">
            <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
            <h2 className="truncate text-sm font-medium text-foreground">
              {chat.selectedConfig ? configName(chat.selectedConfig, t) : t("chat.selectModelToStart")}
            </h2>
          </div>
        </div>

        {isEmpty ? (
          <div className="flex flex-1 flex-col items-center justify-center px-4 pb-[12vh]">
            <div className="mx-auto flex w-full max-w-3xl flex-col items-stretch gap-6">
              <div className="text-center space-y-2">
                <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-foreground selection:bg-primary/20">
                  {t("chat.welcomeTitle")}
                </h1>
              </div>

              <div className="w-full">
                <AssistantComposer
                  sessionId={chat.effectiveSessionId}
                  messages={chat.messages}
                  sendDisabled={!chat.selectedConfig || chat.isBusy}
                  isRunning={chat.isStreaming}
                  showDisclaimer={false}
                  onSend={chat.sendMessage}
                  onStop={chat.stop}
                />
              </div>

              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                {suggestions.map((item, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => void chat.sendMessage(item.prompt)}
                    disabled={!chat.selectedConfig || chat.isBusy}
                    className="flex flex-col gap-1 rounded-2xl border border-border/70 bg-card/60 p-3.5 text-left text-xs text-muted-foreground transition-all hover:bg-accent hover:text-foreground hover:border-foreground/20 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-40 disabled:pointer-events-none shadow-2xs cursor-pointer"
                  >
                    <span className="font-medium text-foreground line-clamp-1">{item.text}</span>
                    <span className="line-clamp-1 text-muted-foreground/80">{item.prompt}</span>
                  </button>
                ))}
              </div>

              <p className="text-center text-xs text-muted-foreground/75 select-none">
                {t("chat.disclaimer")}
              </p>
            </div>
          </div>
        ) : (
          <>
            <ChatMessageList
              key={chat.effectiveSessionId ?? "new-chat"}
              autoScrollKey={autoScrollKey}
              messages={chat.messages}
              agentSteps={chat.agentSteps}
              isLoading={chat.messagesLoading}
              isStreaming={chat.isStreaming}
              onRegenerate={handleRegenerate}
            />

            <div className="mx-auto w-full max-w-3xl shrink-0 px-3 pb-3 sm:px-4 sm:pb-5">
              {chat.errorMessage ? <p className="mb-2 text-center text-sm text-amber-600">{chat.errorMessage}</p> : null}

              <AssistantComposer
                sessionId={chat.effectiveSessionId}
                messages={chat.messages}
                sendDisabled={!chat.selectedConfig || chat.isBusy}
                isRunning={chat.isStreaming}
                onSend={chat.sendMessage}
                onStop={chat.stop}
              />
            </div>
          </>
        )}
      </section>
    </div>
  );
}

