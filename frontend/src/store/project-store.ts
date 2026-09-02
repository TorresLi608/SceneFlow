import { create } from "zustand";
import { arrayMove } from "@dnd-kit/sortable";

import { normalizeOrder, nowISO } from "@/lib/project-factory";
import type { Episode, EpisodeSummary, Project, Scene, SceneUpdatePayload } from "@/types/project";

/** The scene fields a user can edit directly; the pipeline owns everything else. */
export type SceneEdit = Partial<
  Pick<
    Scene,
    | "narration"
    | "dialogue"
    | "visualPrompt"
    | "shotType"
    | "cameraMove"
    | "durationMs"
    | "subtitleText"
    | "isLocked"
  >
> & {
  /**
   * An empty string clears the speaker. Not null: the backend drops null fields so it can
   * tell "leave this alone" from "set it", so null would silently do nothing.
   */
  speakerCharacterId?: string;
};

interface ProjectStoreState {
  projects: Project[];
  selectedProjectId: string;
  initialized: boolean;
  reset: () => void;
  initializeProjects: (projects: Project[]) => void;
  selectProject: (projectId: string) => void;
  createProject: (project: Project) => void;
  removeProject: (projectId: string) => void;
  setProjectStatus: (projectID: string, status: Project["status"]) => void;
  updateProjectFields: (
    projectID: string,
    patch: Partial<
      Pick<
        Project,
        | "status"
        | "title"
        | "description"
        | "coverImageUrl"
        | "originalScript"
        | "seriesBible"
        | "videoStatus"
        | "videoProgress"
        | "videoUrl"
        | "productionSettings"
        | "currentStage"
      >
    >
  ) => void;
  /** Switch which episode the workbench is editing, and load its shots. */
  openEpisode: (projectID: string, episodeId: string, scenes: Scene[]) => void;
  upsertEpisode: (projectID: string, episode: EpisodeSummary | Episode) => void;
  removeEpisode: (projectID: string, episodeId: string) => void;
  applyParsedScenes: (
    projectID: string,
    status: Project["status"],
    scenes: Scene[],
    source: "llm" | "fallback",
    warning?: string
  ) => void;
  applySceneStreamUpdate: (projectID: string, sceneID: string, data: SceneUpdatePayload) => void;
  updateCurrentScript: (script: string) => void;
  updateScene: (sceneId: string, patch: SceneEdit) => void;
  addScene: (scene: Scene) => void;
  removeScene: (sceneId: string) => void;
  /** Cast lives in its own join table, so it is set through its own endpoint and action. */
  setSceneCast: (sceneId: string, characterIds: string[]) => void;
  /** A deleted character has to leave every shot it was cast in. */
  dropCharacter: (characterId: string) => void;
  reorderScenes: (activeId: string, overId: string) => void;
}

function normalizeScene(scene: Scene): Scene {
  return {
    ...scene,
    episodeId: scene.episodeId ?? null,
    dialogue: scene.dialogue ?? "",
    // The backend clears a speaker by storing NULL, but an older row may hold "".
    speakerCharacterId: scene.speakerCharacterId || null,
    shotType: scene.shotType ?? "",
    cameraMove: scene.cameraMove ?? "",
    durationMs: typeof scene.durationMs === "number" ? scene.durationMs : 0,
    subtitleText: scene.subtitleText ?? "",
    characterIds: scene.characterIds ?? [],
    isLocked: Boolean(scene.isLocked),
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
    video: {
      url: scene.video?.url ?? null,
      status: scene.video?.status ?? "idle",
      progress: typeof scene.video?.progress === "number" ? scene.video.progress : 0,
    },
    errorMessage: scene.errorMessage ?? "",
  };
}

