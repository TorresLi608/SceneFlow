export type SceneTaskStatus = "idle" | "generating" | "success" | "error";

export interface Scene {
  id: string;
  order: number;
  narration: string;
  visualPrompt: string;
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
}

export type ProjectStatus = "idle" | "parsing" | "generating" | "video_generating" | "done";
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
  status: ProjectStatus;
  videoStatus: SceneTaskStatus | "idle";
  videoProgress: number;
  videoUrl: string | null;
  productionSettings: ProductionSettings;
  currentStage: ProjectStage;
  updatedAt: string;
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
  visualPrompt?: string;
}

export interface ReorderScenesInput {
  sceneIds: string[];
}

export interface ParseProjectInput {
  script: string;
  model?: string;
}

export interface ParseProjectResponse {
  projectId: string;
  status: ProjectStatus;
  source: "llm" | "fallback";
  warning?: string;
  scenes: Scene[];
}

export interface GenerateProjectInput {
  model?: string;
}

export interface GenerateProjectResponse {
  projectId: string;
  status: ProjectStatus;
  sceneCount: number;
  model?: string;
  provider?: string;
  imageModel?: string;
  warning?: string;
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
  narration?: string;
  visualPrompt?: string;
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
