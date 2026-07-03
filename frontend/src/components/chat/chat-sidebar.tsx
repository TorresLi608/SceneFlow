"use client";

import { MessageSquarePlus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { UserConfig } from "@/types/auth";
import type { ChatSession } from "@/types/chat";
import { configName } from "./chat-format";

interface ChatSidebarProps {
  chatConfigs: UserConfig[];
  effectiveConfigId: string;
  effectiveSessionId: string | null;
  sessions: ChatSession[];
  sessionsLoading: boolean;
  isBusy: boolean;
  formatDateTime: (value: Date | string | number) => string;
  onConfigChange: (value: string) => void;
  onCreateSession: () => void;
  onDeleteSession: (id: string) => void;
  onSelectSession: (id: string) => void;
}

export function ChatSidebar({
  chatConfigs,
  effectiveConfigId,
  effectiveSessionId,
  sessions,
  sessionsLoading,
  isBusy,
  formatDateTime,
  onConfigChange,
  onCreateSession,
  onDeleteSession,
  onSelectSession,
}: ChatSidebarProps) {
  const selectedConfig = chatConfigs.find((config) => `${config.source}:${config.id}` === effectiveConfigId);

  return (
    <aside className="min-h-0 overflow-y-auto border-b border-border/60 bg-muted/20 p-4 md:border-r md:border-b-0">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">智能问答</h2>
        <Button size="icon" variant="outline" onClick={onCreateSession} disabled={isBusy || chatConfigs.length === 0}>
          <MessageSquarePlus className="size-4" />
        </Button>
      </div>

      <div className="mt-4 space-y-3">
        <Select value={effectiveConfigId} onValueChange={(value) => onConfigChange(value ?? "")}>
          <SelectTrigger>
            <SelectValue placeholder="选择模型">{selectedConfig ? configName(selectedConfig) : undefined}</SelectValue>
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false}>
            {chatConfigs.map((config) => (
              <SelectItem key={`${config.source}:${config.id}`} value={`${config.source}:${config.id}`}>
                {configName(config)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {chatConfigs.length === 0 ? (
          <p className="text-sm text-amber-600">请先使用官方配置，或在设置里保存并校验一个文本模型。</p>
        ) : null}

        <div className="space-y-2">
          {sessionsLoading ? <Skeleton className="h-12 w-full" /> : null}
          {sessions.map((session) => (
            <div
              key={session.id}
              className={cn(
                "group flex w-full items-start gap-2 rounded-md border px-3 py-2 text-left text-sm transition",
                effectiveSessionId === session.id ? "border-border bg-background" : "border-transparent hover:bg-background/80"
              )}
            >
              <button type="button" onClick={() => onSelectSession(session.id)} className="min-w-0 flex-1 text-left">
                <span className="block truncate font-medium">{session.title}</span>
                <span className="mt-1 block text-xs text-muted-foreground">{formatDateTime(session.updatedAt)}</span>
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onDeleteSession(session.id);
                }}
                className="mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 transition hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus:opacity-100"
                aria-label="删除对话"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