function normalizeProject(project: Project): Project {
  return {
    ...project,
    description: project.description ?? "",
    coverImageUrl: project.coverImageUrl ?? null,
    seriesBible: project.seriesBible ?? "",
    videoStatus: project.videoStatus ?? "idle",
    videoProgress: typeof project.videoProgress === "number" ? project.videoProgress : 0,
    videoUrl: project.videoUrl ?? null,
    productionSettings: project.productionSettings ?? {
      mode: "comic",
      aspectRatio: "9:16",
      width: 1080,
      height: 1920,
      fps: 24,
      targetDurationMs: 60000,
      language: "zh-CN",
      stylePrompt: "",
      negativePrompt: "",
    },
    currentStage: project.currentStage ?? "script",
    currentEpisodeId: project.currentEpisodeId ?? null,
    episodes: project.episodes ?? [],
    scenes: normalizeOrder((project.scenes ?? []).map(normalizeScene)),
  };
}

/** Keep an episode's shot count honest after the storyboard under it changes. */
function withSceneCount(episodes: EpisodeSummary[], episodeId: string | null, count: number) {
  if (!episodeId) {
    return episodes;
  }
  return episodes.map((episode) =>
    episode.id === episodeId ? { ...episode, sceneCount: count } : episode
  );
}

/** Drop the script and shots an episode detail carries: the switcher list holds summaries. */
function toSummary(episode: EpisodeSummary | Episode): EpisodeSummary {
  return {
    id: episode.id,
    projectId: episode.projectId,
    episodeNumber: episode.episodeNumber,
    title: episode.title,
    synopsis: episode.synopsis,
    status: episode.status,
    videoStatus: episode.videoStatus,
    videoProgress: episode.videoProgress,
    durationMs: episode.durationMs,
    sceneCount: episode.sceneCount,
    toneImageStatus: episode.toneImageStatus,
    toneImageUrl: episode.toneImageUrl,
    errorMessage: episode.errorMessage,
    updatedAt: episode.updatedAt,
  };
}

const reorder = (items: Scene[], activeId: string, overId: string) => {
  const oldIndex = items.findIndex((scene) => scene.id === activeId);
  const newIndex = items.findIndex((scene) => scene.id === overId);

  if (oldIndex < 0 || newIndex < 0) {
    return items;
  }

  return normalizeOrder(arrayMove(items, oldIndex, newIndex));
};

