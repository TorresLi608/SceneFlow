"use client";

import type { MouseEvent } from "react";
import { TextMessagePartProvider } from "@assistant-ui/react";
import { StreamdownTextPrimitive, type ControlsConfig } from "@assistant-ui/react-streamdown";
import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { CheckCircle2, FileText, ImageIcon, Loader2, XCircle } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ChatAgentStep, ChatAttachment, ChatMessage } from "@/types/chat";

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

const streamdownPlugins = { code, cjk };
const streamdownControls = { code: { copy: true, download: false }, table: false, mermaid: false } as unknown as ControlsConfig;

function legacyCopy(text: string) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();
  try {
    document.execCommand("copy");
  } finally {
    textarea.remove();
  }
}

function copyWithFallback(text: string) {
  const writeText = navigator.clipboard?.writeText?.bind(navigator.clipboard);
  if (writeText) {
    void writeText(text).catch(() => legacyCopy(text));
    return;
  }

  legacyCopy(text);
}

function handleCodeCopyCapture(event: MouseEvent<HTMLDivElement>) {
  const button = (event.target as Element).closest('[data-streamdown="code-block-copy-button"]');
  const codeBlock = button?.closest('[data-streamdown="code-block"]');
  const code = codeBlock?.querySelector('[data-streamdown="code-block-body"]')?.textContent;
  if (!button || !code) {
    return;
  }

  copyWithFallback(code);
}

function MessageContent({ content, isRunning }: { content: string; isRunning: boolean }) {
  return (
    <TextMessagePartProvider text={content} isRunning={isRunning}>
      <StreamdownTextPrimitive
        caret={isRunning ? "block" : undefined}
        containerClassName="min-w-0"
        containerProps={{ onClickCapture: handleCodeCopyCapture }}
        controls={streamdownControls}
        defer
        mode={isRunning ? "streaming" : "static"}
        plugins={streamdownPlugins}
        shikiTheme={["github-light", "github-dark"]}
      />
    </TextMessagePartProvider>
  );
}

function attachmentImage(attachment: ChatAttachment) {
  return attachment.content.find((part) => part.type === "image")?.image ?? "";
}

function MessageAttachments({ attachments }: { attachments: ChatAttachment[] }) {
  if (attachments.length === 0) {
    return null;
  }

  return (
    <div className="mb-2 flex flex-wrap gap-2">
      {attachments.map((attachment) => {
        const image = attachmentImage(attachment);

        return (
          <div key={attachment.id} className="flex max-w-64 items-center gap-2 rounded-lg border border-border/70 bg-background/80 p-1.5 text-xs">
            {image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={image} alt="" className="size-10 shrink-0 rounded-md object-cover" />
            ) : (
              <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                {attachment.type === "image" ? <ImageIcon className="size-4" /> : <FileText className="size-4" />}
              </span>
            )}
            <span className="min-w-0 truncate">{attachment.name}</span>
          </div>
        );
      })}
    </div>
  );
}

export function ChatMessageList({ messages, agentSteps, isLoading }: ChatMessageListProps) {
  return (
    <div className="chat-message-list-scrollbar min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-6">
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
              "max-w-[86%] text-sm leading-7",
              message.role === "user"
                ? "ml-auto rounded-2xl bg-muted px-4 py-2.5 whitespace-pre-wrap"
                : "mr-auto w-full max-w-full text-foreground"
            )}
          >
            {message.reasoning ? (
              <details className="mb-3 rounded-xl bg-muted/60 px-3 py-2 text-xs">
                <summary className="cursor-pointer opacity-80">模型思考</summary>
                <div className="mt-1 opacity-80">{message.reasoning}</div>
              </details>
            ) : null}
            <MessageAttachments attachments={message.attachments ?? []} />
            <MessageContent content={message.content} isRunning={isLoading && message.role === "assistant"} />
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
    </div>
  );
}
