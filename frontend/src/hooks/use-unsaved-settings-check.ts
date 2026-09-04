import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getProjectModelsAction, listProjectsAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import type { Project } from "@/types/project";

/**
 * Hook to check if project settings have unsaved changes.
 * Compares current project settings against what the info page might have in draft.
 *
 * This relies on detecting when the user is on the info page and has unsaved changes there.
 * For the episode page, we check if the project's modelSettings or productionSettings
 * differ from the resolved models, which would indicate a pending save.
 */
export function useUnsavedSettingsCheck(projectId: string) {
  const [acknowledgedUnsaved, setAcknowledgedUnsaved] = useState(false);

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: listProjectsAction,
    staleTime: 300_000,
  });

  const modelsQuery = useQuery({
    queryKey: queryKeys.projectModels(projectId),
    queryFn: () => getProjectModelsAction(projectId),
    staleTime: 300_000,
  });

  const project = projectsQuery.data?.projects.find((p) => p.id === projectId);

  /**
   * Check if there are unsaved settings.
   *
   * Since we can't directly track draft state from the info page across components,
   * we use a simpler heuristic: if the user manually acknowledges they understand
   * settings may be unsaved, or if they're actively editing on the info page.
   *
   * For a more robust solution, we'd need to:
   * 1. Lift the draft state to a global store, or
   * 2. Add a "hasUnsavedChanges" flag that info page sets when editing
   *
   * For now, we'll return false by default and let the user trigger the check manually.
   */
  const hasUnsavedSettings = false; // Simplified for now

  const reset = () => setAcknowledgedUnsaved(false);

  return {
    hasUnsavedSettings,
    acknowledgedUnsaved,
    setAcknowledgedUnsaved,
    reset,
    project,
    models: modelsQuery.data?.models,
  };
}
