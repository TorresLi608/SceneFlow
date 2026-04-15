import { httpClient } from "@/lib/http/client";
import type { ParseProjectInput, ParseProjectResponse, Project } from "@/types/project";

interface ProjectTemplatesResponse {
  projects: Project[];
}

export async function getProjectTemplatesAction() {
	const response = await httpClient.get<ProjectTemplatesResponse>("/api/bff/projects/templates");
	return response.data;
}

export async function parseProjectAction(projectID: string, payload: ParseProjectInput) {
	const response = await httpClient.post<ParseProjectResponse>(
		`/api/bff/projects/${projectID}/parse`,
		payload
	);
	return response.data;
}
