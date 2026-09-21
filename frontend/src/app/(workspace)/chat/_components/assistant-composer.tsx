"use client";

import {
  type AppendMessage,
  type AttachmentAdapter,
  type CompleteAttachment,
  type ExternalThreadMessage,
  type PendingAttachment,
  AssistantRuntimeProvider,
  AttachmentPrimitive,
  AuiIf,
  ComposerPrimitive,
  ThreadPrimitive,
  useAuiEvent,
  useExternalStoreRuntime,
} from "@assistant-ui/react";
import { ArrowUp, Plus, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { ChatAttachment, ChatAttachmentPart, ChatMessage } from "@/types/chat";

interface AssistantComposerProps {
  sessionId: string | null;
  messages: ChatMessage[];
  sendDisabled: boolean;
  isRunning: boolean;
  placeholder?: string;
  showDisclaimer?: boolean;
  onSend: (content: string, attachments?: ChatAttachment[]) => Promise<void>;
  onStop: () => void;
}

const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const TEXT_FILE_EXTENSIONS = new Set([
  ".txt",
  ".md",
  ".markdown",
  ".csv",
  ".tsv",
  ".json",
  ".jsonl",
  ".xml",
  ".html",
  ".htm",
  ".css",
  ".scss",
  ".sass",
  ".less",
  ".js",
  ".jsx",
  ".ts",
  ".tsx",
  ".mjs",
  ".cjs",
  ".py",
  ".java",
  ".go",
  ".rs",
  ".php",
  ".rb",
  ".swift",
  ".kt",
  ".kts",
  ".c",
  ".cc",
  ".cpp",
  ".h",
  ".hpp",
  ".cs",
  ".sh",
  ".bash",
  ".zsh",
  ".fish",
  ".sql",
  ".yaml",
  ".yml",
  ".toml",
  ".ini",
  ".env",
  ".log",
]);

function assertAttachmentSize(file: File, message: string) {
  if (file.size > MAX_ATTACHMENT_BYTES) {
    throw new Error(message);
  }
}

function attachmentId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function fileExtension(file: File) {
  const name = file.name.toLowerCase();
  return name.includes(".") ? `.${name.split(".").pop()}` : "";
}

function isTextFile(file: File) {
  return file.type.startsWith("text/") || ["application/json", "application/xml", "application/javascript"].includes(file.type) || TEXT_FILE_EXTENSIONS.has(fileExtension(file));
}

function attachmentType(file: File) {
  if (file.type.startsWith("image/")) {
    return "image";
  }
  return isTextFile(file) || [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt"].includes(fileExtension(file))
    ? "document"
    : "file";
}

function readFileAsDataUrl(file: File, errorMessage: string) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error ?? new Error(errorMessage));
    reader.readAsDataURL(file);
  });
}

function readFileText(file: File, errorMessage: string) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error ?? new Error(errorMessage));
    reader.readAsText(file);
  });
}

class ChatAttachmentAdapter implements AttachmentAdapter {
  constructor(private readonly messages: { tooLarge: string; readFailed: string }) {}

  accept = "*";

  async add(state: { file: File }): Promise<PendingAttachment> {
    assertAttachmentSize(state.file, this.messages.tooLarge);
    return {
      id: attachmentId(),
      type: attachmentType(state.file),
      name: state.file.name,
      contentType: state.file.type || "application/octet-stream",
      file: state.file,
      status: { type: "requires-action", reason: "composer-send" },
    };
  }

  async send(attachment: PendingAttachment): Promise<CompleteAttachment> {
    const { file } = attachment;
    if (file.type.startsWith("image/")) {
      return {
        ...attachment,
        status: { type: "complete" },
        content: [{ type: "image", image: await readFileAsDataUrl(file, this.messages.readFailed), filename: file.name }],
      };
    }

    if (isTextFile(file)) {
      const text = await readFileText(file, this.messages.readFailed);
      return {
        ...attachment,
        status: { type: "complete" },
        content: [{ type: "text", text: `<attachment name=${JSON.stringify(file.name)}>\n${text}\n</attachment>` }],
      };
    }

    return {
      ...attachment,
      status: { type: "complete" },
      content: [
        {
          type: "file",
          data: await readFileAsDataUrl(file, this.messages.readFailed),
          mimeType: file.type || "application/octet-stream",
          filename: file.name,
        },
      ],
    };
  }

