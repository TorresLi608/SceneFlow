import type { ParseProjectInput, ParseProjectResponse } from "@/types/project";
import { backendClient } from "@/lib/http/backend-client";
import { createTemplateProjects } from "@/lib/project-factory";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function getProjectTemplatesByBff() {
	await sleep(600);

	return {
		projects: createTemplateProjects(),
	};
}

export async function parseProjectByBff(
	projectID: string,
	payload: ParseProjectInput,
	authorization?: string
) {
	const response = await backendClient.post<ParseProjectResponse>(
		`/api/projects/${projectID}/parse`,
		payload,
		{
			headers: {
				Authorization: authorization,
			},
		}
	);

	return response.data;
}
