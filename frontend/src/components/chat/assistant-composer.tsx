"use client";

import {
  AuiProvider,
  ComposerPrimitive,
  ExternalThread,
  ThreadPrimitive,
  useAui,
  type AppendMessage,
  type ExternalThreadMessage,
} from "@assistant-ui/react";
import { Send } from "lucide-react";
import { useCallback, useMemo } from "react";

import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/chat";

interface AssistantComposerProps {
  messages: ChatMessage[];
  disabled: boolean;
  isRunning: boolean;
  onSend: (content: string) => Promise<void>;
}

function appendMessageText(message: AppendMessage) {
  return message.content
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("")
    .trim();
}

function toAssistantMessage(message: ChatMessage, isLastRunning: boolean): ExternalThreadMessage {
  const createdAt = new Date(message.createdAt);

  if (message.role === "user") {
    return {
      id: message.id,
      role: "user",
      content: [{ type: "text", text: message.content }],
      attachments: [],
      createdAt,
      metadata: { custom: {} },
    };
  }

  return {
    id: message.id,
    role: "assistant",
    content: [
      ...(message.reasoning ? [{ type: "reasoning" as const, text: message.reasoning }] : []),
      { type: "text", text: message.content },
    ],
    createdAt,
    status: isLastRunning ? { type: "running" } : { type: "complete", reason: "stop" },
    metadata: {
      unstable_state: null,
      unstable_annotations: [],
      unstable_data: [],
      steps: [],
      custom: {
        provider: message.provider,
        model: message.model,
      },
    },
  };
}

export function AssistantComposer({ messages, disabled, isRunning, onSend }: AssistantComposerProps) {
  const assistantMessages = useMemo(
    () =>
      messages.map((message, index) =>
        toAssistantMessage(message, isRunning && index === messages.length - 1 && message.role === "assistant")
      ),
    [isRunning, messages]
  );

  const handleNew = useCallback(
    async (message: AppendMessage) => {
      const content = appendMessageText(message);
      if (content) {
        await onSend(content);
      }
    },
    [onSend]
  );

  const aui = useAui({
    thread: ExternalThread({
      messages: assistantMessages,
      isRunning,
      isSendDisabled: disabled,
      onNew: handleNew,
    }),
  });

  return (
    <AuiProvider value={aui}>
      <ThreadPrimitive.ViewportProvider>
        <ComposerPrimitive.Root className="flex min-h-16 items-end gap-2 rounded-2xl border border-border/70 bg-background px-3 py-3 shadow-sm">
          <ComposerPrimitive.Input
            submitMode="enter"
            disabled={disabled}
            placeholder="输入问题..."
            className="max-h-40 min-h-10 flex-1 resize-none bg-transparent py-2 text-sm leading-6 outline-none placeholder:text-muted-foreground"
          />
          <ComposerPrimitive.Send
            className={cn(
              "inline-flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground transition hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground"
            )}
            aria-label="发送"
          >
            <Send className="size-4" />
          </ComposerPrimitive.Send>
        </ComposerPrimitive.Root>
      </ThreadPrimitive.ViewportProvider>
    </AuiProvider>
  );
}
