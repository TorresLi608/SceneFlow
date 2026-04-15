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

export interface Project {
  id: string;
  title: string;
  originalScript: string;
  status: ProjectStatus;
  videoStatus: SceneTaskStatus | "idle";
  videoProgress: number;
  videoUrl: string | null;
  updatedAt: string;
  scenes: Scene[];
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
