import { create } from "zustand";

import { createEmptyProject, normalizeOrder, nowISO } from "@/lib/project-factory";
import type { Project, Scene } from "@/types/project";

interface ProjectStoreState {
	projects: Project[];
	selectedProjectId: string;
	initialized: boolean;
	initializeProjects: (projects: Project[]) => void;
	selectProject: (projectId: string) => void;
	createProject: () => void;
	setProjectStatus: (projectID: string, status: Project["status"]) => void;
	applyParsedScenes: (
		projectID: string,
		status: Project["status"],
		scenes: Scene[],
		source: "llm" | "fallback",
		warning?: string
	) => void;
	updateCurrentScript: (script: string) => void;
	updateScene: (sceneId: string, patch: Partial<Pick<Scene, "narration" | "visualPrompt">>) => void;
	reorderScenes: (activeId: string, overId: string) => void;
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
    const safeProjects = projects.length > 0 ? projects : [createEmptyProject(1)];

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

	setProjectStatus: (projectID, status) => {
		set((state) => ({
			projects: state.projects.map((project) =>
				project.id === projectID
					? {
							...project,
							status,
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
							updatedAt: nowISO(),
							scenes: normalizeOrder(scenes),
					  }
					: project
			),
		}));

		void source;
		void warning;
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
