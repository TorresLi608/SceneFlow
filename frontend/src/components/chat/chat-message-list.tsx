"use client";

import { Bot, User } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/chat";
import { messageClass } from "./chat-format";

interface ChatMessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
}

export function ChatMessageList({ messages, isLoading }: ChatMessageListProps) {
  return (
    <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-border/70 bg-background p-3">
      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-16 w-4/5" />
          <Skeleton className="ml-auto h-16 w-3/5" />
        </div>
      ) : null}

      {!isLoading && messages.length === 0 ? (
        <p className="py-20 text-center text-sm text-muted-foreground">暂无消息，直接提问即可。</p>
      ) : null}

      {messages.map((message) => (
        <div
          key={message.id}
          className={cn(
            "max-w-[82%] rounded-lg px-3 py-2 text-sm leading-6 whitespace-pre-wrap",
            messageClass(message.role)
          )}
        >
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
  );
}