  async remove(): Promise<void> {
    return;
  }
}

function appendMessageText(message: AppendMessage) {
  return message.content
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("")
    .trim();
}

function toChatPart(part: CompleteAttachment["content"][number], fallbackName: string): ChatAttachmentPart | null {
  if (part.type === "text") {
    return { type: "text", text: part.text };
  }
  if (part.type === "image") {
    return { type: "image", image: part.image, filename: part.filename ?? fallbackName };
  }
  if (part.type === "file") {
    return {
      type: "file",
      data: part.data,
      mimeType: part.mimeType,
      filename: part.filename ?? fallbackName,
    };
  }
  return null;
}

function toChatAttachments(attachments: readonly CompleteAttachment[] | undefined): ChatAttachment[] {
  return (attachments ?? [])
    .map((attachment) => ({
      id: attachment.id,
      type: attachment.type,
      name: attachment.name,
      contentType: attachment.contentType,
      content: attachment.content
        .map((part) => toChatPart(part, attachment.name))
        .filter((part): part is ChatAttachmentPart => part !== null),
    }))
    .filter((attachment) => attachment.content.length > 0);
}

function toAssistantAttachments(attachments: ChatAttachment[]): CompleteAttachment[] {
  return attachments.map((attachment) => ({
    id: attachment.id,
    type: attachment.type,
    name: attachment.name,
    contentType: attachment.contentType,
    content: attachment.content,
    status: { type: "complete" },
  }));
}

