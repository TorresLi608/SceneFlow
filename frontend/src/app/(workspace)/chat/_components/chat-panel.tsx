"use client";

import { History } from "lucide-react";
import { useState } from "react";

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

  const sidebar = (
    <ChatSidebar
        chatConfigs={chat.chatConfigs}
        effectiveConfigId={chat.effectiveConfigId}
        effectiveSessionId={chat.effectiveSessionId}
        sessions={chat.sessions}
        sessionsLoading={chat.sessionsLoading}
        isBusy={chat.isBusy}
        formatDateTime={formatDateTime}
        onConfigChange={chat.setSelectedConfigId}
        onCreateSession={() => { chat.createSession(); setHistoryOpen(false); }}
        onDeleteSession={chat.deleteSession}
        onSelectSession={(id) => { chat.selectSession(id); setHistoryOpen(false); }}
      />
  );

  return (
    <div className="grid min-h-0 min-w-0 flex-1 grid-cols-1 gap-0 bg-background md:grid-cols-[292px_minmax(0,1fr)]">
      <div className="hidden min-h-0 md:flex">{sidebar}</div>

      <section className="flex min-h-0 min-w-0 flex-col">
        <div className="flex shrink-0 items-center gap-3 border-b border-border/60 px-3 py-2 sm:px-5 sm:py-4">
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
          <h2 className="min-w-0 truncate text-sm font-medium">
            {chat.selectedConfig ? configName(chat.selectedConfig, t) : t("chat.selectModelToStart")}
          </h2>
        </div>

        <ChatMessageList
          key={chat.effectiveSessionId ?? "new-chat"}
          autoScrollKey={autoScrollKey}
          messages={chat.messages}
          agentSteps={chat.agentSteps}
          isLoading={chat.messagesLoading}
          isStreaming={chat.isStreaming}
        />

        <div className="mx-auto w-full max-w-3xl shrink-0 px-3 pb-3 sm:px-4 sm:pb-5">
          {chat.errorMessage ? <p className="text-sm text-amber-600">{chat.errorMessage}</p> : null}

          <AssistantComposer
            sessionId={chat.effectiveSessionId}
            messages={chat.messages}
            sendDisabled={!chat.selectedConfig || chat.isBusy}
            isRunning={chat.isStreaming}
            onSend={chat.sendMessage}
            onStop={chat.stop}
          />
        </div>
      </section>
    </div>
  );
}
