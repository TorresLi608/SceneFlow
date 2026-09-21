"use client";

import { TextMessagePartProvider } from "@assistant-ui/react";
import { StreamdownTextPrimitive, type ControlsConfig } from "@assistant-ui/react-streamdown";
import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import {
  Bot,
  Check,
  ChevronDown,
  Clock,
  Copy,
  FileText,
  Globe,
  ImageIcon,
  RotateCcw,
  Sparkles,
  Square,
  XCircle,
} from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent, type WheelEvent } from "react";

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
  onRegenerate?: () => void;
}

function StepKindIcon({ label, className }: { label: string; className?: string }) {
  if (label.includes("搜索") || label.includes("web") || label.includes("Search")) {
    return <Globe className={className} />;
  }
  if (label.includes("历史") || label.includes("上下文") || label.includes("Context")) {
    return <Clock className={className} />;
  }
  if (label.includes("图片") || label.includes("视觉") || label.includes("Image")) {
    return <ImageIcon className={className} />;
  }
  if (label.includes("文档") || label.includes("PDF") || label.includes("Word")) {
    return <FileText className={className} />;
  }
  if (label.includes("分析") || label.includes("思考") || label.includes("意图") || label.includes("Intent")) {
    return <Sparkles className={className} />;
  }
  return <Bot className={className} />;
}

function formatStepLabel(
  step: ChatAgentStep,
  t: (key: string, params?: Record<string, string | number>) => string,
  locale: string
): string {
  if (locale !== "en") return step.label;

  const id = (step.id || "").toLowerCase();
  const label = step.label || "";

  if (id === "load_context" || label.includes("加载历史") || label.includes("上下文")) {
    return t("chat.stepLoadContext");
  }
  if (id === "compress_context" || label.includes("长期记忆") || label.includes("压缩")) {
    return t("chat.stepCompressContext");
  }
  if (id === "agent_analyze" || label.includes("意图分析")) {
    return t("chat.stepIntentAnalysis");
  }
  if (id === "agent_generate" || label.includes("生成回复") || label.includes("组织回答")) {
    return t("chat.stepGenerateResponse");
  }
  if (id === "save_message" || label.includes("保存回复")) {
    return t("chat.stepSaveMessage");
  }
  if (id === "runtime_error" || label.includes("失败")) {
    return t("chat.stepRuntimeError");
  }
  if (label.includes("搜索") || id.includes("web_search")) {
    return t("chat.stepWebSearch");
  }
  if (label.includes("网页") || id.includes("fetch_web_content")) {
    return t("chat.stepFetchWebContent");
  }
  if (label.includes("图片") || id.includes("generate_image")) {
    return t("chat.stepGenerateImage");
  }
  if (label.includes("PDF") || id.includes("generate_pdf")) {
    return t("chat.stepGeneratePdf");
  }
  if (label.includes("Word") || id.includes("generate_word")) {
    return t("chat.stepGenerateWord");
  }
  if (label.includes("日志") || id.includes("error_log")) {
    return t("chat.stepSearchErrorLogs");
  }

  return step.label;
}

