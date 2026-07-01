"use client";

import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { UserConfig } from "@/types/auth";
import { configName } from "./chat-format";
import { ChatMessageList } from "./chat-message-list";
import { ChatSidebar } from "./chat-sidebar";
import { useChatController } from "./use-chat-controller";

interface ChatPanelProps {
  configs: UserConfig[];
  formatDateTime: (value: Date | string | number) => string;
}

export function ChatPanel({ configs, formatDateTime }: ChatPanelProps) {
  const chat = useChatController(configs);

  return (
    <div className="grid flex-1 gap-4 p-4 md:grid-cols-[280px_minmax(0,1fr)] md:p-6">
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
        onSelectSession={chat.selectSession}
      />

      <Card className="min-h-[640px] border-border/80">
        <CardHeader>
          <CardTitle className="text-base">
            {chat.selectedConfig ? configName(chat.selectedConfig) : "选择模型开始对话"}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex min-h-[560px] flex-col gap-3">
          <ChatMessageList messages={chat.messages} isLoading={chat.messagesLoading} />

          {chat.errorMessage ? <p className="text-sm text-amber-600">{chat.errorMessage}</p> : null}

          <div className="flex gap-2">
            <Textarea
              value={chat.input}
              onChange={(event) => chat.setInput(event.target.value)}
              placeholder="输入问题..."
              className="min-h-20"
              disabled={!chat.selectedConfig || chat.isBusy}
            />
            <Button
              className="h-20 px-4"
              onClick={chat.sendMessage}
              disabled={!chat.input.trim() || !chat.selectedConfig || chat.isBusy}
            >
              <Send className="size-4" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
