"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/actions/query-keys";
import { listUserConfigsAction } from "@/actions/settings-actions";
import { useI18n } from "@/lib/i18n";

import { ChatPanel } from "./_components/chat-panel";

export default function ChatPage() {
  const { formatDateTime } = useI18n();
  const configsQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
    staleTime: 30_000,
  });

  return (
    <ChatPanel
      configs={configsQuery.data?.configs ?? []}
      officialConfigs={configsQuery.data?.officialConfigs ?? []}
      formatDateTime={formatDateTime}
    />
  );
}
