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
  CreateProjectInput,
  ProjectItemResponse,
  ProjectListResponse,
  GenerationJobListResponse,
  ReorderScenesInput,
  UpdateProjectInput,
  UpdateProductionSettingsInput,
  UpdateSceneInput,
} from "@/types/project";

export async function listProjectsAction() {
  const response = await httpClient.get<ProjectListResponse>("/api/bff/projects");
  return response.data;
}

export async function createProjectAction(payload: CreateProjectInput) {
  const response = await httpClient.post<ProjectItemResponse>("/api/bff/projects", payload);
  return response.data;
}

export async function updateProjectAction(projectID: string, payload: UpdateProjectInput) {
  const response = await httpClient.patch<ProjectItemResponse>(`/api/bff/projects/${projectID}`, payload);
  return response.data;
}

export async function updateProductionSettingsAction(projectID: string, payload: UpdateProductionSettingsInput) {
  const response = await httpClient.patch<ProjectItemResponse>(
    `/api/bff/projects/${projectID}/production-settings`,
    payload
  );
  return response.data;
}

export async function listProjectJobsAction(projectID: string) {
  const response = await httpClient.get<GenerationJobListResponse>(`/api/bff/projects/${projectID}/jobs`);
  return response.data;
}

export async function updateProjectSceneAction(projectID: string, sceneID: string, payload: UpdateSceneInput) {
  const response = await httpClient.patch<{ scene: unknown }>(`/api/bff/projects/${projectID}/scenes/${sceneID}`, payload);
  return response.data;
}

export async function reorderProjectScenesAction(projectID: string, payload: ReorderScenesInput) {
  const response = await httpClient.patch<ProjectItemResponse>(`/api/bff/projects/${projectID}/scenes/reorder`, payload);
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
