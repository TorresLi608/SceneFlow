import { generationRequestTimeout, httpClient } from "@/lib/http/client";
import type {
  CharacterItemResponse,
  CharacterListResponse,
  CharacterVariantItemResponse,
  CreateCharacterInput,
  CreateCharacterVariantInput,
  CreateEpisodeInput,
  EpisodeItemResponse,
  EpisodeListResponse,
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
  SetSceneCastInput,
  SetSceneCastResponse,
  UpdateCharacterInput,
  UpdateEpisodeInput,
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
  const response = await httpClient.post<ParseProjectResponse>(`/api/bff/projects/${projectID}/parse`, payload, {
    timeout: generationRequestTimeout,
  });
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
    payload,
    { timeout: generationRequestTimeout }
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

export async function listEpisodesAction(projectID: string) {
  const response = await httpClient.get<EpisodeListResponse>(`/api/bff/projects/${projectID}/episodes`);
  return response.data;
}

export async function getEpisodeAction(projectID: string, episodeID: string) {
  const response = await httpClient.get<EpisodeItemResponse>(
    `/api/bff/projects/${projectID}/episodes/${episodeID}`
  );
  return response.data;
}

export async function createEpisodeAction(projectID: string, payload: CreateEpisodeInput) {
  const response = await httpClient.post<EpisodeItemResponse>(
    `/api/bff/projects/${projectID}/episodes`,
    payload
  );
  return response.data;
}

export async function updateEpisodeAction(projectID: string, episodeID: string, payload: UpdateEpisodeInput) {
  const response = await httpClient.patch<EpisodeItemResponse>(
    `/api/bff/projects/${projectID}/episodes/${episodeID}`,
    payload
  );
  return response.data;
}

export async function deleteEpisodeAction(projectID: string, episodeID: string) {
  await httpClient.delete(`/api/bff/projects/${projectID}/episodes/${episodeID}`);
}

export async function listCharactersAction(projectID: string) {
  const response = await httpClient.get<CharacterListResponse>(`/api/bff/projects/${projectID}/characters`);
  return response.data;
}

export async function createCharacterAction(projectID: string, payload: CreateCharacterInput) {
  const response = await httpClient.post<CharacterItemResponse>(
    `/api/bff/projects/${projectID}/characters`,
    payload
  );
  return response.data;
}

export async function updateCharacterAction(projectID: string, characterID: string, payload: UpdateCharacterInput) {
  const response = await httpClient.patch<CharacterItemResponse>(
    `/api/bff/projects/${projectID}/characters/${characterID}`,
    payload
  );
  return response.data;
}

export async function deleteCharacterAction(projectID: string, characterID: string) {
  await httpClient.delete(`/api/bff/projects/${projectID}/characters/${characterID}`);
}

/** Draws the reference portrait; slow enough that callers should show a pending state. */
export async function generateCharacterPortraitAction(projectID: string, characterID: string) {
  const response = await httpClient.post<CharacterItemResponse>(
    `/api/bff/projects/${projectID}/characters/${characterID}/portrait`,
    undefined,
    { timeout: generationRequestTimeout }
  );
  return response.data;
}

export async function createCharacterVariantAction(
  projectID: string,
  characterID: string,
  payload: CreateCharacterVariantInput
) {
  const response = await httpClient.post<CharacterVariantItemResponse>(
    `/api/bff/projects/${projectID}/characters/${characterID}/variants`,
    payload
  );
  return response.data;
}

export async function deleteCharacterVariantAction(projectID: string, characterID: string, variantID: string) {
  await httpClient.delete(`/api/bff/projects/${projectID}/characters/${characterID}/variants/${variantID}`);
}

export async function setSceneCastAction(projectID: string, sceneID: string, payload: SetSceneCastInput) {
  const response = await httpClient.put<SetSceneCastResponse>(
    `/api/bff/projects/${projectID}/scenes/${sceneID}/characters`,
    payload
  );
  return response.data;
}
