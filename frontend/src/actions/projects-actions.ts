import { httpClient } from "@/lib/http/client";
import type {
  GenerateProjectInput,
  GenerateProjectResponse,
  GenerateVideoInput,
  GenerateVideoResponse,
  OptimizeProjectInput,
  OptimizeProjectResponse,
  ParseProjectInput,
  ParseProjectResponse,
  Project,
} from "@/types/project";

interface ProjectTemplatesResponse {
  projects: Project[];
}

export async function getProjectTemplatesAction() {
  const response = await httpClient.get<ProjectTemplatesResponse>("/api/bff/projects/templates");
  return response.data;
}

export async function parseProjectAction(projectID: string, payload: ParseProjectInput) {
  const response = await httpClient.post<ParseProjectResponse>(`/api/bff/projects/${projectID}/parse`, payload);
  return response.data;
}

export async function generateProjectAction(projectID: string, payload: GenerateProjectInput) {
  const response = await httpClient.post<GenerateProjectResponse>(
    `/api/bff/projects/${projectID}/generate`,
    payload
  );
  return response.data;
}

export async function optimizeProjectAction(projectID: string, payload: OptimizeProjectInput) {
  const response = await httpClient.post<OptimizeProjectResponse>(
    `/api/bff/projects/${projectID}/optimize`,
    payload
  );
  return response.data;
}

export async function generateVideoAction(projectID: string, payload: GenerateVideoInput) {
  const response = await httpClient.post<GenerateVideoResponse>(
    `/api/bff/projects/${projectID}/generate-video`,
    payload
  );
  return response.data;
}

export async function deleteProjectAction(projectID: string) {
  await httpClient.delete(`/api/bff/projects/${projectID}`);
}
