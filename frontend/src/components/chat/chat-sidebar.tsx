"use client";

import { MessageSquarePlus } from "lucide-react";

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
  onSelectSession,
}: ChatSidebarProps) {
  const selectedConfig = chatConfigs.find((config) => `${config.source}:${config.id}` === effectiveConfigId);

  return (
    <aside className="border-b border-border/60 bg-muted/20 p-4 md:min-h-[calc(100vh-65px)] md:border-r md:border-b-0">
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
            <button
              key={session.id}
              type="button"
              onClick={() => onSelectSession(session.id)}
              className={cn(
                "w-full rounded-md border px-3 py-2 text-left text-sm transition",
                effectiveSessionId === session.id ? "border-border bg-background" : "border-transparent hover:bg-background/80"
              )}
            >
              <p className="truncate font-medium">{session.title}</p>
              <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(session.updatedAt)}</p>
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
