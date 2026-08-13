"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Clapperboard,
  Film,
  Image as ImageIcon,
  LayoutDashboard,
  LogOut,
  Mic,
  Plus,
  RefreshCw,
  Shield,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  WandSparkles,
} from "lucide-react";
import {
  closestCenter,
  DndContext,
  PointerSensor,
  type DragEndEvent,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";

import {
  createEpisodeAction,
  createProjectSceneAction,
  createProjectAction,
  deleteEpisodeAction,
  deleteProjectSceneAction,
  deleteProjectAction,
  generateProjectAction,
  generateVideoAction,
  getEpisodeAction,
  listCharactersAction,
  listProjectsAction,
  optimizeProjectAction,
  parseProjectAction,
  reorderProjectScenesAction,
  setSceneCastAction,
  updateProjectAction,
  updateProductionSettingsAction,
  updateProjectSceneAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { listUserConfigsAction } from "@/actions/settings-actions";
import { getMeAction } from "@/actions/user-actions";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n";
import { resolveRequestError } from "@/lib/http/errors";
import { configsByPurpose, providerLabel } from "@/lib/model-providers";
import { cn } from "@/lib/utils";
import { useProjectStore, type SceneEdit } from "@/store/project-store";
import { useUserStore } from "@/store/user-store";
import type { UserConfig } from "@/types/auth";
import type {
  EpisodeSummary,
  ProductionSettings,
  ProjectStage,
  ProjectStatus,
  SceneTaskStatus,
  SceneUpdatePayload,
} from "@/types/project";
import { ProductionSettingsForm } from "./production-settings";
import { CharacterPanel } from "./character-panel";
import { SceneCard } from "./scene-card";

type Translate = (key: string, params?: Record<string, string | number>) => string;

const wsBaseURL =
  (process.env.NEXT_PUBLIC_WS_BASE_URL?.trim() || "ws://127.0.0.1:8080").replace(/\/$/, "");

function isTaskStatus(value: unknown): value is SceneTaskStatus | "idle" {
  return (
    value === "idle" || value === "generating" || value === "success" || value === "error"
  );
}

function summarizeActiveConfig(
  config: UserConfig | undefined,
  unconfiguredLabel: string,
  officialLabel: string,
  customLabel: string,
  t: Translate
) {
  if (!config) {
    return unconfiguredLabel;
  }

  return `${config.source === "official" ? officialLabel : customLabel} · ${providerLabel(config.provider, t)} · ${config.modelSeries}`;
}

interface WorkbenchEditorProps {
  projectId?: string;
}

export function WorkbenchEditor({ projectId }: WorkbenchEditorProps) {
  const router = useRouter();
  const { t, formatDateTime } = useI18n();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));
  const wsRef = useRef<WebSocket | null>(null);
  const scriptSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sceneSaveTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [deleteProjectOpen, setDeleteProjectOpen] = useState(false);
  const [videoDialogOpen, setVideoDialogOpen] = useState(false);
  const [videoQuality, setVideoQuality] = useState("");
  const [videoResolution, setVideoResolution] = useState("");
  const [videoFps, setVideoFps] = useState("");
  const [videoDuration, setVideoDuration] = useState(3);
  const [videoPromptExtend, setVideoPromptExtend] = useState(false);
  const [videoSceneIds, setVideoSceneIds] = useState<string[]>([]);
  const [selectedSceneIds, setSelectedSceneIds] = useState<Set<string>>(new Set());
  const [episodeToDelete, setEpisodeToDelete] = useState<EpisodeSummary | null>(null);
  // Set when a reparse would discard rendered shots; the backend held off until the user confirms.
  const [reparsePrompt, setReparsePrompt] = useState<{ discards: number; pending: number } | null>(null);

  const hydrated = useUserStore((state) => state.hydrated);
  const token = useUserStore((state) => state.token);
  const user = useUserStore((state) => state.user);
  const setUser = useUserStore((state) => state.setUser);
  const logout = useUserStore((state) => state.logout);

  const projects = useProjectStore((state) => state.projects);
  const selectedProjectId = useProjectStore((state) => state.selectedProjectId);
  const initialized = useProjectStore((state) => state.initialized);
  const initializeProjects = useProjectStore((state) => state.initializeProjects);
  const selectProject = useProjectStore((state) => state.selectProject);
  const createProject = useProjectStore((state) => state.createProject);
  const removeProject = useProjectStore((state) => state.removeProject);
  const setProjectStatus = useProjectStore((state) => state.setProjectStatus);
  const updateProjectFields = useProjectStore((state) => state.updateProjectFields);
  const applyParsedScenes = useProjectStore((state) => state.applyParsedScenes);
  const applySceneStreamUpdate = useProjectStore((state) => state.applySceneStreamUpdate);
  const updateCurrentScript = useProjectStore((state) => state.updateCurrentScript);
  const updateScene = useProjectStore((state) => state.updateScene);
  const addScene = useProjectStore((state) => state.addScene);
  const removeScene = useProjectStore((state) => state.removeScene);
  const reorderScenes = useProjectStore((state) => state.reorderScenes);
  const openEpisode = useProjectStore((state) => state.openEpisode);
  const upsertEpisode = useProjectStore((state) => state.upsertEpisode);
  const removeEpisode = useProjectStore((state) => state.removeEpisode);
  const setSceneCast = useProjectStore((state) => state.setSceneCast);
  const dropCharacter = useProjectStore((state) => state.dropCharacter);

  const currentProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId),
    [projects, selectedProjectId]
  );

  const episodes = currentProject?.episodes ?? [];
  const currentEpisodeId = currentProject?.currentEpisodeId ?? null;
  const currentEpisode = episodes.find((episode) => episode.id === currentEpisodeId) ?? null;

  const meQuery = useQuery({
    queryKey: queryKeys.me,
    queryFn: getMeAction,
    enabled: hydrated && Boolean(token),
  });

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: listProjectsAction,
    enabled: hydrated && Boolean(token) && !initialized,
    staleTime: 300_000,
  });

  const userConfigsQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
    enabled: hydrated && Boolean(token),
    staleTime: 30_000,
  });

  // Shares a cache entry with the character panel, which owns the writes.
  const charactersQuery = useQuery({
    queryKey: queryKeys.characters(selectedProjectId),
    queryFn: () => listCharactersAction(selectedProjectId),
    enabled: hydrated && Boolean(token) && Boolean(selectedProjectId),
  });
  const characters = useMemo(() => charactersQuery.data?.characters ?? [], [charactersQuery.data?.characters]);

  const activeUserConfigByPurpose = useMemo(
    () =>
      configsByPurpose(userConfigsQuery.data?.configs ?? [], (config) => {
        const isUsableActiveConfig =
          config.isActive && config.modelSeries.trim().length > 0;
        return isUsableActiveConfig;
      }),
    [userConfigsQuery.data?.configs]
  );
  const officialConfigByPurpose = useMemo(
    () =>
      configsByPurpose(userConfigsQuery.data?.officialConfigs ?? [], (config) => {
        const isUsableActiveConfig =
          config.isActive && config.modelSeries.trim().length > 0;
        return isUsableActiveConfig;
      }),
    [userConfigsQuery.data?.officialConfigs]
  );
  const activeConfigByPurpose = useMemo(
    () => ({ ...officialConfigByPurpose, ...activeUserConfigByPurpose }),
    [activeUserConfigByPurpose, officialConfigByPurpose]
  );
  const activeScriptConfig = activeConfigByPurpose.script;
  const activeImageConfig = activeConfigByPurpose.image;
  const activeVideoConfig = activeConfigByPurpose.video;
  const activeAudioConfig = activeConfigByPurpose.audio;
  const hasUsableScriptConfig = Boolean(activeScriptConfig);
  const hasUsableImageConfig = Boolean(activeImageConfig);

  const parseProjectMutation = useMutation({
    mutationFn: (params: {
      projectId: string;
      script: string;
      model?: string;
      episodeId?: string;
      replaceAll?: boolean;
    }) =>
      parseProjectAction(params.projectId, {
        script: params.script,
        model: params.model,
        episodeId: params.episodeId,
        replaceAll: params.replaceAll,
      }),
    onMutate: ({ projectId }) => {
      setStatusMessage(null);
      setProjectStatus(projectId, "parsing");
    },
    onSuccess: (response) => {
      if (!response.applied) {
        setProjectStatus(response.projectId, "idle");
        setReparsePrompt({
          discards: response.discardsGeneratedScenes,
          pending: response.pendingScenes.length,
        });
        return;
      }

      setReparsePrompt(null);
      applyParsedScenes(
        response.projectId,
        response.status,
        response.scenes,
        response.source,
        response.warning
      );

      if (response.warning) {
        setStatusMessage(response.warning);
      } else if (response.source === "llm") {
        setStatusMessage(t("home.status.parsingDoneLlm"));
      } else {
        setStatusMessage(t("home.status.parsingDoneFallback"));
      }
    },
    onError: (error, variables) => {
      setProjectStatus(variables.projectId, "idle");
      setStatusMessage(resolveRequestError(error, t("home.status.parseFailed")));
    },
  });

  const createProjectMutation = useMutation({
    mutationFn: () => createProjectAction({ title: `${t("home.newProject")} ${projects.length + 1}` }),
    onSuccess: (response) => {
      createProject(response.project);
      router.push(`/projects/${response.project.id}`);
      setStatusMessage(null);
    },
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, t("home.createProjectFailed")));
    },
  });

  const updateProjectMutation = useMutation({
    mutationFn: (params: { projectId: string; originalScript: string }) =>
      updateProjectAction(params.projectId, { originalScript: params.originalScript }),
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, t("home.saveProjectFailed")));
    },
  });

  const updateProductionSettingsMutation = useMutation({
    mutationFn: (params: { projectId: string; settings: ProductionSettings }) =>
      updateProductionSettingsAction(params.projectId, params.settings),
    onSuccess: (response) => {
      updateProjectFields(response.project.id, {
        productionSettings: response.project.productionSettings,
        currentStage: response.project.currentStage,
      });
      setStatusMessage(t("home.productionSettingsSaved"));
    },
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, t("home.productionSettingsFailed")));
    },
  });

  const updateSceneMutation = useMutation({
    mutationFn: (params: { projectId: string; sceneId: string; patch: SceneEdit }) =>
      updateProjectSceneAction(params.projectId, params.sceneId, params.patch),
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, t("home.saveSceneFailed")));
    },
  });

  const reorderScenesMutation = useMutation({
    mutationFn: (params: { projectId: string; sceneIds: string[]; episodeId?: string }) =>
      reorderProjectScenesAction(params.projectId, {
        sceneIds: params.sceneIds,
        episodeId: params.episodeId,
      }),
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, t("home.reorderScenesFailed")));
    },
  });

  const setSceneCastMutation = useMutation({
    mutationFn: (params: { projectId: string; sceneId: string; characterIds: string[]; previous: string[] }) =>
      setSceneCastAction(params.projectId, params.sceneId, { characterIds: params.characterIds }),
    onSuccess: (response) => {
      setSceneCast(response.sceneId, response.characterIds);
    },
    onError: (error, variables) => {
      // The toggle already landed optimistically, so roll it back to what the server has.
      setSceneCast(variables.sceneId, variables.previous);
      setStatusMessage(resolveRequestError(error, t("scene.castFailed")));
    },
  });

  const openEpisodeMutation = useMutation({    mutationFn: (params: { projectId: string; episodeId: string }) =>
      getEpisodeAction(params.projectId, params.episodeId),
    onSuccess: (response, variables) => {
      openEpisode(variables.projectId, response.episode.id, response.episode.scenes);
      setStatusMessage(null);
    },
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, t("home.episodeLoadFailed")));
    },
  });

  const addEpisodeMutation = useMutation({
    mutationFn: (projectId: string) => createEpisodeAction(projectId, {}),
    onSuccess: (response, projectId) => {
      // A new episode is empty, so switching to it needs no extra fetch.
      upsertEpisode(projectId, response.episode);
      openEpisode(projectId, response.episode.id, []);
      setStatusMessage(t("home.episodeAdded", { title: response.episode.title }));
    },
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, t("home.episodeAddFailed")));
    },
  });

  const deleteEpisodeMutation = useMutation({
    mutationFn: (params: { projectId: string; episodeId: string }) =>
      deleteEpisodeAction(params.projectId, params.episodeId),
    onSuccess: (_, variables) => {
      setEpisodeToDelete(null);
      removeEpisode(variables.projectId, variables.episodeId);
      // The store fell back to the newest remaining episode but has none of its shots.
      const fallback = useProjectStore
        .getState()
        .projects.find((project) => project.id === variables.projectId)?.currentEpisodeId;
      if (fallback) {
        openEpisodeMutation.mutate({ projectId: variables.projectId, episodeId: fallback });
      }
      setStatusMessage(t("home.episodeDeleted"));
    },
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, t("home.episodeDeleteFailed")));
    },
  });

  const generateProjectMutation = useMutation({
    mutationFn: (params: { projectId: string; model?: string; episodeId?: string; media: "image" | "audio"; sceneIds: string[] }) =>
      generateProjectAction(params.projectId, {
        model: params.model,
        episodeId: params.episodeId,
        media: params.media,
        sceneIds: params.sceneIds,
      }),
    onMutate: ({ projectId }) => {
      setStatusMessage(null);
      setProjectStatus(projectId, "generating");
    },
    onSuccess: () => {
      setStatusMessage(t("home.status.generateStarted"));
    },
    onError: (error, variables) => {
      setProjectStatus(variables.projectId, "idle");
      setStatusMessage(resolveRequestError(error, t("home.status.generateFailed")));
    },
  });

  const optimizeProjectMutation = useMutation({
    mutationFn: (params: { projectId: string; script: string; model?: string }) =>
      optimizeProjectAction(params.projectId, {
        script: params.script,
        model: params.model,
      }),
    onMutate: () => {
      setStatusMessage(null);
    },
    onSuccess: (response, variables) => {
      // Only the script changed. Forcing status back to idle here used to hide a run that
      // was still in flight.
      updateProjectFields(variables.projectId, {
        originalScript: response.optimizedScript,
      });

      if (response.warning) {
        setStatusMessage(
          t("home.status.optimizeDoneWithWarning", {
            source: response.source,
            warning: response.warning,
          })
        );
      } else {
        setStatusMessage(t("home.status.optimizeDone", { source: response.source.toUpperCase() }));
      }
    },
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, t("home.status.optimizeFailed")));
    },
  });

  const generateVideoMutation = useMutation({
    mutationFn: (params: {
      projectId: string;
      model?: string;
      episodeId?: string;
      quality?: string;
      resolution?: string;
      fps?: number;
      duration: number;
      promptExtend: boolean;
      sceneIds: string[];
    }) => generateVideoAction(params.projectId, {
      model: params.model,
      episodeId: params.episodeId,
      quality: params.quality,
      resolution: params.resolution,
      fps: params.fps,
      duration: params.duration,
      promptExtend: params.promptExtend,
      sceneIds: params.sceneIds,
    }),
    onMutate: ({ projectId }) => {
      setStatusMessage(null);
      updateProjectFields(projectId, {
        status: "video_generating",
        videoStatus: "generating",
        videoProgress: 0,
      });
    },
    onSuccess: () => {
      setVideoDialogOpen(false);
      setVideoSceneIds([]);
      setStatusMessage(t("home.status.videoStarted"));
    },
    onError: (error, variables) => {
      updateProjectFields(variables.projectId, {
        status: "idle",
        videoStatus: "idle",
        videoProgress: 0,
      });
      setStatusMessage(resolveRequestError(error, t("home.status.videoFailed")));
    },
  });

  const deleteProjectMutation = useMutation({
    mutationFn: (projectId: string) => deleteProjectAction(projectId),
    onMutate: () => {
      setStatusMessage(null);
    },
    onSuccess: (_, projectId) => {
      setDeleteProjectOpen(false);
      removeProject(projectId);
      router.push("/");
      setStatusMessage(t("home.status.projectDeleted"));
    },
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, t("home.status.deleteFailed")));
    },
  });

  const createSceneMutation = useMutation({
    mutationFn: (params: { projectId: string; episodeId?: string }) =>
      createProjectSceneAction(params.projectId, { episodeId: params.episodeId }),
    onSuccess: (response) => {
      addScene(response.scene);
      setStatusMessage(t("scene.added"));
    },
    onError: (error) => setStatusMessage(resolveRequestError(error, t("scene.addFailed"))),
  });

  const deleteSceneMutation = useMutation({
    mutationFn: (params: { projectId: string; sceneId: string }) =>
      deleteProjectSceneAction(params.projectId, params.sceneId),
    onSuccess: (_, variables) => {
      removeScene(variables.sceneId);
      setSelectedSceneIds((selected) => {
        const next = new Set(selected);
        next.delete(variables.sceneId);
        return next;
      });
      setStatusMessage(t("scene.deleted"));
    },
    onError: (error) => setStatusMessage(resolveRequestError(error, t("scene.deleteFailed"))),
  });

  useEffect(() => {
    if (!meQuery.data?.user) {
      return;
    }

    setUser(meQuery.data.user);
  }, [meQuery.data?.user, setUser]);

  useEffect(() => {
    if (!hydrated) {
      return;
    }

    if (!token) {
      router.replace("/login");
      return;
    }

    if (!meQuery.isError) {
      return;
    }

    logout();
    router.replace("/login");
  }, [hydrated, token, meQuery.isError, logout, router]);

  useEffect(() => {
    if (!projectsQuery.data?.projects) {
      return;
    }

    initializeProjects(projectsQuery.data.projects);
  }, [initializeProjects, projectsQuery.data?.projects]);

  useEffect(() => {
    if (!projectId || !initialized || selectedProjectId === projectId) {
      return;
    }

    if (projects.some((project) => project.id === projectId)) {
      selectProject(projectId);
    }
  }, [initialized, projectId, projects, selectProject, selectedProjectId]);

  useEffect(() => {
    if (!hydrated || !token || !selectedProjectId) {
      return;
    }

    const wsURL = `${wsBaseURL}/ws/projects/${selectedProjectId}`;
    const socket = new WebSocket(wsURL, [`sceneflow-auth.${token}`]);
    wsRef.current = socket;

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          type?: string;
          projectId?: string;
          sceneId?: string;
          data?: Record<string, unknown>;
        };

        if (!payload.projectId || payload.projectId !== selectedProjectId) {
          return;
        }

        if (payload.type === "PROJECT_UPDATE") {
          const status = payload.data?.status;
          const warning = payload.data?.warning;
          const optimizedScript = payload.data?.optimizedScript;
          const videoStatus = payload.data?.videoStatus;
          const videoProgress = payload.data?.videoProgress;
          const videoUrl = payload.data?.videoUrl;
          const productionSettings = payload.data?.productionSettings;
          const currentStage = payload.data?.currentStage;

          if (typeof status === "string") {
            setProjectStatus(payload.projectId, status as ProjectStatus);
          }

          const patch: Parameters<typeof updateProjectFields>[1] = {};
          if (typeof optimizedScript === "string") {
            patch.originalScript = optimizedScript;
          }
          if (isTaskStatus(videoStatus)) {
            patch.videoStatus = videoStatus;
          }
          if (typeof videoProgress === "number") {
            patch.videoProgress = videoProgress;
          }
          if (typeof videoUrl === "string") {
            patch.videoUrl = videoUrl;
          }
          if (productionSettings && typeof productionSettings === "object") {
            patch.productionSettings = productionSettings as ProductionSettings;
          }
          if (typeof currentStage === "string") {
            patch.currentStage = currentStage as ProjectStage;
          }
          if (Object.keys(patch).length > 0) {
            updateProjectFields(payload.projectId, patch);
          }

          if (typeof warning === "string" && warning.trim()) {
            setStatusMessage(warning);
          }

          if (status === "done") {
            setStatusMessage(t("home.status.generationDone"));
          }

          if (status === "partial") {
            setStatusMessage(t("home.status.generationPartial"));
          }

          if (status === "failed") {
            setStatusMessage(t("home.status.generationFailed"));
          }

          if (videoStatus === "success") {
            setStatusMessage(t("home.status.videoDone"));
          }

          return;
        }

        if (payload.type === "VIDEO_UPDATE") {
          const videoStatus = payload.data?.videoStatus;
          const videoProgress = payload.data?.videoProgress;
          const videoUrl = payload.data?.videoUrl;

          const patch: Parameters<typeof updateProjectFields>[1] = {};
          if (isTaskStatus(videoStatus)) {
            patch.videoStatus = videoStatus;
          }
          if (typeof videoProgress === "number") {
            patch.videoProgress = videoProgress;
          }
          if (typeof videoUrl === "string") {
            patch.videoUrl = videoUrl;
          }
          if (Object.keys(patch).length > 0) {
            updateProjectFields(payload.projectId, patch);
          }

          return;
        }

        if (payload.type === "PROJECT_DELETED") {
          removeProject(payload.projectId);
          setStatusMessage(t("home.status.currentProjectDeleted"));
          return;
        }

        if (payload.type === "SCENE_DELETED" && payload.sceneId) {
          removeScene(payload.sceneId);
          return;
        }

        if (payload.type === "SCENE_UPDATE" && payload.sceneId) {
          applySceneStreamUpdate(payload.projectId, payload.sceneId, payload.data as SceneUpdatePayload);
        }
      } catch {
        // Ignore malformed messages.
      }
    };

    return () => {
      socket.close();
      wsRef.current = null;
    };
  }, [
    hydrated,
    token,
    selectedProjectId,
    applySceneStreamUpdate,
    setProjectStatus,
    updateProjectFields,
    removeProject,
    removeScene,
    t,
  ]);

  useEffect(() => {
    const sceneSaveTimers = sceneSaveTimersRef.current;
    return () => {
      if (scriptSaveTimerRef.current) {
        clearTimeout(scriptSaveTimerRef.current);
      }
      Object.values(sceneSaveTimers).forEach(clearTimeout);
    };
  }, []);

  const saveCurrentScript = (value: string) => {
    if (!currentProject) {
      return;
    }
    updateCurrentScript(value);
    if (scriptSaveTimerRef.current) {
      clearTimeout(scriptSaveTimerRef.current);
    }
    const projectId = currentProject.id;
    scriptSaveTimerRef.current = setTimeout(() => {
      updateProjectMutation.mutate({ projectId, originalScript: value });
    }, 500);
  };

  const openVideoDialog = (sceneIds?: string[]) => {
    const capabilities = activeVideoConfig?.videoCapabilities;
    if (!capabilities) return;
    const unlockedIds = sceneIds?.filter(
      (sceneId) => !currentProject?.scenes.find((scene) => scene.id === sceneId)?.isLocked
    ) ?? [];
    if (sceneIds && unlockedIds.length === 0) return;
    setVideoSceneIds(unlockedIds);
    setVideoQuality(capabilities.qualities[0] ?? "");
    setVideoResolution(capabilities.resolutions[0] ?? "");
    setVideoFps(capabilities.fps[0] ? String(capabilities.fps[0]) : "");
    setVideoDuration(capabilities.minDuration);
    setVideoPromptExtend(false);
    setVideoDialogOpen(true);
  };

  const generateScenes = (media: "image" | "audio", sceneIds: string[]) => {
    if (!currentProject) return;
    const unlockedIds = sceneIds.filter(
      (sceneId) => !currentProject.scenes.find((scene) => scene.id === sceneId)?.isLocked
    );
    if (unlockedIds.length === 0) return;
    generateProjectMutation.mutate({
      projectId: currentProject.id,
      model: media === "image" ? activeImageConfig?.modelSeries : activeAudioConfig?.modelSeries,
      episodeId: currentProject.currentEpisodeId ?? undefined,
      media,
      sceneIds: unlockedIds,
    });
  };

  const selectedScenes = currentProject?.scenes.filter((scene) => selectedSceneIds.has(scene.id)) ?? [];
  const failedSceneIds = (media: "image" | "audio" | "video") =>
    currentProject?.scenes.filter((scene) => scene[media].status === "error").map((scene) => scene.id) ?? [];
  const generationBusy = Boolean(
    currentProject && ["parsing", "generating", "video_generating"].includes(currentProject.status)
  );

  const saveScenePatch = (sceneId: string, patch: SceneEdit) => {
    if (!currentProject) {
      return;
    }
    updateScene(sceneId, patch);
    const projectId = currentProject.id;
    const key = `${projectId}:${sceneId}`;
    if (sceneSaveTimersRef.current[key]) {
      clearTimeout(sceneSaveTimersRef.current[key]);
    }
    sceneSaveTimersRef.current[key] = setTimeout(() => {
      updateSceneMutation.mutate({ projectId, sceneId, patch });
      delete sceneSaveTimersRef.current[key];
    }, 500);
  };

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) {
      return;
    }

    reorderScenes(String(active.id), String(over.id));
    const nextProject = useProjectStore.getState().projects.find((project) => project.id === selectedProjectId);
    if (nextProject) {
      reorderScenesMutation.mutate({
        projectId: nextProject.id,
        sceneIds: nextProject.scenes.map((scene) => scene.id),
        episodeId: nextProject.currentEpisodeId ?? undefined,
      });
    }
  };

  if (!hydrated) {
    return <main className="flex min-h-screen items-center justify-center">{t("common.initializing")}</main>;
  }

  if (!token) {
    return <main className="flex min-h-screen items-center justify-center">{t("common.redirectingToLogin")}</main>;
  }

  if (!currentProject && !projectsQuery.isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <Button onClick={() => createProjectMutation.mutate()} disabled={createProjectMutation.isPending}>
          {t("common.createFirstProject")}
        </Button>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="flex min-h-screen flex-col md:flex-row">
        <aside className="flex w-full shrink-0 flex-col border-b border-border/70 bg-card/60 md:w-[300px] md:border-b-0 md:border-r">
          <div className="space-y-3 p-4">
            <div className="flex items-center gap-2">
              <div className="rounded-lg bg-primary/20 p-2 text-primary">
                <Clapperboard className="size-4" />
              </div>
              <div>
                <p className="text-sm font-semibold">SceneFlow</p>
                <p className="text-xs text-muted-foreground">{t("home.brandSubtitle")}</p>
              </div>
            </div>

            <Button
              className="w-full justify-start"
              onClick={() => createProjectMutation.mutate()}
              disabled={createProjectMutation.isPending}
            >
              <Plus className="mr-2 size-4" />
              {t("home.newProject")}
            </Button>
          </div>

          <div className="space-y-1 px-3 pb-3">
            <p className="px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("home.businessCenter")}</p>
            <button
              type="button"
              onClick={() => router.push("/")}
              className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm text-muted-foreground hover:bg-muted/60"
            >
              <LayoutDashboard className="size-4" />
              {t("home.backToProjectList")}
            </button>

            <div className="pt-3">
              <p className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("home.adminCenter")}</p>
              <button
                type="button"
                onClick={() => router.push("/admin/models")}
                className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm text-muted-foreground hover:bg-muted/60"
              >
                <SlidersHorizontal className="size-4" />
                {t("home.modelManagement")}
              </button>
              {user?.role === "superAdmin" ? (
                <button
                  type="button"
                  onClick={() => router.push("/admin/users")}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm text-muted-foreground hover:bg-muted/60"
                >
                  <Shield className="size-4" />
                  {t("home.userManagement")}
                </button>
              ) : null}
            </div>
          </div>

          <Separator />

          <div className="flex-1 space-y-2 overflow-y-auto px-3 py-4">
            <p className="px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("home.projectList")}</p>

            {projectsQuery.isLoading && projects.length === 0 ? (
              <div className="space-y-2 px-1">
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-4/5" />
              </div>
            ) : null}

            {projects.map((project, index) => {
              const isActive = project.id === currentProject?.id;

              return (
                <button
                  key={project.id}
                  type="button"
                  onClick={() => {
                    selectProject(project.id);
                    router.push(`/projects/${project.id}`);
                  }}
                  className={cn(
                    "animate-in fade-in-0 slide-in-from-left-1 w-full rounded-lg border border-transparent px-3 py-2 text-left transition duration-300",
                    isActive
                      ? "border-primary/30 bg-primary/10"
                      : "bg-background/50 hover:border-border/80 hover:bg-background"
                  )}
                  style={{ animationDelay: `${index * 40}ms` }}
                >
                  <p className="truncate text-sm font-medium">{project.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t("home.scenesCount", {
                      count: project.scenes.length,
                      time: formatDateTime(project.updatedAt),
                    })}
                  </p>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="flex min-w-0 flex-1 flex-col">
          <header className="border-b border-border/70 bg-card/60">
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 md:px-6">
              <div>
                <p className="text-base font-semibold">{currentProject?.title ?? t("home.projectTitleLoading")}</p>
                <p className="text-xs text-muted-foreground">
                  {t("common.currentUser", {
                    username: meQuery.isLoading ? t("common.loading") : user?.nickname || user?.username || t("common.unknownUser"),
                  })}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <PreferencesSwitcher />

                <Button
                  variant="secondary"
                  onClick={() => {
                    logout();
                    router.replace("/login");
                  }}
                >
                  <LogOut className="mr-2 size-4" />
                  {t("common.logout")}
                </Button>
              </div>
            </div>
          </header>

          <div className="grid flex-1 gap-6 p-4 md:p-6 xl:grid-cols-[360px_minmax(0,1fr)]">
            <Card className="h-fit border-border/80">
              <CardHeader>
                <CardTitle className="text-base">{t("home.scriptInput")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {currentProject ? (
                  <ProductionSettingsForm
                    key={currentProject.id}
                    settings={currentProject.productionSettings}
                    disabled={updateProductionSettingsMutation.isPending}
                    onSave={(settings) =>
                      updateProductionSettingsMutation.mutate({
                        projectId: currentProject.id,
                        settings,
                      })
                    }
                  />
                ) : null}

                <div className="grid gap-2 rounded-lg border border-border/80 bg-muted/30 p-3 text-xs text-muted-foreground sm:grid-cols-2">
                  <p>
                    {t("home.scriptConfigSummary", {
                      value: summarizeActiveConfig(
                        activeScriptConfig,
                        t("settings.unconfigured"),
                        t("settings.officialConfig"),
                        t("settings.customConfig"),
                        t
                      ),
                    })}
                  </p>
                  <p>
                    {t("home.imageConfigSummary", {
                      value: summarizeActiveConfig(
                        activeImageConfig,
                        t("settings.unconfigured"),
                        t("settings.officialConfig"),
                        t("settings.customConfig"),
                        t
                      ),
                    })}
                  </p>
                  <p>
                    {t("home.videoConfigSummary", {
                      value: summarizeActiveConfig(
                        activeVideoConfig,
                        t("settings.unconfigured"),
                        t("settings.officialConfig"),
                        t("settings.customConfig"),
                        t
                      ),
                    })}
                  </p>
                  <p>
                    {t("home.audioConfigSummary", {
                      value: activeAudioConfig
                        ? summarizeActiveConfig(
                            activeAudioConfig,
                            t("settings.unconfigured"),
                            t("settings.officialConfig"),
                            t("settings.customConfig"),
                            t
                          )
                        : t("settings.builtinSystemTts"),
                    })}
                  </p>
                </div>

                <Textarea
                  value={currentProject?.originalScript ?? ""}
                  onChange={(event) => saveCurrentScript(event.target.value)}
                  placeholder={t("home.storyPlaceholder")}
                  className="min-h-[300px]"
                  disabled={!currentProject}
                />

                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Badge variant="secondary">
                    {t("home.status", { status: currentProject?.status ?? "loading" })}
                  </Badge>

                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      onClick={() => {
                        if (!currentProject) {
                          return;
                        }

                        optimizeProjectMutation.mutate({
                          projectId: currentProject.id,
                          script: currentProject.originalScript,
                          model: activeScriptConfig?.modelSeries,
                        });
                      }}
                      disabled={
                        !currentProject ||
                        !hasUsableScriptConfig ||
                        optimizeProjectMutation.isPending ||
                        currentProject.originalScript.trim().length === 0
                      }
                    >
                      <Sparkles className="mr-2 size-4" />
                      {optimizeProjectMutation.isPending ? t("home.optimizingScript") : t("home.optimizeScript")}
                    </Button>

                    <Button
                      variant="outline"
                      onClick={() => {
                        if (!currentProject) {
                          return;
                        }

                        parseProjectMutation.mutate({
                          projectId: currentProject.id,
                          script: currentProject.originalScript,
                          model: activeScriptConfig?.modelSeries,
                          episodeId: currentProject.currentEpisodeId ?? undefined,
                        });
                      }}
                      disabled={!currentProject || !hasUsableScriptConfig || currentProject.status === "parsing"}
                    >
                      <WandSparkles className="mr-2 size-4" />
                      {currentProject?.status === "parsing" ? t("home.parsingScenes") : t("home.generateStoryboard")}
                    </Button>

                    <Button
                      variant="outline"
                      onClick={() => {
                        if (!currentProject || deleteProjectMutation.isPending) {
                          return;
                        }
                        setDeleteProjectOpen(true);
                      }}
                      disabled={!currentProject || deleteProjectMutation.isPending}
                    >
                      <Trash2 className="mr-2 size-4" />
                      {deleteProjectMutation.isPending ? t("home.deletingProject") : t("home.deleteProject")}
                    </Button>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">
                    {t("home.videoStatus", { status: currentProject?.videoStatus ?? "idle" })}
                  </Badge>
                  <Badge variant="outline">
                    {t("home.videoProgress", { progress: currentProject?.videoProgress ?? 0 })}
                  </Badge>
                </div>

                {currentProject?.videoUrl ? (
                  <a
                    href={currentProject.videoUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center text-xs text-primary underline-offset-4 hover:underline"
                  >
                    {t("home.openVideoLink")}
                  </a>
                ) : null}

                {!hasUsableScriptConfig ? (
                  <p className="text-xs text-amber-600">
                    {t("home.scriptRequiredHint")}
                  </p>
                ) : null}

                {statusMessage ? <p className="text-xs text-muted-foreground">{statusMessage}</p> : null}
              </CardContent>
            </Card>

            {currentProject ? (
              <CharacterPanel
                projectId={currentProject.id}
                onStatus={setStatusMessage}
                onCharacterDeleted={dropCharacter}
              />
            ) : null}

            <Card className="min-h-[500px] border-border/80">
              <CardHeader className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-base">{t("home.sceneFlowTitle")}</CardTitle>
                  {currentEpisode ? (
                    <span className="text-xs text-muted-foreground">
                      {t("home.episodeShotCount", { count: currentProject?.scenes.length ?? 0 })}
                    </span>
                  ) : null}
                </div>

                <div className="flex flex-wrap items-center gap-2 border-t border-border/60 pt-3">
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={Boolean(currentProject?.scenes.length) && selectedScenes.length === currentProject?.scenes.length}
                      onChange={(event) =>
                        setSelectedSceneIds(
                          event.target.checked
                            ? new Set(currentProject?.scenes.map((scene) => scene.id) ?? [])
                            : new Set()
                        )
                      }
                      className="size-4 accent-primary"
                    />
                    {t("scene.selectAll")}
                  </label>
                  <Badge variant="outline">{t("scene.selectedCount", { count: selectedScenes.length })}</Badge>
                  <Button size="sm" onClick={() => generateScenes("image", selectedScenes.map((scene) => scene.id))} disabled={generationBusy || !hasUsableImageConfig || selectedScenes.length === 0}>
                    <ImageIcon />
                    {t("scene.generateSelectedImages")}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => generateScenes("audio", selectedScenes.map((scene) => scene.id))} disabled={generationBusy || selectedScenes.length === 0}>
                    <Mic />
                    {t("scene.generateSelectedAudio")}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => openVideoDialog(selectedScenes.map((scene) => scene.id))} disabled={generationBusy || !activeVideoConfig?.videoCapabilities || selectedScenes.length === 0}>
                    <Film />
                    {t("scene.generateSelectedVideo")}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => generateScenes("image", failedSceneIds("image"))} disabled={generationBusy || !hasUsableImageConfig || failedSceneIds("image").length === 0}>
                    <RefreshCw />
                    {t("scene.retryFailedImages")}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => generateScenes("audio", failedSceneIds("audio"))} disabled={generationBusy || failedSceneIds("audio").length === 0}>
                    <RefreshCw />
                    {t("scene.retryFailedAudio")}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => openVideoDialog(failedSceneIds("video"))} disabled={generationBusy || !activeVideoConfig?.videoCapabilities || failedSceneIds("video").length === 0}>
                    <RefreshCw />
                    {t("scene.retryFailedVideo")}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => currentProject && createSceneMutation.mutate({ projectId: currentProject.id, episodeId: currentProject.currentEpisodeId ?? undefined })} disabled={!currentProject || generationBusy || createSceneMutation.isPending}>
                    <Plus />
                    {t("scene.add")}
                  </Button>
                </div>

                {/* Shots below belong to the selected episode only, so the switcher sits with them. */}
                <div className="flex flex-wrap items-center gap-2">
                  {episodes.map((episode) => (
                    <Button
                      key={episode.id}
                      size="sm"
                      variant={episode.id === currentEpisodeId ? "default" : "outline"}
                      onClick={() => {
                        if (!currentProject || episode.id === currentEpisodeId) {
                          return;
                        }
                        openEpisodeMutation.mutate({ projectId: currentProject.id, episodeId: episode.id });
                      }}
                      disabled={openEpisodeMutation.isPending}
                    >
                      {episode.title}
                      <Badge variant="secondary" className="ml-2">
                        {episode.sceneCount}
                      </Badge>
                    </Button>
                  ))}

                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      if (currentProject) {
                        addEpisodeMutation.mutate(currentProject.id);
                      }
                    }}
                    disabled={!currentProject || addEpisodeMutation.isPending}
                  >
                    <Plus className="mr-1 size-4" />
                    {t("home.addEpisode")}
                  </Button>

                  {currentEpisode ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-muted-foreground"
                      onClick={() => setEpisodeToDelete(currentEpisode)}
                      disabled={deleteEpisodeMutation.isPending}
                    >
                      <Trash2 className="mr-1 size-4" />
                      {t("home.deleteEpisode")}
                    </Button>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent>
                {!currentProject ? (
                  <div className="space-y-3">
                    <Skeleton className="h-40 w-full" />
                    <Skeleton className="h-40 w-full" />
                  </div>
                ) : openEpisodeMutation.isPending ? (
                  <div className="space-y-3">
                    <Skeleton className="h-40 w-full" />
                    <Skeleton className="h-40 w-full" />
                  </div>
                ) : currentProject.scenes.length === 0 ? (
                  <p className="py-14 text-center text-sm text-muted-foreground">{t("home.noScenes")}</p>
                ) : (
                  <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                    <SortableContext
                      items={currentProject.scenes.map((scene) => scene.id)}
                      strategy={verticalListSortingStrategy}
                    >
                      <div className="space-y-3">
                        {currentProject.scenes.map((scene, index) => (
                          <div
                            key={scene.id}
                            className="animate-in fade-in-0 slide-in-from-bottom-1 duration-300"
                            style={{ animationDelay: `${index * 45}ms` }}
                          >
                            <SceneCard
                              scene={scene}
                              characters={characters}
                              selected={selectedSceneIds.has(scene.id)}
                              disabled={generationBusy}
                              onSelectedChange={(selected) => setSelectedSceneIds((current) => {
                                const next = new Set(current);
                                if (selected) next.add(scene.id); else next.delete(scene.id);
                                return next;
                              })}
                              onGenerate={(media) => {
                                if (media === "video") openVideoDialog([scene.id]);
                                else generateScenes(media, [scene.id]);
                              }}
                              onDelete={() => {
                                if (window.confirm(t("scene.deleteConfirm", { order: scene.order }))) {
                                  deleteSceneMutation.mutate({ projectId: currentProject.id, sceneId: scene.id });
                                }
                              }}
                              onNarrationChange={(value) =>
                                saveScenePatch(scene.id, {
                                  narration: value,
                                })
                              }
                              onPromptChange={(value) =>
                                saveScenePatch(scene.id, {
                                  visualPrompt: value,
                                })
                              }
                              onFieldChange={(patch) => saveScenePatch(scene.id, patch)}
                              onCastChange={(characterIds) => {
                                const previous = scene.characterIds;
                                setSceneCast(scene.id, characterIds);
                                setSceneCastMutation.mutate({
                                  projectId: currentProject.id,
                                  sceneId: scene.id,
                                  characterIds,
                                  previous,
                                });
                              }}
                            />
                          </div>
                        ))}
                      </div>
                    </SortableContext>
                  </DndContext>
                )}
              </CardContent>
            </Card>
          </div>
        </section>
      </div>

      <Dialog
        open={videoDialogOpen}
        onOpenChange={(open) => {
          if (!generateVideoMutation.isPending) setVideoDialogOpen(open);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("home.videoDialogTitle")}</DialogTitle>
            <DialogDescription>
              {t("home.videoDialogSummary", {
                ready: currentProject?.scenes.filter((scene) => scene.image.url).length ?? 0,
                missing: currentProject?.scenes.filter((scene) => !scene.image.url).length ?? 0,
              })}
            </DialogDescription>
          </DialogHeader>
          {activeVideoConfig?.videoCapabilities ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {activeVideoConfig.videoCapabilities.qualities.length ? (
                <div className="space-y-2">
                  <Label>{t("videos.quality")}</Label>
                  <Select value={videoQuality} onValueChange={(value) => setVideoQuality(value ?? "")}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{activeVideoConfig.videoCapabilities.qualities.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              ) : null}
              {activeVideoConfig.videoCapabilities.resolutions.length ? (
                <div className="space-y-2">
                  <Label>{t("videos.resolution")}</Label>
                  <Select value={videoResolution} onValueChange={(value) => setVideoResolution(value ?? "")}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{activeVideoConfig.videoCapabilities.resolutions.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              ) : null}
              {activeVideoConfig.videoCapabilities.fps.length ? (
                <div className="space-y-2">
                  <Label>{t("videos.fps")}</Label>
                  <Select value={videoFps} onValueChange={(value) => setVideoFps(value ?? "")}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{activeVideoConfig.videoCapabilities.fps.map((value) => <SelectItem key={value} value={String(value)}>{value} FPS</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              ) : null}
              <div className="space-y-2">
                <Label>{t("videos.duration")}</Label>
                <Select value={String(videoDuration)} onValueChange={(value) => setVideoDuration(Number(value))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent className="max-h-64">
                    {Array.from({ length: activeVideoConfig.videoCapabilities.maxDuration - activeVideoConfig.videoCapabilities.minDuration + 1 }, (_, index) => activeVideoConfig.videoCapabilities!.minDuration + index).map((value) => <SelectItem key={value} value={String(value)}>{value} s</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              {activeVideoConfig.videoCapabilities.promptExtend ? (
                <label className="flex items-center justify-between gap-3 sm:col-span-2">
                  <span className="text-sm font-medium">{t("videos.promptExtend")}</span>
                  <Switch checked={videoPromptExtend} onCheckedChange={setVideoPromptExtend} />
                </label>
              ) : null}
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setVideoDialogOpen(false)} disabled={generateVideoMutation.isPending}>{t("common.cancel")}</Button>
            <Button
              onClick={() => {
                if (!currentProject || !activeVideoConfig) return;
                generateVideoMutation.mutate({
                  projectId: currentProject.id,
                  model: activeVideoConfig.modelSeries,
                  episodeId: currentProject.currentEpisodeId ?? undefined,
                  quality: videoQuality || undefined,
                  resolution: videoResolution || undefined,
                  fps: videoFps ? Number(videoFps) : undefined,
                  duration: videoDuration,
                  promptExtend: videoPromptExtend,
                  sceneIds: videoSceneIds,
                });
              }}
              disabled={!currentProject || generateVideoMutation.isPending}
            >
              <Film data-icon="inline-start" />
              {generateVideoMutation.isPending ? t("home.generatingVideo") : t("home.generateVideo")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={reparsePrompt !== null}
        onOpenChange={(open) => {
          if (!open && !parseProjectMutation.isPending) setReparsePrompt(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("home.reparseTitle")}</DialogTitle>
            <DialogDescription>
              {t("home.reparseConfirm", {
                count: reparsePrompt?.discards ?? 0,
                pending: reparsePrompt?.pending ?? 0,
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setReparsePrompt(null)}
              disabled={parseProjectMutation.isPending}
            >
              {t("home.reparseKeep")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (!currentProject) return;
                parseProjectMutation.mutate({
                  projectId: currentProject.id,
                  script: currentProject.originalScript,
                  model: activeScriptConfig?.modelSeries,
                  episodeId: currentProject.currentEpisodeId ?? undefined,
                  replaceAll: true,
                });
              }}
              disabled={!currentProject || parseProjectMutation.isPending}
            >
              {t("home.reparseReplace")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteProjectOpen}
        onOpenChange={(open) => {
          if (!deleteProjectMutation.isPending) setDeleteProjectOpen(open);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("home.deleteProject")}</DialogTitle>
            <DialogDescription>
              {t("home.deleteProjectConfirm", { title: currentProject?.title ?? "" })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteProjectOpen(false)}
              disabled={deleteProjectMutation.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (currentProject) deleteProjectMutation.mutate(currentProject.id);
              }}
              disabled={!currentProject || deleteProjectMutation.isPending}
            >
              <Trash2 data-icon="inline-start" />
              {deleteProjectMutation.isPending ? t("home.deletingProject") : t("home.deleteProject")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={Boolean(episodeToDelete)}
        onOpenChange={(open) => {
          if (!open && !deleteEpisodeMutation.isPending) setEpisodeToDelete(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("home.deleteEpisode")}</DialogTitle>
            <DialogDescription>
              {t("home.deleteEpisodeConfirm", {
                title: episodeToDelete?.title ?? "",
                count: episodeToDelete?.sceneCount ?? 0,
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEpisodeToDelete(null)}
              disabled={deleteEpisodeMutation.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (currentProject && episodeToDelete) {
                  deleteEpisodeMutation.mutate({
                    projectId: currentProject.id,
                    episodeId: episodeToDelete.id,
                  });
                }
              }}
              disabled={!currentProject || !episodeToDelete || deleteEpisodeMutation.isPending}
            >
              <Trash2 data-icon="inline-start" />
              {t("home.deleteEpisode")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