function formatStepDetail(detail: string | undefined, locale: string): string {
  if (!detail || locale !== "en") return detail || "";

  // 模型 xxx -> Model xxx
  const modelMatch = detail.match(/^模型\s*(.+)$/);
  if (modelMatch) return `Model ${modelMatch[1]}`;

  // x 条历史，约 y tokens -> x history messages, ~y tokens
  const historyMatch = detail.match(/^(\d+)\s*条历史[，,\s]*约\s*(\d+)\s*tokens?$/);
  if (historyMatch) return `${historyMatch[1]} history messages, ~${historyMatch[2]} tokens`;

  // 检索「xxx」 -> Searching "xxx"
  const searchMatch = detail.match(/^检索[「"“](.+?)[」"”]$/);
  if (searchMatch) return `Searching "${searchMatch[1]}"`;

  // 抓取「xxx」 -> Fetching "xxx"
  const fetchMatch = detail.match(/^抓取[「"“](.+?)[」"”]$/);
  if (fetchMatch) return `Fetching "${fetchMatch[1]}"`;

  // 提示词「xxx」 -> Prompt: "xxx"
  const promptMatch = detail.match(/^提示词[「"“](.+?)[」"”]$/);
  if (promptMatch) return `Prompt: "${promptMatch[1]}"`;

  // 文档「xxx」 -> Document: "xxx"
  const docMatch = detail.match(/^文档[「"“](.+?)[」"”]$/);
  if (docMatch) return `Document: "${docMatch[1]}"`;

  // 精选 x 条相关网页结果 -> x relevant search results
  const resultMatch = detail.match(/^精选\s*(\d+)\s*条相关网页结果$/);
  if (resultMatch) return `${resultMatch[1]} relevant search results`;

  // 提取完成，共 x 字符 -> Extracted x characters
  const extractMatch = detail.match(/^提取完成[，,\s]*共\s*(\d+)\s*字符$/);
  if (extractMatch) return `Extracted ${extractMatch[1]} characters`;

  // 上下文超过 x token 预算 -> Context exceeds x token budget
  const budgetMatch = detail.match(/^上下文超过\s*(\d+)\s*token\s*预算$/);
  if (budgetMatch) return `Context exceeds ${budgetMatch[1]} token budget`;

  // 保留最近 x 条明细消息 -> Retained latest x messages
  const retainMatch = detail.match(/^保留最近\s*(\d+)\s*条明细消息$/);
  if (retainMatch) return `Retained latest ${retainMatch[1]} messages`;

  // 固定短语
  const exactMap: Record<string, string> = {
    "分析完成": "Analysis completed",
    "分析完成，调用工具": "Analysis completed, calling tools",
    "正在生成回复内容": "Generating response content",
    "回复生成完成": "Response generation completed",
    "已写入 SQLite": "Saved to SQLite",
  };

  if (exactMap[detail]) {
    return exactMap[detail];
  }

  return detail;
}

function StepStatusBadge({ status }: { status: ChatAgentStep["status"] }) {
  if (status === "running") {
    return (
      <span className="relative flex size-3.5 shrink-0 items-center justify-center">
        <span className="absolute inline-flex size-3 animate-ping rounded-full bg-primary/40 opacity-75" />
        <span className="relative inline-flex size-2 rounded-full bg-primary" />
      </span>
    );
  }
  if (status === "done") {
    return (
      <span className="flex size-3.5 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400">
        <Check className="size-2.5 stroke-[2.5]" />
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="flex size-3.5 shrink-0 items-center justify-center rounded-full bg-destructive/15 text-destructive">
        <XCircle className="size-2.5" />
      </span>
    );
  }
  return (
    <span className="flex size-3.5 shrink-0 items-center justify-center rounded-full bg-muted-foreground/20 text-muted-foreground">
      <Square className="size-1.5 fill-current" />
    </span>
  );
}

