"use client";

import { useParams } from "next/navigation";

import { WorkbenchEditor } from "@/components/workbench/workbench-editor";

export default function ProjectEditorPage() {
  const params = useParams<{ projectId: string }>();

  return <WorkbenchEditor projectId={params.projectId} />;
}
