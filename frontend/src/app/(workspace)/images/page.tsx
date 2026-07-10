"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/actions/query-keys";
import { listUserConfigsAction } from "@/actions/settings-actions";

import { ImageGenerationPanel } from "./_components/image-generation-panel";

export default function ImagesPage() {
  const configsQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
    staleTime: 30_000,
  });

  return (
    <ImageGenerationPanel
      configs={configsQuery.data?.configs ?? []}
      officialConfigs={configsQuery.data?.officialConfigs ?? []}
    />
  );
}
