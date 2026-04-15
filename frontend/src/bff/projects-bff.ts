import type {
  GenerateProjectInput,
  GenerateProjectResponse,
  GenerateVideoInput,
  GenerateVideoResponse,
  OptimizeProjectInput,
  OptimizeProjectResponse,
  ParseProjectInput,
  ParseProjectResponse,
} from "@/types/project";
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
  const response = await backendClient.post<ParseProjectResponse>(`/api/projects/${projectID}/parse`, payload, {
    headers: {
      Authorization: authorization,
    },
  });

  return response.data;
}

export async function generateProjectByBff(
  projectID: string,
  payload: GenerateProjectInput,
  authorization?: string
) {
  const response = await backendClient.post<GenerateProjectResponse>(
    `/api/projects/${projectID}/generate`,
    payload,
    {
      headers: {
        Authorization: authorization,
      },
    }
  );

  return response.data;
}

export async function optimizeProjectByBff(
  projectID: string,
  payload: OptimizeProjectInput,
  authorization?: string
) {
  const response = await backendClient.post<OptimizeProjectResponse>(
    `/api/projects/${projectID}/optimize`,
    payload,
    {
      headers: {
        Authorization: authorization,
      },
    }
  );

  return response.data;
}

export async function generateVideoByBff(
  projectID: string,
  payload: GenerateVideoInput,
  authorization?: string
) {
  const response = await backendClient.post<GenerateVideoResponse>(
    `/api/projects/${projectID}/generate-video`,
    payload,
    {
      headers: {
        Authorization: authorization,
      },
    }
  );

  return response.data;
}

export async function deleteProjectByBff(projectID: string, authorization?: string) {
  await backendClient.delete(`/api/projects/${projectID}`, {
    headers: {
      Authorization: authorization,
    },
  });
}
