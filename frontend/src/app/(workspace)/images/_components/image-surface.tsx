"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/actions/query-keys";
import { listUserConfigsAction } from "@/actions/settings-actions";

import { ImageGenerationPanel } from "./image-generation-panel";

/**
 * Content of the `/images` menu. Mounted by the workspace keep-alive host rather than by
 * `images/page.tsx`, so an in-flight generation survives switching to another menu and back.
 */
export function ImageSurface({ active }: { active: boolean }) {
  const configsQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
    staleTime: 30_000,
  });

  return (
    <ImageGenerationPanel
      active={active}
      configs={configsQuery.data?.configs ?? []}
      officialConfigs={configsQuery.data?.officialConfigs ?? []}
    />
  );
}