export const useProjectStore = create<ProjectStoreState>()((set) => ({
  projects: [],
  selectedProjectId: "",
  initialized: false,

  reset: () =>
    set({
      projects: [],
      selectedProjectId: "",
      initialized: false,
    }),

  initializeProjects: (projects) => {
    const normalized = projects.map(normalizeProject);

    set((state) => {
      if (state.initialized) {
        return state;
      }

      return {
        projects: normalized,
        selectedProjectId: normalized[0]?.id ?? "",
        initialized: true,
      };
    });
  },

  selectProject: (projectId) => set({ selectedProjectId: projectId }),

  createProject: (project) => {
    const nextProject = normalizeProject(project);
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

  openEpisode: (projectID, episodeId, scenes) => {
    set((state) => ({
      projects: state.projects.map((project) =>
        project.id === projectID
          ? {
              ...project,
              currentEpisodeId: episodeId,
              episodes: withSceneCount(project.episodes, episodeId, scenes.length),
              scenes: normalizeOrder(scenes.map(normalizeScene)),
            }
          : project
      ),
    }));
  },

  upsertEpisode: (projectID, episode) => {
    const summary = toSummary(episode);
    set((state) => ({
      projects: state.projects.map((project) => {
        if (project.id !== projectID) {
          return project;
        }

        const known = project.episodes.some((item) => item.id === summary.id);
        const episodes = known
          ? project.episodes.map((item) => (item.id === summary.id ? summary : item))
          : [...project.episodes, summary].sort((a, b) => a.episodeNumber - b.episodeNumber);

        return { ...project, episodes, updatedAt: nowISO() };
      }),
    }));
  },

  removeEpisode: (projectID, episodeId) => {
    set((state) => ({
      projects: state.projects.map((project) => {
        if (project.id !== projectID) {
          return project;
        }

        const episodes = project.episodes.filter((item) => item.id !== episodeId);
        const stillOpen = project.currentEpisodeId !== episodeId;

        return {
          ...project,
          episodes,
          updatedAt: nowISO(),
          // The open episode just went away, so fall back to the newest one that is left.
          // Its shots arrive with the follow-up load; showing the deleted one's would lie.
          currentEpisodeId: stillOpen ? project.currentEpisodeId : episodes.at(-1)?.id ?? null,
          scenes: stillOpen ? project.scenes : [],
        };
      }),
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
              episodes: withSceneCount(project.episodes, project.currentEpisodeId, scenes.length),
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
            video: { ...scene.video },
          };

          if (typeof data.order === "number") {
            nextScene.order = data.order;
          }
          if (typeof data.narration === "string") {
            nextScene.narration = data.narration;
          }
          if (typeof data.dialogue === "string") {
            nextScene.dialogue = data.dialogue;
          }
          if ("speakerCharacterId" in data) {
            nextScene.speakerCharacterId = data.speakerCharacterId ?? null;
          }
          if (Array.isArray(data.characterIds)) {
            nextScene.characterIds = data.characterIds;
          }
          if (typeof data.visualPrompt === "string") {
            nextScene.visualPrompt = data.visualPrompt;
          }
          if (typeof data.shotType === "string") {
            nextScene.shotType = data.shotType;
          }
          if (typeof data.cameraMove === "string") {
            nextScene.cameraMove = data.cameraMove;
          }
          if (typeof data.durationMs === "number") {
            nextScene.durationMs = data.durationMs;
          }
          if (typeof data.subtitleText === "string") {
            nextScene.subtitleText = data.subtitleText;
          }
          if (typeof data.isLocked === "boolean") {
            nextScene.isLocked = data.isLocked;
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
          if (typeof data.videoStatus === "string") {
            nextScene.video.status = data.videoStatus;
          }
          if (typeof data.videoProgress === "number") {
            nextScene.video.progress = data.videoProgress;
          }
          if ("videoUrl" in data) {
            nextScene.video.url = data.videoUrl ?? null;
          }
          if (typeof data.errorMsg === "string") {
            nextScene.errorMessage = data.errorMsg;
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
                  ? // Through normalize so a cleared speaker ("" on the wire) lands as null
                    // here too, rather than the store and the server disagreeing.
                    normalizeScene({ ...scene, ...patch } as Scene)
                  : scene
              ),
            }
      ),
    }));
  },

  addScene: (scene) => {
    set((state) => ({
      projects: state.projects.map((project) =>
        project.id !== state.selectedProjectId
          ? project
          : {
              ...project,
              episodes: withSceneCount(project.episodes, project.currentEpisodeId, project.scenes.length + 1),
              scenes: normalizeOrder([...project.scenes, normalizeScene(scene)]),
              updatedAt: nowISO(),
            }
      ),
    }));
  },

  removeScene: (sceneId) => {
    set((state) => ({
      projects: state.projects.map((project) => {
        if (project.id !== state.selectedProjectId) return project;
        const scenes = normalizeOrder(project.scenes.filter((scene) => scene.id !== sceneId));
        return {
          ...project,
          episodes: withSceneCount(project.episodes, project.currentEpisodeId, scenes.length),
          scenes,
          updatedAt: nowISO(),
        };
      }),
    }));
  },

  setSceneCast: (sceneId, characterIds) => {
    set((state) => ({
      projects: state.projects.map((project) =>
        project.id !== state.selectedProjectId
          ? project
          : {
              ...project,
              updatedAt: nowISO(),
              scenes: project.scenes.map((scene) =>
                scene.id === sceneId ? { ...scene, characterIds } : scene
              ),
            }
      ),
    }));
  },

  dropCharacter: (characterId) => {
    set((state) => ({
      projects: state.projects.map((project) =>
        project.id !== state.selectedProjectId
          ? project
          : {
              ...project,
              scenes: project.scenes.map((scene) => ({
                ...scene,
                characterIds: scene.characterIds.filter((id) => id !== characterId),
                // The speaker is not part of the cast, so it has to be cleared separately.
                speakerCharacterId:
                  scene.speakerCharacterId === characterId ? null : scene.speakerCharacterId,
              })),
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
