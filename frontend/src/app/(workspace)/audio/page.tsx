"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/actions/query-keys";
import { listUserConfigsAction } from "@/actions/settings-actions";

import { AudioGenerationPanel } from "./_components/audio-generation-panel";

export default function AudioPage() {
  const configsQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
    staleTime: 30_000,
  });

  return (
    <AudioGenerationPanel
      configs={configsQuery.data?.configs ?? []}
      officialConfigs={configsQuery.data?.officialConfigs ?? []}
    />
  );
}
