"use client";

import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ChatAgentStep, ChatMessage } from "@/types/chat";

interface ChatMessageListProps {
  messages: ChatMessage[];
  agentSteps: ChatAgentStep[];
  isLoading: boolean;
}

function StepIcon({ status }: { status: ChatAgentStep["status"] }) {
  if (status === "done") {
    return <CheckCircle2 className="size-3.5 text-emerald-600" />;
  }
  if (status === "error") {
    return <XCircle className="size-3.5 text-destructive" />;
  }
  return <Loader2 className="size-3.5 animate-spin text-muted-foreground" />;
}

export function ChatMessageList({ messages, agentSteps, isLoading }: ChatMessageListProps) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-5 overflow-y-auto px-4 py-6">
      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-12 w-4/5 rounded-2xl" />
          <Skeleton className="ml-auto h-12 w-3/5 rounded-2xl" />
        </div>
      ) : null}

      {!isLoading && messages.length === 0 ? (
        <div className="flex flex-1 items-center justify-center py-20 text-center">
          <p className="text-sm text-muted-foreground">暂无消息，直接提问即可。</p>
        </div>
      ) : null}

      {messages.map((message) => (
        <div
          key={message.id}
          className={cn(
            "max-w-[86%] text-sm leading-7 whitespace-pre-wrap",
            message.role === "user"
              ? "ml-auto rounded-2xl bg-muted px-4 py-2.5"
              : "mr-auto w-full max-w-full text-foreground"
          )}
        >
          {message.reasoning ? (
            <details className="mb-3 rounded-xl bg-muted/60 px-3 py-2 text-xs">
              <summary className="cursor-pointer opacity-80">模型思考</summary>
              <div className="mt-1 opacity-80">{message.reasoning}</div>
            </details>
          ) : null}
          {message.content}
        </div>
      ))}

      {agentSteps.length > 0 ? (
        <div className="mr-auto w-full max-w-full rounded-xl border border-border/70 bg-muted/30 px-3 py-2 text-xs">
          <p className="mb-2 font-medium text-foreground">执行流程</p>
          <div className="space-y-1.5">
            {agentSteps.map((step) => (
              <div key={step.id} className="flex items-start gap-2 text-muted-foreground">
                <span className="mt-0.5">
                  <StepIcon status={step.status} />
                </span>
                <div className="min-w-0">
                  <p className="text-foreground">{step.label}</p>
                  {step.detail ? <p className="truncate">{step.detail}</p> : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
