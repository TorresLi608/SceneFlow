import { create } from "zustand";

import { createEmptyProject, normalizeOrder, nowISO } from "@/lib/project-factory";
import type { Project, Scene, SceneUpdatePayload } from "@/types/project";

interface ProjectStoreState {
  projects: Project[];
  selectedProjectId: string;
  initialized: boolean;
  initializeProjects: (projects: Project[]) => void;
  selectProject: (projectId: string) => void;
  createProject: () => void;
  removeProject: (projectId: string) => void;
  setProjectStatus: (projectID: string, status: Project["status"]) => void;
  updateProjectFields: (
    projectID: string,
    patch: Partial<
      Pick<Project, "status" | "originalScript" | "videoStatus" | "videoProgress" | "videoUrl">
    >
  ) => void;
  applyParsedScenes: (
    projectID: string,
    status: Project["status"],
    scenes: Scene[],
    source: "llm" | "fallback",
    warning?: string
  ) => void;
  applySceneStreamUpdate: (projectID: string, sceneID: string, data: SceneUpdatePayload) => void;
  updateCurrentScript: (script: string) => void;
  updateScene: (sceneId: string, patch: Partial<Pick<Scene, "narration" | "visualPrompt">>) => void;
  reorderScenes: (activeId: string, overId: string) => void;
}

function normalizeScene(scene: Scene): Scene {
  return {
    ...scene,
    image: {
      url: scene.image?.url ?? null,
      status: scene.image?.status ?? "idle",
      progress: typeof scene.image?.progress === "number" ? scene.image.progress : 0,
    },
    audio: {
      url: scene.audio?.url ?? null,
      status: scene.audio?.status ?? "idle",
      progress: typeof scene.audio?.progress === "number" ? scene.audio.progress : 0,
      duration: typeof scene.audio?.duration === "number" ? scene.audio.duration : 0,
    },
  };
}

function normalizeProject(project: Project): Project {
  return {
    ...project,
    videoStatus: project.videoStatus ?? "idle",
    videoProgress: typeof project.videoProgress === "number" ? project.videoProgress : 0,
    videoUrl: project.videoUrl ?? null,
    scenes: normalizeOrder(project.scenes.map(normalizeScene)),
  };
}

const reorder = (items: Scene[], activeId: string, overId: string) => {
  const oldIndex = items.findIndex((scene) => scene.id === activeId);
  const newIndex = items.findIndex((scene) => scene.id === overId);

  if (oldIndex < 0 || newIndex < 0) {
    return items;
  }

  const cloned = [...items];
  const [moved] = cloned.splice(oldIndex, 1);
  cloned.splice(newIndex, 0, moved);
  return normalizeOrder(cloned);
};

export const useProjectStore = create<ProjectStoreState>()((set, get) => ({
  projects: [],
  selectedProjectId: "",
  initialized: false,

  initializeProjects: (projects) => {
    const normalized = projects.map(normalizeProject);
    const safeProjects = normalized.length > 0 ? normalized : [createEmptyProject(1)];

    set((state) => {
      if (state.initialized) {
        return state;
      }

      return {
        projects: safeProjects,
        selectedProjectId: safeProjects[0]?.id ?? "",
        initialized: true,
      };
    });
  },

  selectProject: (projectId) => set({ selectedProjectId: projectId }),

  createProject: () => {
    const nextProject = createEmptyProject(get().projects.length + 1);

    set((state) => ({
      projects: [nextProject, ...state.projects],
      selectedProjectId: nextProject.id,
      initialized: true,
    }));
  },

  removeProject: (projectId) => {
    set((state) => {
      const nextProjects = state.projects.filter((project) => project.id !== projectId);
      if (nextProjects.length === 0) {
        return {
          projects: [],
          selectedProjectId: "",
          initialized: true,
        };
      }

      const selectedProjectId =
        state.selectedProjectId === projectId ? nextProjects[0].id : state.selectedProjectId;

      return {
        projects: nextProjects,
        selectedProjectId,
        initialized: true,
      };
    });
  },

  setProjectStatus: (projectID, status) => {
    set((state) => ({
      projects: state.projects.map((project) =>
        project.id === projectID
          ? {
              ...project,
              status,
              updatedAt: nowISO(),
            }
          : project
      ),
    }));
  },

  updateProjectFields: (projectID, patch) => {
    set((state) => ({
      projects: state.projects.map((project) =>
        project.id === projectID
          ? {
              ...project,
              ...patch,
              updatedAt: nowISO(),
            }
          : project
      ),
    }));
  },

  applyParsedScenes: (projectID, status, scenes, source, warning) => {
    set((state) => ({
      projects: state.projects.map((project) =>
        project.id === projectID
          ? {
              ...project,
              status,
              videoStatus: "idle",
              videoProgress: 0,
              videoUrl: null,
              updatedAt: nowISO(),
              scenes: normalizeOrder(scenes.map(normalizeScene)),
            }
          : project
      ),
    }));

    void source;
    void warning;
  },

  applySceneStreamUpdate: (projectID, sceneID, data) => {
    set((state) => ({
      projects: state.projects.map((project) => {
        if (project.id !== projectID) {
          return project;
        }

        const updatedScenes = project.scenes.map((scene) => {
          if (scene.id !== sceneID) {
            return scene;
          }

          const nextScene: Scene = {
            ...scene,
            image: { ...scene.image },
            audio: { ...scene.audio },
          };

          if (typeof data.order === "number") {
            nextScene.order = data.order;
          }
          if (typeof data.narration === "string") {
            nextScene.narration = data.narration;
          }
          if (typeof data.visualPrompt === "string") {
            nextScene.visualPrompt = data.visualPrompt;
          }

          if (typeof data.imageStatus === "string") {
            nextScene.image.status = data.imageStatus;
          }
          if (typeof data.imageProgress === "number") {
            nextScene.image.progress = data.imageProgress;
          }
          if ("imageUrl" in data) {
            nextScene.image.url = data.imageUrl ?? null;
          }

          if (typeof data.audioStatus === "string") {
            nextScene.audio.status = data.audioStatus;
          }
          if (typeof data.audioProgress === "number") {
            nextScene.audio.progress = data.audioProgress;
          }
          if ("audioUrl" in data) {
            nextScene.audio.url = data.audioUrl ?? null;
          }
          if (typeof data.audioDuration === "number") {
            nextScene.audio.duration = data.audioDuration;
          }

          return nextScene;
        });

        return {
          ...project,
          updatedAt: nowISO(),
          scenes: normalizeOrder(updatedScenes),
        };
      }),
    }));
  },

  updateCurrentScript: (script) => {
    set((state) => ({
      projects: state.projects.map((project) =>
        project.id === state.selectedProjectId
          ? {
              ...project,
              originalScript: script,
              updatedAt: nowISO(),
            }
          : project
      ),
    }));
  },

  updateScene: (sceneId, patch) => {
    set((state) => ({
      projects: state.projects.map((project) =>
        project.id !== state.selectedProjectId
          ? project
          : {
              ...project,
              updatedAt: nowISO(),
              scenes: project.scenes.map((scene) =>
                scene.id === sceneId
                  ? {
                      ...scene,
                      ...patch,
                    }
                  : scene
              ),
            }
      ),
    }));
  },

  reorderScenes: (activeId, overId) => {
    set((state) => ({
      projects: state.projects.map((project) =>
        project.id !== state.selectedProjectId
          ? project
          : {
              ...project,
              updatedAt: nowISO(),
              scenes: reorder(project.scenes, activeId, overId),
            }
      ),
    }));
  },
}));
