"use client";

import { useParams } from "next/navigation";

import { WorkbenchEditor } from "../_components/workbench-editor";

/**
 * The pre-refactor single-screen editor, kept reachable while the workbench sections are
 * built out section by section. `episodes/` links here until the episode editor replaces it.
 *
 * Deliberately outside the `(workbench)` route group: it ships its own full-screen chrome
 * and would render a second sidebar inside the shell.
 */
export default function ProjectWorkbenchPage() {
  const params = useParams<{ projectId: string }>();

  return <WorkbenchEditor projectId={params.projectId} />;
}
