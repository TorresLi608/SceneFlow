export type SceneTaskStatus = "idle" | "generating" | "success" | "error";

/** One shot inside an episode. Order numbers restart at 1 in every episode. */
export interface Scene {
  id: string;
  episodeId: string | null;
  order: number;
  narration: string;
  /** Spoken by `speakerCharacterId`; `narration` stays the narrator's line. */
  dialogue: string;
  speakerCharacterId: string | null;
  visualPrompt: string;
  shotType: string;
  cameraMove: string;
  /** Manual screen-time override in ms. 0 means follow the voice track's length. */
  durationMs: number;
  subtitleText: string;
  /** An approved shot that a batch rerun must leave alone. */
  isLocked: boolean;
  image: {
    url: string | null;
    status: SceneTaskStatus;
    progress: number;
  };
  audio: {
    url: string | null;
    status: SceneTaskStatus;
    progress: number;
    duration: number;
  };
  video: {
    url: string | null;
    status: SceneTaskStatus | "idle";
    progress: number;
  };
  /** Last failure reason, persisted so it survives a reload. Empty when the scene is healthy. */
  errorMessage: string;
}

export type EpisodeStatus = "draft" | "storyboard" | "generating" | "done" | "partial" | "failed";

/** An episode without its script or shots: enough to render a switcher or a series list. */
export interface EpisodeSummary {
  id: string;
  projectId: string;
  episodeNumber: number;
  title: string;
  synopsis: string;
  status: EpisodeStatus;
  videoStatus: SceneTaskStatus | "idle";
  videoProgress: number;
  durationMs: number;
  sceneCount: number;
  errorMessage: string;
  updatedAt: string;
}

export interface Episode extends EpisodeSummary {
  sourceText: string;
  videoUrl: string | null;
  scenes: Scene[];
}

export type ProjectStatus =
  | "idle"
  | "parsing"
  | "generating"
  | "video_generating"
  | "done"
  /** Some shots landed and some failed; retry the failed ones rather than rerunning everything. */
  | "partial"
  | "failed";
export type ProjectMode = "comic" | "drama";
export type ProjectStage = "script" | "bible" | "storyboard" | "audio" | "timeline" | "export";

export interface ProductionSettings {
  mode: ProjectMode;
  aspectRatio: "9:16" | "16:9" | "1:1";
  width: number;
  height: number;
  fps: 24 | 30;
  targetDurationMs: number;
  language: string;
  stylePrompt: string;
  negativePrompt: string;
}

export interface Project {
  id: string;
  title: string;
  originalScript: string;
  /** World, tone, and running plot threads, carried into later episodes. */
  seriesBible: string;
  status: ProjectStatus;
  videoStatus: SceneTaskStatus | "idle";
  videoProgress: number;
  videoUrl: string | null;
  productionSettings: ProductionSettings;
  currentStage: ProjectStage;
  /** The episode `scenes` belongs to. Null only for a series with no episode yet. */
  currentEpisodeId: string | null;
  episodes: EpisodeSummary[];
  updatedAt: string;
  /** The current episode's shots, never the whole series': order numbers restart each episode. */
  scenes: Scene[];
}

export interface ProjectItemResponse {
  project: Project;
}

export interface ProjectListResponse {
  projects: Project[];
}

export interface CreateProjectInput {
  title?: string;
  originalScript?: string;
  productionSettings?: Partial<ProductionSettings>;
}

export interface UpdateProjectInput {
  title?: string;
  originalScript?: string;
  seriesBible?: string;
}

export interface CreateEpisodeInput {
  title?: string;
  synopsis?: string;
  sourceText?: string;
}

export interface UpdateEpisodeInput {
  title?: string;
  synopsis?: string;
  sourceText?: string;
  status?: EpisodeStatus;
}

export interface EpisodeListResponse {
  episodes: EpisodeSummary[];
}

export interface EpisodeItemResponse {
  episode: Episode;
}

export type UpdateProductionSettingsInput = Partial<ProductionSettings> & {
  currentStage?: ProjectStage;
};

export type GenerationJobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

export interface GenerationJob {
  id: string;
  projectId: string;
  sceneId: string | null;
  jobType: "storyboards" | "audio" | "videos" | "preview" | "export";
  status: GenerationJobStatus;
  progress: number;
  attempt: number;
  maxAttempts: number;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface GenerationJobListResponse {
  jobs: GenerationJob[];
}

export interface UpdateSceneInput {
  narration?: string;
  dialogue?: string;
  speakerCharacterId?: string;
  visualPrompt?: string;
  shotType?: string;
  cameraMove?: string;
  durationMs?: number;
  subtitleText?: string;
  isLocked?: boolean;
}

export interface ReorderScenesInput {
  sceneIds: string[];
  /** Order numbers restart each episode, so a reorder is always within one. */
  episodeId?: string;
}

export interface ParseProjectInput {
  script: string;
  model?: string;
  /** Which episode the parsed shots land in. Omitted means the current one. */
  episodeId?: string;
  /**
   * Reparsing discards generated shots. Without this the backend returns a preview
   * (`applied: false`) so the user can confirm before losing rendered work.
   */
  replaceAll?: boolean;
}

/** A parsed shot that has not been written to the project yet. */
export interface PendingScene {
  order: number;
  narration: string;
  visualPrompt: string;
}

export interface ParseProjectResponse {
  projectId: string;
  episodeId: string;
  status: ProjectStatus;
  source: "llm" | "fallback";
  warning?: string;
  applied: boolean;
  discardsGeneratedScenes: number;
  pendingScenes: PendingScene[];
  scenes: Scene[];
}

export interface GenerateProjectInput {
  model?: string;
  episodeId?: string;
}

export interface GenerateProjectResponse {
  projectId: string;
  episodeId: string;
  status: ProjectStatus;
  sceneCount: number;
  model?: string;
  provider?: string;
  imageModel?: string;
}

export interface OptimizeProjectInput {
  script?: string;
  model?: string;
}

export interface OptimizeProjectResponse {
  projectId: string;
  optimizedScript: string;
  tips: string[];
  source: "llm" | "fallback";
  warning?: string;
  appliedToProject: boolean;
}

export interface GenerateVideoInput {
  model?: string;
}

export interface GenerateVideoResponse {
  projectId: string;
  status: ProjectStatus;
  model: string;
}

export interface SceneUpdatePayload {
  episodeId?: string;
  narration?: string;
  dialogue?: string;
  speakerCharacterId?: string | null;
  visualPrompt?: string;
  shotType?: string;
  cameraMove?: string;
  durationMs?: number;
  subtitleText?: string;
  isLocked?: boolean;
  order?: number;
  parseStatus?: string;
  imageStatus?: SceneTaskStatus;
  imageProgress?: number;
  imageUrl?: string | null;
  audioStatus?: SceneTaskStatus;
  audioProgress?: number;
  audioUrl?: string | null;
  audioDuration?: number;
  videoStatus?: SceneTaskStatus | "idle";
  videoProgress?: number;
  videoUrl?: string | null;
  videoModel?: string;
  errorMsg?: string;
}