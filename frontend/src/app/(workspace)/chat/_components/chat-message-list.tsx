"use client";

import { TextMessagePartProvider } from "@assistant-ui/react";
import { StreamdownTextPrimitive, type ControlsConfig } from "@assistant-ui/react-streamdown";
import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { ArrowDown, CheckCircle2, FileText, ImageIcon, Loader2, Square, XCircle } from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useRef, useState, type MouseEvent, type WheelEvent } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { ChatAgentStep, ChatAttachment, ChatMessage } from "@/types/chat";

interface ChatMessageListProps {
  autoScrollKey: string;
  messages: ChatMessage[];
  agentSteps: ChatAgentStep[];
  isLoading: boolean;
  isStreaming: boolean;
}

function StepIcon({ status }: { status: ChatAgentStep["status"] }) {
  if (status === "done") {
    return <CheckCircle2 className="size-3.5 text-emerald-600" />;
  }
  if (status === "error") {
    return <XCircle className="size-3.5 text-destructive" />;
  }
  if (status === "stopped") {
    return <Square className="size-3.5 fill-current text-muted-foreground" />;
  }
  return <Loader2 className="size-3.5 animate-spin text-muted-foreground" />;
}

const streamdownPlugins = { code, cjk };
const streamdownControls = { code: { copy: true, download: false }, table: false, mermaid: false } as unknown as ControlsConfig;
const BOTTOM_THRESHOLD = 80;
const INITIAL_SCROLL_RETRY_DELAYS = [50, 150, 350];

function isNearBottom(element: HTMLDivElement) {
  return element.scrollHeight - element.scrollTop - element.clientHeight < BOTTOM_THRESHOLD;
}

function hasScrollableOverflow(element: HTMLDivElement) {
  return element.scrollHeight > element.clientHeight + BOTTOM_THRESHOLD;
}

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
              <Image src={image} alt="" width={40} height={40} unoptimized className="size-10 shrink-0 rounded-md object-cover" />
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

