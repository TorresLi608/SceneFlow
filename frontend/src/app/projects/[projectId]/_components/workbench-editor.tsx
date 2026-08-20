"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { isCancel } from "axios";
import {
  ArrowLeft,
  Clapperboard,
  FileText,
  Film,
  Image as ImageIcon,
  Layers,
  LayoutDashboard,
  LogOut,
  Plus,
  RefreshCw,
  Shield,
  SlidersHorizontal,
  Sparkles,
  Square,
  Trash2,
  Users,
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
import { configsByPurpose } from "@/lib/model-providers";
import { cn } from "@/lib/utils";
import { useProjectStore, type SceneEdit } from "@/store/project-store";
import { useUserStore } from "@/store/user-store";
import type {
  EpisodeSummary,
  ProductionSettings,
  ProjectStage,
  ProjectStatus,
  SceneTaskStatus,
  SceneUpdatePayload,
} from "@/types/project";
import { ProductionSettingsForm } from "./production-settings";
import { SceneCard } from "./scene-card";

const wsBaseURL =
  (process.env.NEXT_PUBLIC_WS_BASE_URL?.trim() || "ws://127.0.0.1:8080").replace(/\/$/, "");

function isTaskStatus(value: unknown): value is SceneTaskStatus | "idle" {
  return (
    value === "idle" || value === "generating" || value === "success" || value === "error"
  );
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
  const [videoAspectRatio, setVideoAspectRatio] = useState("");
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
  const hasUsableScriptConfig = Boolean(activeScriptConfig);
  const hasUsableImageConfig = Boolean(activeImageConfig);
  const parseController = useRef<AbortController | null>(null);
  const optimizeController = useRef<AbortController | null>(null);

  const stopParse = (projectId?: string) => {
    parseController.current?.abort();
    parseController.current = null;
    if (projectId) {
      setProjectStatus(projectId, "idle");
    }
    parseProjectMutation.reset();
  };

  const startParse = (params: {
    projectId: string;
    script: string;
    model?: string;
    episodeId?: string;
    replaceAll?: boolean;
  }) => {
    parseController.current = new AbortController();
    parseProjectMutation.mutate(params);
  };

  const stopOptimize = () => {
    optimizeController.current?.abort();
    optimizeController.current = null;
    optimizeProjectMutation.reset();
  };

  const startOptimize = (params: {
    projectId: string;
    script: string;
    model?: string;
  }) => {
    optimizeController.current = new AbortController();
    optimizeProjectMutation.mutate(params);
  };

  const parseProjectMutation = useMutation({
    mutationFn: (params: {
      projectId: string;
      script: string;
      model?: string;
      episodeId?: string;
      replaceAll?: boolean;
    }) =>
      parseProjectAction(
        params.projectId,
        {
          script: params.script,
          model: params.model,
          episodeId: params.episodeId,
          replaceAll: params.replaceAll,
        },
        parseController.current?.signal
      ),
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
      if (isCancel(error)) return;
      setStatusMessage(resolveRequestError(error, t("home.status.parseFailed")));
    },
    onSettled: () => {
      parseController.current = null;
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

  const openEpisodeMutation = useMutation({
    mutationFn: (params: { projectId: string; episodeId: string }) =>
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
    // The episodes section is where episodes are named; this legacy path only needs a
    // placeholder that satisfies the now-required title.
    mutationFn: (projectId: string) =>
      createEpisodeAction(projectId, { title: t("home.episodeLabel", { number: episodes.length + 1 }) }),
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
    mutationFn: (params: { projectId: string; model?: string; episodeId?: string; sceneIds: string[] }) =>
      generateProjectAction(params.projectId, {
        model: params.model,
        episodeId: params.episodeId,
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
      optimizeProjectAction(
        params.projectId,
        {
          script: params.script,
          model: params.model,
        },
        optimizeController.current?.signal
      ),
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
      if (isCancel(error)) return;
      setStatusMessage(resolveRequestError(error, t("home.status.optimizeFailed")));
    },
    onSettled: () => {
      optimizeController.current = null;
    },
  });

  const generateVideoMutation = useMutation({
    mutationFn: (params: {
      projectId: string;
      model?: string;
      episodeId?: string;
      quality?: string;
      aspectRatio?: string;
      fps?: number;
      duration: number;
      promptExtend: boolean;
      sceneIds: string[];
    }) => generateVideoAction(params.projectId, {
      model: params.model,
      episodeId: params.episodeId,
      quality: params.quality,
      aspectRatio: params.aspectRatio,
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
          const title = payload.data?.title;
          const description = payload.data?.description;

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
          if (typeof title === "string") {
            patch.title = title;
          }
          if (typeof description === "string") {
            patch.description = description;
          }
          // Presence, not a type guard: clearing the cover broadcasts an explicit null, and
          // the backend only sends the key when it changed. A typeof check would drop the clear.
          if (payload.data && "coverImageUrl" in payload.data) {
            const cover = payload.data.coverImageUrl;
            patch.coverImageUrl = typeof cover === "string" ? cover : null;
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
    setVideoAspectRatio(capabilities.aspectRatios[0] ?? "");
    setVideoFps(capabilities.fps[0] ? String(capabilities.fps[0]) : "");
    setVideoDuration(capabilities.minDuration);
    setVideoPromptExtend(false);
    setVideoDialogOpen(true);
  };

  const generateScenes = (sceneIds: string[]) => {
    if (!currentProject) return;
    const unlockedIds = sceneIds.filter(
      (sceneId) => !currentProject.scenes.find((scene) => scene.id === sceneId)?.isLocked
    );
    if (unlockedIds.length === 0) return;
    generateProjectMutation.mutate({
      projectId: currentProject.id,
      model: activeImageConfig?.modelSeries,
      episodeId: currentProject.currentEpisodeId ?? undefined,
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
        {/* 左侧工作台导航侧栏 */}
        <aside className="flex w-full shrink-0 flex-col border-b border-border/70 bg-card/60 md:w-[280px] md:border-b-0 md:border-r backdrop-blur-md">
          <div className="space-y-3 p-4">
            <div className="flex items-center gap-2.5">
              <div className="flex size-8 items-center justify-center rounded-xl bg-primary/10 text-primary shadow-inner">
                <Clapperboard className="size-4" />
              </div>
              <div>
                <p className="text-sm font-bold text-foreground">SceneFlow</p>
                <p className="text-[10px] text-muted-foreground">{t("home.brandSubtitle")}</p>
              </div>
            </div>

            <Button
              className="w-full justify-start gap-1.5 h-9 rounded-xl font-semibold shadow-xs cursor-pointer"
              onClick={() => createProjectMutation.mutate()}
              disabled={createProjectMutation.isPending}
            >
              <Plus className="size-4" />
              {t("home.newProject")}
            </Button>
          </div>

          <div className="space-y-1 px-3 pb-3">
            <p className="px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{t("home.businessCenter")}</p>
            <button
              type="button"
              onClick={() => router.push("/ai-script")}
              className="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-xs text-muted-foreground hover:bg-muted/70 hover:text-foreground cursor-pointer transition-colors"
            >
              <LayoutDashboard className="size-3.5" />
              {t("home.backToProjectList")}
            </button>

            <div className="pt-2">
              <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{t("home.adminCenter")}</p>
              <button
                type="button"
                onClick={() => router.push("/admin/models")}
                className="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-xs text-muted-foreground hover:bg-muted/70 hover:text-foreground cursor-pointer transition-colors"
              >
                <SlidersHorizontal className="size-3.5" />
                {t("home.modelManagement")}
              </button>
              {user?.role === "superAdmin" ? (
                <button
                  type="button"
                  onClick={() => router.push("/admin/users")}
                  className="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-xs text-muted-foreground hover:bg-muted/70 hover:text-foreground cursor-pointer transition-colors"
                >
                  <Shield className="size-3.5" />
                  {t("home.userManagement")}
                </button>
              ) : null}
            </div>
          </div>

          <Separator />

          <div className="flex-1 space-y-1.5 overflow-y-auto px-3 py-3">
            <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{t("home.projectList")}</p>

            {projectsQuery.isLoading && projects.length === 0 ? (
              <div className="space-y-2 px-1">
                <Skeleton className="h-14 w-full rounded-xl" />
                <Skeleton className="h-14 w-full rounded-xl" />
                <Skeleton className="h-14 w-4/5 rounded-xl" />
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
                    "animate-in fade-in-0 slide-in-from-left-1 w-full rounded-xl border px-3 py-2 text-left transition duration-200 cursor-pointer",
                    isActive
                      ? "border-primary/40 bg-primary/10 shadow-xs"
                      : "border-transparent bg-background/40 hover:border-border/80 hover:bg-background/80"
                  )}
                  style={{ animationDelay: `${index * 30}ms` }}
                >
                  <p className={cn("truncate text-xs font-semibold", isActive ? "text-primary" : "text-foreground")}>
                    {project.title}
                  </p>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">
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

        {/* 主编辑区 */}
        <section className="flex min-w-0 flex-1 flex-col">
          {/* 工作台顶部工具栏 */}
          <header className="sticky top-0 z-20 border-b border-border/70 bg-card/80 backdrop-blur-md">
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 md:px-6">
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  size="xs"
                  className="h-8 rounded-lg gap-1 px-2 text-xs text-muted-foreground hover:bg-muted cursor-pointer"
                  onClick={() => router.push("/ai-script")}
                >
                  <ArrowLeft className="size-3.5" />
                  <span className="hidden sm:inline">{t("home.aiScript")}</span>
                </Button>
                <div className="h-4 w-px bg-border/80" />
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-foreground">
                      {currentProject?.title ?? t("home.projectTitleLoading")}
                    </p>
                    {currentProject ? (
                      <Badge variant="outline" className="text-[10px] rounded-md px-1.5 py-0">
                        {currentProject.status}
                      </Badge>
                    ) : null}
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    {t("common.currentUser", {
                      username: meQuery.isLoading ? t("common.loading") : user?.nickname || user?.username || t("common.unknownUser"),
                    })}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {currentProject ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 rounded-xl text-xs gap-1.5 cursor-pointer font-medium"
                    render={<Link href={`/projects/${currentProject.id}/characters`} />}
                  >
                    <Users className="size-3.5 text-primary" />
                    {t("workbench.characters")}
                  </Button>
                ) : null}

                <PreferencesSwitcher />

                <Button
                  variant="secondary"
                  size="sm"
                  className="h-8 rounded-xl text-xs gap-1.5 cursor-pointer"
                  onClick={() => {
                    logout();
                    router.replace("/login");
                  }}
                >
                  <LogOut className="size-3.5" />
                  {t("common.logout")}
                </Button>
              </div>
            </div>
          </header>

          <div className="grid flex-1 gap-6 p-4 md:p-6 xl:grid-cols-[400px_minmax(0,1fr)]">
            {/* 左侧：剧本与生产设置 */}
            <div className="space-y-5">
              {/* 剧本输入与处理卡片 */}
              <Card className="rounded-2xl border-border/70 bg-card/75 shadow-sm backdrop-blur-md">
                <CardHeader className="border-b border-border/50 bg-muted/20 px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText className="size-4 text-primary" />
                      <CardTitle className="text-sm font-bold text-foreground">{t("home.scriptInput")}</CardTitle>
                    </div>
                    <Badge variant="secondary" className="rounded-md text-[10px] px-1.5 py-0">
                      {currentProject?.originalScript.trim().length ?? 0} 字
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4 p-4">
                  <Textarea
                    value={currentProject?.originalScript ?? ""}
                    onChange={(event) => saveCurrentScript(event.target.value)}
                    placeholder={t("home.storyPlaceholder")}
                    className="min-h-[260px] resize-none rounded-xl text-xs bg-muted/20 focus-visible:bg-background leading-relaxed"
                    disabled={!currentProject}
                  />

                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Badge variant="outline" className="text-[10px]">
                      {t("home.status", { status: currentProject?.status ?? "loading" })}
                    </Badge>

                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant={optimizeProjectMutation.isPending ? "destructive" : "outline"}
                        onClick={() => {
                          if (!currentProject) {
                            return;
                          }
                          if (optimizeProjectMutation.isPending) {
                            stopOptimize();
                            return;
                          }
                          startOptimize({
                            projectId: currentProject.id,
                            script: currentProject.originalScript,
                            model: activeScriptConfig?.modelSeries,
                          });
                        }}
                        disabled={
                          !currentProject ||
                          !hasUsableScriptConfig ||
                          (currentProject.originalScript.trim().length === 0 && !optimizeProjectMutation.isPending)
                        }
                        className={cn("h-8 rounded-xl text-xs cursor-pointer", optimizeProjectMutation.isPending && "animate-pulse font-medium")}
                      >
                        {optimizeProjectMutation.isPending ? (
                          <Square className="mr-1.5 size-3.5 fill-current" />
                        ) : (
                          <Sparkles className="mr-1.5 size-3.5 text-primary" />
                        )}
                        {optimizeProjectMutation.isPending
                          ? t("home.stopOptimizingScript")
                          : t("home.optimizeScript")}
                      </Button>

                      <Button
                        size="sm"
                        variant={
                          currentProject?.status === "parsing" || parseProjectMutation.isPending
                            ? "destructive"
                            : "outline"
                        }
                        onClick={() => {
                          if (!currentProject) {
                            return;
                          }
                          if (currentProject.status === "parsing" || parseProjectMutation.isPending) {
                            stopParse(currentProject.id);
                            return;
                          }
                          startParse({
                            projectId: currentProject.id,
                            script: currentProject.originalScript,
                            model: activeScriptConfig?.modelSeries,
                            episodeId: currentProject.currentEpisodeId ?? undefined,
                          });
                        }}
                        disabled={!currentProject || !hasUsableScriptConfig}
                        className={cn(
                          "h-8 rounded-xl text-xs cursor-pointer",
                          (currentProject?.status === "parsing" || parseProjectMutation.isPending) &&
                          "animate-pulse font-medium"
                        )}
                      >
                        {currentProject?.status === "parsing" || parseProjectMutation.isPending ? (
                          <Square className="mr-1.5 size-3.5 fill-current" />
                        ) : (
                          <WandSparkles className="mr-1.5 size-3.5 text-primary" />
                        )}
                        {currentProject?.status === "parsing" || parseProjectMutation.isPending
                          ? t("home.stopParsingScenes")
                          : t("home.generateStoryboard")}
                      </Button>

                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          if (!currentProject || deleteProjectMutation.isPending) {
                            return;
                          }
                          setDeleteProjectOpen(true);
                        }}
                        disabled={!currentProject || deleteProjectMutation.isPending}
                        className="h-8 rounded-xl text-xs text-muted-foreground hover:bg-destructive/10 hover:text-destructive cursor-pointer px-2.5"
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </div>

                  {currentProject?.videoUrl || currentProject?.videoStatus !== "idle" ? (
                    <div className="rounded-xl border border-border/60 bg-muted/20 p-3 space-y-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <Badge variant="outline" className="text-[10px]">
                          {t("home.videoStatus", { status: currentProject?.videoStatus ?? "idle" })}
                        </Badge>
                        <span className="text-[10px] text-muted-foreground">
                          {t("home.videoProgress", { progress: currentProject?.videoProgress ?? 0 })}
                        </span>
                      </div>
                      {currentProject?.videoUrl ? (
                        <a
                          href={currentProject.videoUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center text-xs text-primary font-medium underline-offset-4 hover:underline"
                        >
                          {t("home.openVideoLink")}
                        </a>
                      ) : null}
                    </div>
                  ) : null}

                  {!hasUsableScriptConfig ? (
                    <p className="text-xs text-amber-600">
                      {t("home.scriptRequiredHint")}
                    </p>
                  ) : null}

                  {statusMessage ? <p className="text-xs text-muted-foreground">{statusMessage}</p> : null}
                </CardContent>
              </Card>

              {/* 生产约束设置 */}
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
            </div>

            {/* 右侧：分镜时间线与分镜卡片流 */}
            <div className="space-y-4">
              {/* 顶部分镜总览与批量操作卡片 */}
              <Card className="rounded-2xl border-border/70 bg-card/75 shadow-sm backdrop-blur-md">
                <CardHeader className="space-y-3 p-4">
                  {/* 剧集选择与剧集增删 */}
                  <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-border/50 pb-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {episodes.map((episode) => (
                        <Button
                          key={episode.id}
                          size="xs"
                          variant={episode.id === currentEpisodeId ? "default" : "outline"}
                          onClick={() => {
                            if (!currentProject || episode.id === currentEpisodeId) {
                              return;
                            }
                            openEpisodeMutation.mutate({ projectId: currentProject.id, episodeId: episode.id });
                          }}
                          disabled={openEpisodeMutation.isPending}
                          className="h-7 rounded-lg text-xs gap-1.5 cursor-pointer"
                        >
                          {episode.title}
                          <Badge variant="secondary" className="h-4 rounded-sm px-1 text-[9px]">
                            {episode.sceneCount}
                          </Badge>
                        </Button>
                      ))}

                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => {
                          if (currentProject) {
                            addEpisodeMutation.mutate(currentProject.id);
                          }
                        }}
                        disabled={!currentProject || addEpisodeMutation.isPending}
                        className="h-7 rounded-lg text-xs text-muted-foreground hover:bg-muted cursor-pointer"
                      >
                        <Plus className="mr-1 size-3" />
                        {t("home.addEpisode")}
                      </Button>
                    </div>

                    {currentEpisode ? (
                      <Button
                        size="xs"
                        variant="ghost"
                        className="h-7 rounded-lg text-xs text-muted-foreground hover:bg-destructive/10 hover:text-destructive cursor-pointer"
                        onClick={() => setEpisodeToDelete(currentEpisode)}
                        disabled={deleteEpisodeMutation.isPending}
                      >
                        <Trash2 className="mr-1 size-3" />
                        {t("home.deleteEpisode")}
                      </Button>
                    ) : null}
                  </div>

                  {/* 批量操作工具条 */}
                  <div className="flex flex-wrap items-center justify-between gap-2.5 pt-1">
                    <div className="flex items-center gap-2">
                      <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground cursor-pointer">
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
                          className="size-4 rounded accent-primary cursor-pointer"
                        />
                        {t("scene.selectAll")}
                      </label>
                      <Badge variant="secondary" className="rounded-md text-[10px] px-1.5 py-0">
                        {t("scene.selectedCount", { count: selectedScenes.length })}
                      </Badge>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        size="xs"
                        className="h-7 rounded-lg text-xs gap-1 cursor-pointer font-medium"
                        onClick={() => generateScenes(selectedScenes.map((scene) => scene.id))}
                        disabled={generationBusy || !hasUsableImageConfig || selectedScenes.length === 0}
                      >
                        <ImageIcon className="size-3" />
                        {t("scene.generateSelectedImages")}
                      </Button>
                      <Button
                        size="xs"
                        variant="secondary"
                        className="h-7 rounded-lg text-xs gap-1 cursor-pointer"
                        onClick={() => openVideoDialog(selectedScenes.map((scene) => scene.id))}
                        disabled={generationBusy || !activeVideoConfig?.videoCapabilities || selectedScenes.length === 0}
                      >
                        <Film className="size-3" />
                        {t("scene.generateSelectedVideo")}
                      </Button>
                      <Button
                        size="xs"
                        variant="outline"
                        className="h-7 rounded-lg text-xs gap-1 cursor-pointer"
                        onClick={() => generateScenes(failedSceneIds("image"))}
                        disabled={generationBusy || !hasUsableImageConfig || failedSceneIds("image").length === 0}
                      >
                        <RefreshCw className="size-3" />
                        {t("scene.retryFailedImages")}
                      </Button>
                      <Button
                        size="xs"
                        variant="outline"
                        className="h-7 rounded-lg text-xs gap-1 cursor-pointer"
                        onClick={() => openVideoDialog(failedSceneIds("video"))}
                        disabled={generationBusy || !activeVideoConfig?.videoCapabilities || failedSceneIds("video").length === 0}
                      >
                        <RefreshCw className="size-3" />
                        {t("scene.retryFailedVideo")}
                      </Button>
                      <Button
                        size="xs"
                        variant="outline"
                        className="h-7 rounded-lg text-xs gap-1 cursor-pointer"
                        onClick={() => currentProject && createSceneMutation.mutate({ projectId: currentProject.id, episodeId: currentProject.currentEpisodeId ?? undefined })}
                        disabled={!currentProject || generationBusy || createSceneMutation.isPending}
                      >
                        <Plus className="size-3" />
                        {t("scene.add")}
                      </Button>
                    </div>
                  </div>
                </CardHeader>
              </Card>

              {/* 分镜卡片列表 */}
              <div className="space-y-4">
                {!currentProject ? (
                  <div className="space-y-3">
                    <Skeleton className="h-44 w-full rounded-2xl" />
                    <Skeleton className="h-44 w-full rounded-2xl" />
                  </div>
                ) : openEpisodeMutation.isPending ? (
                  <div className="space-y-3">
                    <Skeleton className="h-44 w-full rounded-2xl" />
                    <Skeleton className="h-44 w-full rounded-2xl" />
                  </div>
                ) : currentProject.scenes.length === 0 ? (
                  <div className="flex min-h-64 flex-col items-center justify-center rounded-3xl border border-dashed border-border/80 bg-card/30 p-8 text-center backdrop-blur-sm">
                    <Layers className="size-8 text-muted-foreground/50" />
                    <p className="mt-3 text-sm font-semibold text-foreground">{t("home.noScenes")}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      在左侧输入剧情并点击「一键生成分镜」，AI 将自动切分出镜头画面
                    </p>
                  </div>
                ) : (
                  <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                    <SortableContext
                      items={currentProject.scenes.map((scene) => scene.id)}
                      strategy={verticalListSortingStrategy}
                    >
                      <div className="space-y-4">
                        {currentProject.scenes.map((scene, index) => (
                          <div
                            key={scene.id}
                            className="animate-in fade-in-0 slide-in-from-bottom-1 duration-300"
                            style={{ animationDelay: `${index * 30}ms` }}
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
                                else if (media === "image") generateScenes([scene.id]);
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
                                setSceneCastMutation.mutate({
                                  projectId: currentProject.id,
                                  sceneId: scene.id,
                                  characterIds,
                                  previous: scene.characterIds,
                                });
                              }}
                            />
                          </div>
                        ))}
                      </div>
                    </SortableContext>
                  </DndContext>
                )}
              </div>
            </div>
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
              {activeVideoConfig.videoCapabilities.aspectRatios.length ? (
                <div className="space-y-2">
                  <Label>{t("videos.aspectRatio")}</Label>
                  <Select value={videoAspectRatio} onValueChange={(value) => setVideoAspectRatio(value ?? "")}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{activeVideoConfig.videoCapabilities.aspectRatios.map((value) => <SelectItem key={value} value={value}>{value === "adaptive" ? t("videos.aspectRatioAdaptive") : value}</SelectItem>)}</SelectContent>
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
                  aspectRatio: videoAspectRatio || undefined,
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