function AgentExecutionFlow({ steps, isStreaming }: { steps: ChatAgentStep[]; isStreaming: boolean }) {
  const { t, locale } = useI18n();
  const [isOpen, setIsOpen] = useState(false);

  // 步骤去重：相同标签与详情的已完成步骤合并，避免由于模型并发调用导致冗余刷屏
  const uniqueSteps = useMemo(() => {
    const list: ChatAgentStep[] = [];
    const seen = new Set<string>();
    for (const step of steps) {
      const key = `${step.label}::${step.detail}::${step.status}`;
      if (step.status === "done" && seen.has(key)) {
        continue;
      }
      seen.add(key);
      list.push(step);
    }
    return list;
  }, [steps]);

  // 倒序寻找最新处于 running 的步骤；若全部完成则取最后一个步骤
  const runningStep = [...uniqueSteps].reverse().find((s) => s.status === "running");
  const activeStep = runningStep ?? uniqueSteps.at(-1);

  let summaryText = t("chat.agentSteps");
  const searchStep = uniqueSteps.find((s) => s.label.includes("搜索") || s.id.includes("search"));
  const hasSearch = Boolean(searchStep);

  const formattedRunningLabel = runningStep ? formatStepLabel(runningStep, t, locale) : "";
  const formattedRunningDetail = runningStep?.detail ? formatStepDetail(runningStep.detail, locale) : "";

  if (isStreaming) {
    if (runningStep) {
      if (
        runningStep.id === "agent_generate" ||
        runningStep.label.includes("回复") ||
        runningStep.label.includes("回答")
      ) {
        summaryText = t("chat.generatingResponse");
      } else {
        summaryText = formattedRunningDetail
          ? `${formattedRunningLabel}: ${formattedRunningDetail}`
          : `${formattedRunningLabel}...`;
      }
    } else {
      summaryText = t("chat.generatingResponse");
    }
  } else if (hasSearch && searchStep?.detail && (searchStep.detail.includes("条") || searchStep.detail.includes("results"))) {
    summaryText = formatStepDetail(searchStep.detail, locale);
  } else {
    const doneCount = uniqueSteps.filter((s) => s.status === "done").length;
    summaryText = t("chat.stepsCompleted", { count: doneCount });
  }

  const activeLabel = activeStep ? formatStepLabel(activeStep, t, locale) : "";

  return (
    <div className="mb-3 block max-w-full text-xs">
      <div
        className={cn(
          "overflow-hidden rounded-2xl border transition-all duration-200",
          isOpen
            ? "w-full border-border/80 bg-muted/20 shadow-xs backdrop-blur-sm dark:bg-white/[0.03] dark:border-white/10"
            : "border-border/60 bg-muted/30 hover:bg-muted/50 dark:bg-white/[0.04] dark:hover:bg-white/[0.07] dark:border-white/10"
        )}
      >
        <button
          type="button"
          onClick={() => setIsOpen((prev) => !prev)}
          className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left transition-colors cursor-pointer select-none"
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {isStreaming && runningStep ? (
              <span className="relative flex size-2 shrink-0">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
                <span className="relative inline-flex size-2 rounded-full bg-primary" />
              </span>
            ) : hasSearch ? (
              <Globe className="size-3.5 shrink-0 text-blue-500" />
            ) : (
              <StepKindIcon label={activeLabel} className="size-3.5 shrink-0 text-emerald-500" />
            )}
            <span className="truncate font-medium text-foreground text-xs">
              {summaryText}
            </span>
          </div>
          <div className="flex items-center gap-1 shrink-0 text-muted-foreground/70 text-[11px]">
            <span className="hidden sm:inline">{isOpen ? t("chat.collapseSteps") : t("chat.expandSteps")}</span>
            <ChevronDown className={cn("size-3.5 transition-transform duration-200", isOpen && "rotate-180")} />
          </div>
        </button>

        {isOpen ? (
          <div className="border-t border-border/50 px-4 py-3 bg-background/40 space-y-2.5">
            <div className="relative pl-5 space-y-3 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-px before:bg-border/60">
              {uniqueSteps.map((step) => {
                const label = formatStepLabel(step, t, locale);
                const detail = formatStepDetail(step.detail, locale);
                return (
                  <div key={step.id} className="relative flex items-start gap-2.5">
                    <span className="absolute -left-5 mt-0.5">
                      <StepStatusBadge status={step.status} />
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 font-medium text-foreground text-xs">
                        <StepKindIcon label={label} className="size-3.5 text-muted-foreground/80" />
                        <span>{label}</span>
                      </div>
                      {detail ? (
                        <p className="mt-0.5 text-[11px] text-muted-foreground font-mono truncate leading-relaxed">
                          {detail}
                        </p>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}


const streamdownPlugins = { code, cjk };
const streamdownControls = { code: { copy: true, download: false }, table: false, mermaid: false } as unknown as ControlsConfig;
const BOTTOM_THRESHOLD = 80;
const INITIAL_SCROLL_RETRY_DELAYS = [50, 150, 350];

import { ChatMarkdownImage } from "./chat-markdown-image";

const streamdownComponents = { img: ChatMarkdownImage };

/**
 * 清洗消息中可能由模型 Base64 幻觉手抄导致的重复或坏损图片 Markdown。
 * 当同一条消息包含相同标题的图片时，保留最后出现的合法签名版本。
 */
function sanitizeChatMessageContent(content: string): string {
  if (!content || !content.includes("![")) {
    return content;
  }
  const imgRegex = /!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g;
  const matches = [...content.matchAll(imgRegex)];
  if (matches.length <= 1) {
    return content;
  }

  const seenKeys = new Set<string>();
  const toRemoveIndices = new Set<number>();

  for (let i = matches.length - 1; i >= 0; i--) {
    const match = matches[i];
    const alt = match[1].trim();
    const url = match[2];
    const key = alt || url;
    if (seenKeys.has(key)) {
      toRemoveIndices.add(i);
    } else {
      seenKeys.add(key);
    }
  }

  if (toRemoveIndices.size === 0) {
    return content;
  }

  let result = content;
  for (let i = matches.length - 1; i >= 0; i--) {
    if (toRemoveIndices.has(i)) {
      result = result.replace(matches[i][0], "").replace(/\n{3,}/g, "\n\n").trim();
    }
  }
  return result;
}

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
  const codeText = codeBlock?.querySelector('[data-streamdown="code-block-body"]')?.textContent;
  if (!button || !codeText) {
    return;
  }

  copyWithFallback(codeText);
}

function MessageContent({ content, isRunning }: { content: string; isRunning: boolean }) {
  const sanitizedContent = sanitizeChatMessageContent(content);
  return (
    <div className="relative min-w-0 max-w-full">
      <TextMessagePartProvider text={sanitizedContent} isRunning={isRunning}>
        <StreamdownTextPrimitive
          caret={undefined}
          className={cn(isRunning && "chat-streaming-cursor")}
          components={streamdownComponents}
          containerClassName="min-w-0 max-w-full [overflow-wrap:anywhere]"
          containerProps={{ onClickCapture: handleCodeCopyCapture }}
          controls={streamdownControls}
          defer
          mode={isRunning ? "streaming" : "static"}
          plugins={streamdownPlugins}
          shikiTheme={["github-light", "github-dark"]}
        />
      </TextMessagePartProvider>
    </div>
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
          <div
            key={attachment.id}
            className="flex max-w-64 items-center gap-2 rounded-2xl border border-border/70 bg-background/80 p-1.5 text-xs shadow-2xs dark:bg-white/5"
          >
            {image ? (
              <Image src={image} alt="" width={40} height={40} unoptimized className="size-10 shrink-0 rounded-xl object-cover" />
            ) : (
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                {attachment.type === "image" ? <ImageIcon className="size-4" /> : <FileText className="size-4" />}
              </span>
            )}
            <span className="min-w-0 truncate pr-1">{attachment.name}</span>
          </div>
        );
      })}
    </div>
  );
}

function MessageActionBar({
  content,
  isAssistant,
  canRegenerate,
  onRegenerate,
}: {
  content: string;
  isAssistant: boolean;
  canRegenerate?: boolean;
  onRegenerate?: () => void;
}) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    copyWithFallback(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [content]);

  return (
    <div
      className={cn(
        "flex items-center gap-1 pt-1.5 text-muted-foreground transition-opacity",
        isAssistant
          ? "opacity-0 group-hover:opacity-100 focus-within:opacity-100"
          : "justify-end opacity-0 group-hover:opacity-100 focus-within:opacity-100"
      )}
    >
      <button
        type="button"
        onClick={handleCopy}
        className="flex size-7 items-center justify-center rounded-lg text-muted-foreground/80 transition-colors hover:bg-muted hover:text-foreground active:scale-95 cursor-pointer"
        title={copied ? t("chat.copied") : t("chat.copyMessage")}
        aria-label={copied ? t("chat.copied") : t("chat.copyMessage")}
      >
        {copied ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
      </button>
      {canRegenerate && onRegenerate ? (
        <button
          type="button"
          onClick={onRegenerate}
          className="flex size-7 items-center justify-center rounded-lg text-muted-foreground/80 transition-colors hover:bg-muted hover:text-foreground active:scale-95 cursor-pointer"
          title={t("chat.regenerate")}
          aria-label={t("chat.regenerate")}
        >
          <RotateCcw className="size-3.5" />
        </button>
      ) : null}
    </div>
  );
}

export function ChatMessageList({
  autoScrollKey,
  messages,
  agentSteps,
  isLoading,
  isStreaming,
  onRegenerate,
}: ChatMessageListProps) {
  const { t } = useI18n();
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const lastForcedScrollKeyRef = useRef("");
  const shouldFollowRef = useRef(true);
  const scrollFrameRef = useRef<number | null>(null);
  const forceTimerRefs = useRef<number[]>([]);
  const [showScrollButton, setShowScrollButton] = useState(false);

  const setScrollButton = useCallback((next: boolean) => {
    setShowScrollButton((current) => (current === next ? current : next));
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
        <div ref={contentRef} className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
          {isLoading ? (
            <div className="space-y-4">
              <Skeleton className="h-14 w-4/5 rounded-[22px]" />
              <Skeleton className="ml-auto h-12 w-3/5 rounded-[22px]" />
            </div>
          ) : null}

          {messages.map((message, index) => {
            const isLast = index === messages.length - 1;
            const isLastAssistant = message.role === "assistant" && isLast;

            return (
              <div
                key={message.id}
                className={cn(
                  "group relative min-w-0 text-sm leading-7",
                  message.role === "user"
                    ? "ml-auto flex w-full max-w-[85%] flex-col items-end sm:max-w-[72%]"
                    : "mr-auto w-full max-w-full text-foreground"
                )}
              >
                {message.role === "user" ? (
                  <>
                    <MessageAttachments attachments={message.attachments ?? []} />
                    <div className="rounded-[24px] bg-[#f4f4f4] px-4.5 py-3 text-[#0d0d0d] whitespace-pre-wrap dark:bg-[#2f2f2f] dark:text-[#ececec] shadow-2xs font-normal selection:bg-primary/20">
                      <MessageContent content={message.content} isRunning={false} />
                    </div>
                    <MessageActionBar content={message.content} isAssistant={false} />
                  </>
                ) : (
                  <>
                    {/* 执行流程（置顶展示于助手回答上方，参考 ChatGPT / Perplexity 设计） */}
                    {isLastAssistant && agentSteps.length > 0 ? (
                      <AgentExecutionFlow steps={agentSteps} isStreaming={isStreaming} />
                    ) : null}

                    {message.reasoning ? (
                      <details className="group/reasoning mb-3.5 rounded-2xl border border-border/50 bg-muted/30 px-3.5 py-2 text-xs transition-colors hover:bg-muted/50">
                        <summary className="flex cursor-pointer select-none items-center gap-1.5 font-medium text-muted-foreground list-none group-open/reasoning:text-foreground">
                          <Sparkles className="size-3.5 text-primary" />
                          <span>{t("chat.reasoning")}</span>
                          <ChevronDown className="ml-auto size-3.5 transition-transform group-open/reasoning:rotate-180" />
                        </summary>
                        <div className="mt-2 text-muted-foreground leading-relaxed whitespace-pre-wrap border-t border-border/40 pt-2 font-mono text-[11px] opacity-90">
                          {message.reasoning}
                        </div>
                      </details>
                    ) : null}
                    <MessageAttachments attachments={message.attachments ?? []} />
                    <div className="py-0.5">
                      <MessageContent
                        content={message.content}
                        isRunning={isStreaming && isLastAssistant}
                      />
                    </div>
                    <MessageActionBar
                      content={message.content}
                      isAssistant={true}
                      canRegenerate={isLastAssistant && !isStreaming}
                      onRegenerate={onRegenerate}
                    />
                  </>
                )}
              </div>
            );
          })}

          {/* 当等待首个助手消息内容下发且已有执行流程（如正在分析、搜索）时，优雅展示待答占位 */}
          {messages.at(-1)?.role !== "assistant" && agentSteps.length > 0 ? (
            <div className="mr-auto w-full max-w-full text-foreground text-sm leading-7">
              <AgentExecutionFlow steps={agentSteps} isStreaming={isStreaming} />
              {isStreaming ? (
                <div className="flex items-center py-1 px-0.5">
                  <span className="inline-block h-[1.15em] w-[2.5px] rounded-full bg-primary shadow-[0_0_10px_rgba(59,130,246,0.6)] animate-[chat-cursor-pulse_0.8s_ease-in-out_infinite_alternate]" />
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {showScrollButton ? (
        <button
          type="button"
          onClick={() => scrollToBottom()}
          aria-label={t("chat.scrollToBottom")}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 z-20 flex size-9 items-center justify-center rounded-full border border-border/80 bg-background/90 text-foreground shadow-md backdrop-blur-sm transition-all hover:bg-muted hover:scale-105 active:scale-95 focus-visible:outline-none cursor-pointer"
        >
          <ChevronDown className="size-4.5" />
        </button>
      ) : null}
    </div>
  );
}

