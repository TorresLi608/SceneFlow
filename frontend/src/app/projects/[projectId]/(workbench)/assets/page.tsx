"use client";

import { useParams } from "next/navigation";
import { ProjectAssetManager } from "../../_components/project-asset-manager";

export default function ProjectAssetsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  return <ProjectAssetManager projectId={projectId} />;
}
