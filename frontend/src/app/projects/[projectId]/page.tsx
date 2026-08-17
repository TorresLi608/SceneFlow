import { redirect } from "next/navigation";

/** The workbench opens on project info; the sections live under the `(workbench)` shell. */
export default async function ProjectPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  redirect(`/projects/${projectId}/info`);
}
