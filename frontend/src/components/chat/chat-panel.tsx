"use client";

import type { UserConfig } from "@/types/auth";
import { AssistantComposer } from "./assistant-composer";
import { configName } from "./chat-format";
import { ChatMessageList } from "./chat-message-list";
import { ChatSidebar } from "./chat-sidebar";
import { useChatController } from "./use-chat-controller";

interface ChatPanelProps {
  configs: UserConfig[];
  officialConfigs: UserConfig[];
  formatDateTime: (value: Date | string | number) => string;
}

export function ChatPanel({ configs, officialConfigs, formatDateTime }: ChatPanelProps) {
  const chat = useChatController(configs, officialConfigs);

  return (
    <div className="grid min-h-0 flex-1 gap-0 bg-background md:grid-cols-[292px_minmax(0,1fr)]">
      <ChatSidebar
        chatConfigs={chat.chatConfigs}
        effectiveConfigId={chat.effectiveConfigId}
        effectiveSessionId={chat.effectiveSessionId}
        sessions={chat.sessions}
        sessionsLoading={chat.sessionsLoading}
        isBusy={chat.isBusy}
        formatDateTime={formatDateTime}
        onConfigChange={chat.setSelectedConfigId}
        onCreateSession={chat.createSession}
        onDeleteSession={chat.deleteSession}
        onSelectSession={chat.selectSession}
      />

      <section className="flex min-h-0 min-w-0 flex-col">
        <div className="border-b border-border/60 px-5 py-4">
          <h2 className="truncate text-sm font-medium">
            {chat.selectedConfig ? configName(chat.selectedConfig) : "选择模型开始对话"}
          </h2>
        </div>

        <ChatMessageList
          messages={chat.messages}
          agentSteps={chat.agentSteps}
          isLoading={chat.messagesLoading}
        />

        <div className="mx-auto w-full max-w-3xl px-4 pb-5">
          {chat.errorMessage ? <p className="text-sm text-amber-600">{chat.errorMessage}</p> : null}

          <AssistantComposer
            messages={chat.messages}
            disabled={!chat.selectedConfig || chat.isBusy}
            isRunning={chat.isBusy}
            onSend={chat.sendMessage}
          />
        </div>
      </section>
    </div>
  );
}
