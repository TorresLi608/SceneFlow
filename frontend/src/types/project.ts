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
    duration: number;
  };
}

export type ProjectStatus = "idle" | "parsing" | "generating" | "done";

export interface Project {
  id: string;
  title: string;
  originalScript: string;
  status: ProjectStatus;
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