export function ChatMessageList({ autoScrollKey, messages, agentSteps, isLoading, isStreaming }: ChatMessageListProps) {
  const { t } = useI18n();
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const lastForcedScrollKeyRef = useRef("");
  const shouldFollowRef = useRef(true);
  const scrollFrameRef = useRef<number | null>(null);
  const forceTimerRefs = useRef<number[]>([]);
  const [showScrollButton, setShowScrollButton] = useState(false);

  const setScrollButton = useCallback((next: boolean) => {
    setShowScrollButton((current) => current === next ? current : next);
  }, []);

  const cancelScrollFrame = useCallback(() => {
    if (scrollFrameRef.current !== null) {
      cancelAnimationFrame(scrollFrameRef.current);
      scrollFrameRef.current = null;
    }
  }, []);

  const cancelAutoScroll = useCallback(() => {
    cancelScrollFrame();
    for (const timer of forceTimerRefs.current) {
      window.clearTimeout(timer);
    }
    forceTimerRefs.current = [];
  }, [cancelScrollFrame]);

  const updateScrollState = useCallback(() => {
    const element = scrollRef.current;
    if (!element) {
      return;
    }

    const atBottom = isNearBottom(element);
    if (atBottom) {
      shouldFollowRef.current = true;
    }
    setScrollButton(!atBottom && hasScrollableOverflow(element));
  }, [setScrollButton]);

  const scrollToBottomNow = useCallback((behavior: ScrollBehavior = "smooth", force = true) => {
    const element = scrollRef.current;
    if (!element) {
      return;
    }

    if (behavior === "smooth") {
      element.scrollTo({ top: element.scrollHeight, behavior });
    } else {
      element.scrollTop = element.scrollHeight;
    }
    if (force) {
      shouldFollowRef.current = true;
    }
    setScrollButton(false);
  }, [setScrollButton]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth", force = true) => {
    cancelAutoScroll();
    scrollToBottomNow(behavior, force);
  }, [cancelAutoScroll, scrollToBottomNow]);

  const scheduleScrollToBottom = useCallback((force = false) => {
    cancelScrollFrame();
    scrollFrameRef.current = requestAnimationFrame(() => {
      scrollFrameRef.current = null;
      if (force || shouldFollowRef.current) {
        scrollToBottomNow("auto", force);
      }
    });
  }, [cancelScrollFrame, scrollToBottomNow]);

  const forceScrollToBottom = useCallback(() => {
    cancelAutoScroll();
    shouldFollowRef.current = true;
    scrollToBottomNow("auto", true);
    scheduleScrollToBottom(true);
    forceTimerRefs.current = INITIAL_SCROLL_RETRY_DELAYS.map((delay) =>
      window.setTimeout(() => scrollToBottomNow("auto", true), delay)
    );
  }, [cancelAutoScroll, scheduleScrollToBottom, scrollToBottomNow]);

  const handleWheelCapture = useCallback((event: WheelEvent<HTMLDivElement>) => {
    if (event.deltaY < 0) {
      const element = scrollRef.current;
      shouldFollowRef.current = false;
      cancelAutoScroll();
      setScrollButton(Boolean(element && hasScrollableOverflow(element)));
    }
  }, [cancelAutoScroll, setScrollButton]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) {
      return;
    }

    element.addEventListener("scroll", updateScrollState, { passive: true });
    return () => {
      element.removeEventListener("scroll", updateScrollState);
    };
  }, [updateScrollState]);

  useEffect(() => {
    const content = contentRef.current;
    if (!content || typeof ResizeObserver === "undefined") {
      return;
    }

    const observer = new ResizeObserver(() => {
      if (shouldFollowRef.current) {
        scheduleScrollToBottom();
      }
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, [scheduleScrollToBottom]);

  useEffect(() => {
    if (shouldFollowRef.current) {
      scheduleScrollToBottom();
    }
    return cancelAutoScroll;
  }, [agentSteps, cancelAutoScroll, isLoading, isStreaming, messages, scheduleScrollToBottom]);

  useEffect(() => {
    if (isLoading || messages.length === 0 || lastForcedScrollKeyRef.current === autoScrollKey) {
      return;
    }

    lastForcedScrollKeyRef.current = autoScrollKey;
    const frame = requestAnimationFrame(forceScrollToBottom);
    return () => cancelAnimationFrame(frame);
  }, [autoScrollKey, forceScrollToBottom, isLoading, messages.length]);

  useEffect(() => {
    return cancelAutoScroll;
  }, [cancelAutoScroll]);

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={scrollRef} onWheelCapture={handleWheelCapture} className="chat-message-list-scrollbar h-full overflow-y-auto [overflow-anchor:none]">
        <div ref={contentRef} className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-6">
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-4/5 rounded-2xl" />
              <Skeleton className="ml-auto h-12 w-3/5 rounded-2xl" />
            </div>
          ) : null}

          {!isLoading && messages.length === 0 ? (
            <div className="flex flex-1 items-center justify-center py-20 text-center">
              <p className="text-sm text-muted-foreground">{t("chat.empty")}</p>
            </div>
          ) : null}

          {messages.map((message, index) => (
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
                  <summary className="cursor-pointer opacity-80">{t("chat.reasoning")}</summary>
                  <div className="mt-1 opacity-80">{message.reasoning}</div>
                </details>
              ) : null}
              <MessageAttachments attachments={message.attachments ?? []} />
              <MessageContent content={message.content} isRunning={isStreaming && message.role === "assistant" && index === messages.length - 1} />
            </div>
          ))}

          {agentSteps.length > 0 ? (
            <div className="mr-auto w-full max-w-full rounded-xl border border-border/70 bg-muted/30 px-3 py-2 text-xs">
              <p className="mb-2 font-medium text-foreground">{t("chat.agentSteps")}</p>
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
      {showScrollButton ? (
        <button
          type="button"
          onClick={() => scrollToBottom()}
          aria-label={t("chat.scrollToBottom")}
          className="absolute bottom-4 left-1/2 inline-flex size-10 -translate-x-1/2 items-center justify-center rounded-full border border-border bg-background/95 text-foreground shadow-lg backdrop-blur transition hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <ArrowDown className="size-5" />
        </button>
      ) : null}
    </div>
  );
}
