import { generationRequestTimeout, httpClient } from "@/lib/http/client";
import type {
  BreakdownEpisodeInput,
  BreakdownEpisodeResponse,
  CancelProjectRunResponse,
  CastSheetResponse,
  CharacterItemResponse,
  CharacterListResponse,
  CharacterStateItemResponse,
  CreateCharacterInput,
  CreateCharacterStateInput,
  CreateEpisodeInput,
  CreatePropInput,
  CreateSceneInput,
  DesignVoiceProfileInput,
  DraftPromptInput,
  DraftPromptResponse,
  EpisodeItemResponse,
  EpisodeListResponse,
  ExportItemResponse,
  ExportListResponse,
  GenerateProjectInput,
  GenerateProjectResponse,
  GenerateCoverInput,
  GenerateCoverResponse,
  GenerateReferenceImageInput,
  GenerateStoryboardInput,
  GenerateStoryboardResponse,
  GenerateToneSheetInput,
  GenerateToneSheetResponse,
  GenerateVideoInput,
  GenerateVideoResponse,
  GenerationReferenceKind,
  ImportVoiceProfileInput,
  OptimizeProjectInput,
  OptimizeProjectResponse,
  ParseProjectInput,
  ParseProjectResponse,
  CreateExportInput,
  CreateProjectInput,
  CreateVoiceProfileInput,
  ProjectItemResponse,
  ProjectListResponse,
  ProjectModelsResponse,
  PromptPresetListResponse,
  PropItemResponse,
  PropListResponse,
  PropSheetResponse,
  GenerationJobListResponse,
  ReorderScenesInput,
  Scene,
  SetProjectCoverInput,
  SetSceneCastInput,
  SetSceneCastResponse,
  UpdateCharacterInput,
  UpdateCharacterStateInput,
  UpdateEpisodeInput,
  UpdateProjectInput,
  UpdateProductionSettingsInput,
  UpdatePropInput,
  UpdateSceneInput,
  UpdateVoiceProfileInput,
  UploadReferenceImageInput,
  VoiceProfileItemResponse,
  VoiceProfileListResponse,
  VoiceSheetResponse,
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

export async function createProjectSceneAction(projectID: string, payload: CreateSceneInput) {
  const response = await httpClient.post<{ scene: Scene }>(`/api/bff/projects/${projectID}/scenes`, payload);
  return response.data;
}

export async function deleteProjectSceneAction(projectID: string, sceneID: string) {
  await httpClient.delete(`/api/bff/projects/${projectID}/scenes/${sceneID}`);
}

export async function deleteGenerationReferenceAction(
  projectID: string,
  kind: GenerationReferenceKind,
  assetID: string
) {
  await httpClient.delete(`/api/bff/projects/${projectID}/references/${kind}/${assetID}`);
}

export async function reorderProjectScenesAction(projectID: string, payload: ReorderScenesInput) {
  const response = await httpClient.patch<ProjectItemResponse>(`/api/bff/projects/${projectID}/scenes/reorder`, payload);
  return response.data;
}

export async function parseProjectAction(projectID: string, payload: ParseProjectInput, signal?: AbortSignal) {
  const response = await httpClient.post<ParseProjectResponse>(`/api/bff/projects/${projectID}/parse`, payload, {
    timeout: generationRequestTimeout,
    signal,
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

export async function optimizeProjectAction(projectID: string, payload: OptimizeProjectInput, signal?: AbortSignal) {
  const response = await httpClient.post<OptimizeProjectResponse>(
    `/api/bff/projects/${projectID}/optimize`,
    payload,
    { timeout: generationRequestTimeout, signal }
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

export async function setProjectCoverAction(projectID: string, payload: SetProjectCoverInput) {
  const response = await httpClient.put<ProjectItemResponse>(`/api/bff/projects/${projectID}/cover`, payload);
  return response.data;
}

export async function clearProjectCoverAction(projectID: string) {
  const response = await httpClient.delete<ProjectItemResponse>(`/api/bff/projects/${projectID}/cover`);
  return response.data;
}

/**
 * Draws a cover and returns the bytes as a data URL without storing them, so the create
 * dialog can use it before a project exists. Apply it with `setProjectCoverAction`.
 */
export async function generateCoverAction(payload: GenerateCoverInput, signal?: AbortSignal) {
  const response = await httpClient.post<GenerateCoverResponse>("/api/bff/projects/cover/generate", payload, {
    timeout: generationRequestTimeout,
    signal,
  });
  return response.data;
}

/** The four models this series will actually use, plus the limits the UI must enforce. */
export async function getProjectModelsAction(projectID: string) {
  const response = await httpClient.get<ProjectModelsResponse>(`/api/bff/projects/${projectID}/models`);
  return response.data;
}

/** Built-in starting points for a prompt field, so a blank box is never the only option. */
export async function listPromptPresetsAction(kind: "character" | "prop" | "cover") {
  const response = await httpClient.get<PromptPresetListResponse>(`/api/bff/prompts/presets?kind=${kind}`);
  return response.data;
}

/**
 * Asks whatever this project is rendering to stop after the shot already in flight.
 * Cooperative, so work the provider has been paid for is kept and the run still reports a
 * terminal status.
 */
export async function cancelProjectRunAction(projectID: string) {
  const response = await httpClient.post<CancelProjectRunResponse>(`/api/bff/projects/${projectID}/cancel`);
  return response.data;
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

/**
 * Starts the two-pass render: a tone sheet that anchors the episode's look, then a frame per
 * shot carrying it. Returns as soon as the run is queued — progress arrives by refetch.
 */
export async function generateStoryboardAction(
  projectID: string,
  episodeID: string,
  payload: GenerateStoryboardInput
) {
  const response = await httpClient.post<GenerateStoryboardResponse>(
    `/api/bff/projects/${projectID}/episodes/${episodeID}/storyboard`,
    payload
  );
  return response.data;
}

/**
 * Anchors the episode's look without rendering shots against it, so the user can approve
 * the anchor before paying for a full-resolution frame per shot.
 */
export async function generateToneSheetAction(
  projectID: string,
  episodeID: string,
  payload: GenerateToneSheetInput
) {
  const response = await httpClient.post<GenerateToneSheetResponse>(
    `/api/bff/projects/${projectID}/episodes/${episodeID}/tone-sheet`,
    payload
  );
  return response.data;
}

/**
 * Splits the script into shots, motion directions, or both, leaning on whichever bible
 * entries the caller selected. Slow enough to need the generation timeout and an abort.
 */
export async function breakdownEpisodeAction(
  projectID: string,
  episodeID: string,
  payload: BreakdownEpisodeInput,
  signal?: AbortSignal
) {
  const response = await httpClient.post<BreakdownEpisodeResponse>(
    `/api/bff/projects/${projectID}/episodes/${episodeID}/breakdown`,
    payload,
    { timeout: generationRequestTimeout, signal }
  );
  return response.data;
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

export async function createCharacterStateAction(
  projectID: string,
  characterID: string,
  payload: CreateCharacterStateInput
) {
  const response = await httpClient.post<CharacterStateItemResponse>(
    `/api/bff/projects/${projectID}/characters/${characterID}/states`,
    payload
  );
  return response.data;
}

export async function updateCharacterStateAction(
  projectID: string,
  characterID: string,
  stateID: string,
  payload: UpdateCharacterStateInput
) {
  const response = await httpClient.patch<CharacterStateItemResponse>(
    `/api/bff/projects/${projectID}/characters/${characterID}/states/${stateID}`,
    payload
  );
  return response.data;
}

export async function deleteCharacterStateAction(projectID: string, characterID: string, stateID: string) {
  await httpClient.delete(`/api/bff/projects/${projectID}/characters/${characterID}/states/${stateID}`);
}

/** Returns the drafted prompt for review; it is not saved until the user applies it. */
export async function draftCharacterStatePromptAction(
  projectID: string,
  characterID: string,
  stateID: string,
  payload: DraftPromptInput,
  signal?: AbortSignal
) {
  const response = await httpClient.post<DraftPromptResponse>(
    `/api/bff/projects/${projectID}/characters/${characterID}/states/${stateID}/prompt`,
    payload,
    { timeout: generationRequestTimeout, signal }
  );
  return response.data;
}

export async function generateCharacterStateImageAction(
  projectID: string,
  characterID: string,
  stateID: string,
  payload: GenerateReferenceImageInput,
  signal?: AbortSignal
) {
  const response = await httpClient.post<CharacterItemResponse>(
    `/api/bff/projects/${projectID}/characters/${characterID}/states/${stateID}/image`,
    payload,
    { timeout: generationRequestTimeout, signal }
  );
  return response.data;
}

export async function uploadCharacterStateImageAction(
  projectID: string,
  characterID: string,
  stateID: string,
  payload: UploadReferenceImageInput
) {
  const response = await httpClient.put<CharacterItemResponse>(
    `/api/bff/projects/${projectID}/characters/${characterID}/states/${stateID}/image`,
    payload
  );
  return response.data;
}

export async function mergeCharacterSheetAction(projectID: string, characterID: string) {
  const response = await httpClient.post<CharacterItemResponse>(
    `/api/bff/projects/${projectID}/characters/${characterID}/sheet`,
    undefined,
    { timeout: generationRequestTimeout }
  );
  return response.data;
}

/** Tiles every character and state into the single sheet a storyboard render carries. */
export async function mergeCastSheetAction(projectID: string) {
  const response = await httpClient.post<CastSheetResponse>(
    `/api/bff/projects/${projectID}/characters/sheet`,
    undefined,
    { timeout: generationRequestTimeout }
  );
  return response.data;
}

export async function listPropsAction(projectID: string) {
  const response = await httpClient.get<PropListResponse>(`/api/bff/projects/${projectID}/props`);
  return response.data;
}

export async function createPropAction(projectID: string, payload: CreatePropInput) {
  const response = await httpClient.post<PropItemResponse>(`/api/bff/projects/${projectID}/props`, payload);
  return response.data;
}

export async function updatePropAction(projectID: string, propID: string, payload: UpdatePropInput) {
  const response = await httpClient.patch<PropItemResponse>(
    `/api/bff/projects/${projectID}/props/${propID}`,
    payload
  );
  return response.data;
}

export async function deletePropAction(projectID: string, propID: string) {
  await httpClient.delete(`/api/bff/projects/${projectID}/props/${propID}`);
}

export async function draftPropPromptAction(
  projectID: string,
  propID: string,
  payload: DraftPromptInput,
  signal?: AbortSignal
) {
  const response = await httpClient.post<DraftPromptResponse>(
    `/api/bff/projects/${projectID}/props/${propID}/prompt`,
    payload,
    { timeout: generationRequestTimeout, signal }
  );
  return response.data;
}

export async function generatePropImageAction(
  projectID: string,
  propID: string,
  payload: GenerateReferenceImageInput,
  signal?: AbortSignal
) {
  const response = await httpClient.post<PropItemResponse>(
    `/api/bff/projects/${projectID}/props/${propID}/image`,
    payload,
    { timeout: generationRequestTimeout, signal }
  );
  return response.data;
}

export async function uploadPropImageAction(projectID: string, propID: string, payload: UploadReferenceImageInput) {
  const response = await httpClient.put<PropItemResponse>(
    `/api/bff/projects/${projectID}/props/${propID}/image`,
    payload
  );
  return response.data;
}

export async function mergePropSheetAction(projectID: string) {
  const response = await httpClient.post<PropSheetResponse>(
    `/api/bff/projects/${projectID}/props/sheet`,
    undefined,
    { timeout: generationRequestTimeout }
  );
  return response.data;
}

export async function listExportsAction(projectID: string) {
  const response = await httpClient.get<ExportListResponse>(`/api/bff/projects/${projectID}/exports`);
  return response.data;
}

/** Queues the merge and returns immediately; the caller polls the job for progress. */
export async function createExportAction(projectID: string, payload: CreateExportInput) {
  const response = await httpClient.post<ExportItemResponse>(`/api/bff/projects/${projectID}/exports`, payload);
  return response.data;
}

export async function getExportAction(projectID: string, exportID: string) {
  const response = await httpClient.get<ExportItemResponse>(`/api/bff/projects/${projectID}/exports/${exportID}`);
  return response.data;
}

export async function deleteExportAction(projectID: string, exportID: string) {
  const response = await httpClient.delete<{ success: boolean }>(`/api/bff/projects/${projectID}/exports/${exportID}`);
  return response.data;
}

export async function listVoicesAction(projectID: string) {
  const response = await httpClient.get<VoiceProfileListResponse>(`/api/bff/projects/${projectID}/voices`);
  return response.data;
}

export async function createVoiceAction(projectID: string, payload: CreateVoiceProfileInput) {
  const response = await httpClient.post<VoiceProfileItemResponse>(`/api/bff/projects/${projectID}/voices`, payload);
  return response.data;
}

export async function updateVoiceAction(projectID: string, voiceID: string, payload: UpdateVoiceProfileInput) {
  const response = await httpClient.patch<VoiceProfileItemResponse>(
    `/api/bff/projects/${projectID}/voices/${voiceID}`,
    payload
  );
  return response.data;
}

export async function deleteVoiceAction(projectID: string, voiceID: string) {
  await httpClient.delete(`/api/bff/projects/${projectID}/voices/${voiceID}`);
}

/**
 * Designs a timbre from a description and binds it to this series. Slow — the provider can
 * take minutes — so it carries the generation timeout and an abort signal.
 */
export async function designVoiceProfileAction(
  projectID: string,
  payload: DesignVoiceProfileInput,
  signal?: AbortSignal
) {
  const response = await httpClient.post<VoiceProfileItemResponse>(
    `/api/bff/projects/${projectID}/voices/design`,
    payload,
    { timeout: generationRequestTimeout, signal }
  );
  return response.data;
}

/** Binds a timbre already saved on the account to this series. */
export async function importVoiceProfileAction(projectID: string, payload: ImportVoiceProfileInput) {
  const response = await httpClient.post<VoiceProfileItemResponse>(
    `/api/bff/projects/${projectID}/voices/import`,
    payload
  );
  return response.data;
}

/** Synthesises the profile's sample line so the user can hear it before binding it. */
export async function previewVoiceAction(projectID: string, voiceID: string) {
  const response = await httpClient.post<VoiceProfileItemResponse>(
    `/api/bff/projects/${projectID}/voices/${voiceID}/preview`,
    undefined,
    { timeout: generationRequestTimeout }
  );
  return response.data;
}

/** Concatenates every auditioned voice into the timbre reference the video model hears. */
export async function mergeVoiceSheetAction(projectID: string) {
  const response = await httpClient.post<VoiceSheetResponse>(
    `/api/bff/projects/${projectID}/voices/merge`,
    undefined,
    { timeout: generationRequestTimeout }
  );
  return response.data;
}

export async function setSceneCastAction(projectID: string, sceneID: string, payload: SetSceneCastInput) {
  const response = await httpClient.put<SetSceneCastResponse>(
    `/api/bff/projects/${projectID}/scenes/${sceneID}/characters`,
    payload
  );
  return response.data;
}
