"use client";

import { MessageSquare, MessageSquarePlus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { configName } from "@/lib/config-format";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { UserConfig } from "@/types/auth";
import type { ChatSession } from "@/types/chat";

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
  const { t } = useI18n();
  const selectedConfig = chatConfigs.find(
    (config) => `${config.source}:${config.id}` === effectiveConfigId
  );

  return (
    <aside className="flex min-h-0 flex-col overflow-hidden border-b border-border/70 bg-card/40 p-4 backdrop-blur-xl md:border-r md:border-b-0 md:p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <MessageSquare className="size-4" />
          </div>
          <h2 className="text-sm font-bold tracking-tight text-foreground">
            {t("home.chat")}
          </h2>
        </div>
        <Button
          size="icon-sm"
          className="rounded-xl shadow-xs cursor-pointer"
          onClick={onCreateSession}
          disabled={isBusy || chatConfigs.length === 0}
        >
          <MessageSquarePlus className="size-4" />
        </Button>
      </div>

      <div className="mt-4 space-y-3">
        {/* 模型选择 */}
        <div className="space-y-1">
          <label className="text-[11px] font-semibold text-muted-foreground">推理模型</label>
          <Select
            value={effectiveConfigId}
            onValueChange={(value) => onConfigChange(value ?? "")}
          >
            <SelectTrigger className="h-9 text-xs">
              <SelectValue placeholder={t("chat.selectModel")}>
                {selectedConfig ? configName(selectedConfig, t) : undefined}
              </SelectValue>
            </SelectTrigger>
            <SelectContent alignItemWithTrigger={false}>
              {chatConfigs.map((config) => (
                <SelectItem
                  key={`${config.source}:${config.id}`}
                  value={`${config.source}:${config.id}`}
                  className="text-xs"
                >
                  {configName(config, t)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {chatConfigs.length === 0 ? (
          <p className="text-xs text-amber-500">{t("chat.noTextModel")}</p>
        ) : null}
      </div>

      {/* 会话列表 */}
      <div className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1 chat-message-list-scrollbar">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
            会话历史
          </span>
          <span className="text-[10px] text-muted-foreground">{sessions.length}</span>
        </div>

        <div className="space-y-1.5">
          {sessionsLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full rounded-xl" />
              <Skeleton className="h-12 w-full rounded-xl" />
            </div>
          ) : null}

          {sessions.map((session) => {
            const isActive = effectiveSessionId === session.id;
            return (
              <div
                key={session.id}
                className={cn(
                  "group relative flex w-full items-start gap-2 rounded-xl border p-2.5 text-left text-xs transition-all cursor-pointer",
                  isActive
                    ? "border-primary/50 bg-primary/10 text-primary shadow-xs dark:bg-primary/15"
                    : "border-border/60 bg-card/40 text-foreground hover:border-border hover:bg-card/80"
                )}
              >
                <button
                  type="button"
                  onClick={() => onSelectSession(session.id)}
                  className="min-w-0 flex-1 text-left cursor-pointer"
                >
                  <span className="block truncate font-semibold">
                    {session.title || "新会话"}
                  </span>
                  <span className="mt-1 block text-[10px] text-muted-foreground">
                    {formatDateTime(session.updatedAt)}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onDeleteSession(session.id);
                  }}
                  className="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-lg text-muted-foreground opacity-0 transition hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus:opacity-100 cursor-pointer"
                  aria-label={t("chat.deleteSession")}
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