function toAssistantMessage(message: ChatMessage, isLastRunning: boolean): ExternalThreadMessage {
  const createdAt = new Date(message.createdAt);

  if (message.role === "user") {
    return {
      id: message.id,
      role: "user",
      content: [{ type: "text", text: message.content }],
      attachments: toAssistantAttachments(message.attachments),
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

function ComposerAttachment() {
  const { t } = useI18n();

  return (
    <AttachmentPrimitive.Root className="group inline-flex h-10 max-w-[220px] min-w-0 items-center gap-2 rounded-xl border border-border/70 bg-muted/45 p-1 pr-1.5 text-xs">
      <AttachmentPrimitive.unstable_Thumb className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-background text-[10px] text-muted-foreground" />
      <span className="min-w-0 flex-1 truncate">
        <AttachmentPrimitive.Name />
      </span>
      <AttachmentPrimitive.Remove className="inline-flex size-6 shrink-0 items-center justify-center rounded-full text-muted-foreground hover:bg-background hover:text-foreground" aria-label={t("chat.removeAttachment")}>
        <X className="size-3.5" />
      </AttachmentPrimitive.Remove>
    </AttachmentPrimitive.Root>
  );
}

function AttachmentError({ onError }: { onError: (message: string) => void }) {
  const { t } = useI18n();

  useAuiEvent("composer.attachmentAddError", ({ reason, message }) => {
    onError(reason === "not-accepted" ? t("chat.attachmentNotAccepted") : message || t("chat.attachmentUploadFailed"));
  });
  return null;
}

export function AssistantComposer({
  sessionId,
  messages,
  sendDisabled,
  isRunning,
  placeholder,
  showDisclaimer = true,
  onSend,
  onStop,
}: AssistantComposerProps) {
  const { t } = useI18n();
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const attachmentAdapter = useMemo<AttachmentAdapter>(
    () => new ChatAttachmentAdapter({ tooLarge: t("chat.attachmentTooLarge"), readFailed: t("chat.readAttachmentFailed") }),
    [t]
  );
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
      const attachments = toChatAttachments(message.attachments);
      if (content || attachments.length) {
        setAttachmentError(null);
        inputRef.current?.focus({ preventScroll: true });
        await onSend(content, attachments);
      }
    },
    [onSend]
  );

  useEffect(() => {
    requestAnimationFrame(() => inputRef.current?.focus({ preventScroll: true }));
  }, [sessionId]);

  const runtime = useExternalStoreRuntime({
    messages: assistantMessages,
    isSendDisabled: sendDisabled,
    isRunning,
    onNew: handleNew,
    adapters: {
      attachments: attachmentAdapter,
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.ViewportProvider>
        <AttachmentError onError={setAttachmentError} />
        <div className="w-full">
          <ComposerPrimitive.Root className="group/composer flex w-full flex-col rounded-[28px] border border-border/80 bg-background px-3 py-2 shadow-xs transition-all focus-within:border-foreground/30 focus-within:shadow-md dark:border-white/10 dark:bg-[#212121] dark:focus-within:border-white/20">
            <ComposerPrimitive.AttachmentDropzone className="flex flex-col gap-1.5 rounded-[22px] data-[dragging]:bg-muted/45">
              <AuiIf condition={({ composer }) => composer.attachments.length > 0}>
                <div className="flex flex-wrap gap-2 px-1 pt-1 pb-1.5">
                  <ComposerPrimitive.Attachments>{() => <ComposerAttachment />}</ComposerPrimitive.Attachments>
                </div>
              </AuiIf>
              <div className="flex items-end gap-1.5">
                <ComposerPrimitive.AddAttachment
                  multiple
                  className="flex size-9 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground active:scale-95 disabled:pointer-events-none disabled:opacity-40 cursor-pointer"
                  aria-label={t("chat.addAttachment")}
                >
                  <Plus className="size-5" />
                </ComposerPrimitive.AddAttachment>
                <ComposerPrimitive.Input
                  ref={inputRef}
                  autoFocus
                  submitMode="enter"
                  placeholder={placeholder || t("chat.inputPlaceholder")}
                  className="max-h-52 min-h-9 min-w-0 flex-1 resize-none bg-transparent py-1.5 pr-2 pl-1 text-base leading-6 text-foreground outline-none placeholder:text-muted-foreground md:text-sm"
                />
                <div className="flex shrink-0 items-center pb-0.5">
                  {isRunning ? (
                    <button
                      type="button"
                      onClick={onStop}
                      className="group relative flex size-9 items-center justify-center rounded-full bg-foreground text-background shadow-xs transition-transform hover:scale-105 active:scale-95 cursor-pointer dark:bg-white dark:text-black"
                      aria-label={t("common.stopGeneration")}
                      title={t("common.stopGeneration")}
                    >
                      <div className="size-3 rounded-[2px] bg-current" />
                    </button>
                  ) : (
                    <ComposerPrimitive.Send
                      className={cn(
                        "flex size-9 items-center justify-center rounded-full bg-foreground text-background shadow-xs transition-all hover:opacity-90 hover:scale-105 active:scale-95 disabled:bg-muted disabled:text-muted-foreground/40 disabled:scale-100 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer dark:bg-white dark:text-black dark:disabled:bg-white/10 dark:disabled:text-white/30"
                      )}
                      aria-label={t("chat.send")}
                    >
                      <ArrowUp className="size-5" />
                    </ComposerPrimitive.Send>
                  )}
                </div>
              </div>
            </ComposerPrimitive.AttachmentDropzone>
          </ComposerPrimitive.Root>
          {showDisclaimer ? (
            <p className="mt-2 text-center text-xs text-muted-foreground/75 select-none">
              {t("chat.disclaimer")}
            </p>
          ) : null}
          {attachmentError ? <p className="mt-2 text-center text-sm text-amber-600">{attachmentError}</p> : null}
        </div>
      </ThreadPrimitive.ViewportProvider>
    </AssistantRuntimeProvider>
  );
}

