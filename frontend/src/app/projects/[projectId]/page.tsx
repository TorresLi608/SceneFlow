"use client";

import { useParams } from "next/navigation";

import { WorkbenchEditor } from "./_components/workbench-editor";

export default function ProjectEditorPage() {
  const params = useParams<{ projectId: string }>();

  return <WorkbenchEditor projectId={params.projectId} />;
}
