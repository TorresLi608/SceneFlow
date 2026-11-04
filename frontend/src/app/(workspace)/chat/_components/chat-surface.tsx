"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/actions/query-keys";
import { listUserConfigsAction } from "@/actions/settings-actions";
import { useI18n } from "@/lib/i18n";

import { ChatPanel } from "./chat-panel";

/**
 * Content of the `/chat` menu. Mounted by the workspace keep-alive host rather than by
 * `chat/page.tsx`, so a streaming answer survives switching to another menu and back.
 */
export function ChatSurface({ active }: { active: boolean }) {
  const { formatDateTime } = useI18n();
  const configsQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
    staleTime: 30_000,
  });

  return (
    <ChatPanel
      active={active}
      configs={configsQuery.data?.configs ?? []}
      officialConfigs={configsQuery.data?.officialConfigs ?? []}
      formatDateTime={formatDateTime}
    />
  );
}
