"use client";

import { useQuery } from "@tanstack/react-query";
import { listProjectResourcesAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { artifactBffUrl } from "@/lib/artifact-url";
import { useI18n } from "@/lib/i18n";
import { localizeResource } from "@/lib/project-resources";

export function useProjectResources(projectId: string, busy = false) {
  // ponytail: catalogue metadata is loaded once; add server paging when large series outgrow it.
  const { locale } = useI18n();
  const query = useQuery({
    queryKey: queryKeys.projectResources(projectId),
    queryFn: () => listProjectResourcesAction(projectId),
    refetchInterval: busy ? 3000 : false,
  });
  return { ...query, resources: (query.data?.resources ?? []).map((item) => ({ ...localizeResource(item, locale), url: artifactBffUrl(item.url) })) };
}
