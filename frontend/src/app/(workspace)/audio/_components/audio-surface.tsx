"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/actions/query-keys";
import { listUserConfigsAction } from "@/actions/settings-actions";

import { VoiceGenerationPanel } from "./voice-generation-panel";

/**
 * Content of the `/audio` menu. Mounted by the workspace keep-alive host rather than by
 * `audio/page.tsx`, so an in-flight voice design survives switching to another menu and back.
 */
export function AudioSurface({ active }: { active: boolean }) {
  const configsQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
    staleTime: 30_000,
  });

  return (
    <VoiceGenerationPanel
      active={active}
      configs={configsQuery.data?.configs ?? []}
      officialConfigs={configsQuery.data?.officialConfigs ?? []}
    />
  );
}
