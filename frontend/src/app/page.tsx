"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Clapperboard,
  Film,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Plus,
  Settings2,
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
  deleteProjectAction,
  generateProjectAction,
  generateVideoAction,
  getProjectTemplatesAction,
  optimizeProjectAction,
  parseProjectAction,
} from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { listUserConfigsAction } from "@/actions/settings-actions";
import { getMeAction } from "@/actions/user-actions";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { SettingsDialog } from "@/components/settings-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { SceneCard } from "@/components/workbench/scene-card";
import { useI18n } from "@/lib/i18n";
import { resolveRequestError } from "@/lib/http/errors";
import { cn } from "@/lib/utils";
import { useProjectStore } from "@/store/project-store";
import { useUserStore } from "@/store/user-store";
import type { ConfigPurpose, UserConfig } from "@/types/auth";
import type { ProjectStatus, SceneTaskStatus, SceneUpdatePayload } from "@/types/project";

const wsBaseURL =
  (process.env.NEXT_PUBLIC_WS_BASE_URL?.trim() || "ws://127.0.0.1:8080").replace(/\/$/, "");

function isTaskStatus(value: unknown): value is SceneTaskStatus | "idle" {
  return (
    value === "idle" || value === "generating" || value === "success" || value === "error"
  );
}

const providerLabelMap: Record<string, string> = {
  qwen: "Qwen",
  deepseek: "DeepSeek",
  doubao: "Doubao",
  openai: "OpenAI",
  "seedance2.0": "Seedance 2.0",
};

function summarizeActiveConfig(config: UserConfig | undefined, unconfiguredLabel: string) {
  if (!config) {
    return unconfiguredLabel;
  }

  const providerLabel = providerLabelMap[config.provider] ?? config.provider;
  return `${providerLabel} · ${config.modelSeries}`;
}

export default function HomePage() {
  const router = useRouter();
  const { t, formatDateTime } = useI18n();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));
  const wsRef = useRef<WebSocket | null>(null);

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

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
  const reorderScenes = useProjectStore((state) => state.reorderScenes);

  const currentProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId),
    [projects, selectedProjectId]
  );

  const meQuery = useQuery({
    queryKey: queryKeys.me,
    queryFn: getMeAction,
    enabled: hydrated && Boolean(token),
  });

  const projectTemplatesQuery = useQuery({
    queryKey: queryKeys.projectTemplates,
    queryFn: getProjectTemplatesAction,
    enabled: hydrated && Boolean(token) && !initialized,
    staleTime: 300_000,
  });

  const userConfigsQuery = useQuery({
    queryKey: queryKeys.userConfigs,
    queryFn: listUserConfigsAction,
    enabled: hydrated && Boolean(token),
    staleTime: 30_000,
  });

  const activeConfigByPurpose = useMemo(
    () =>
      (userConfigsQuery.data?.configs ?? []).reduce<Partial<Record<ConfigPurpose, UserConfig>>>((acc, config) => {
        const isUsableActiveConfig =
          config.isActive && config.isVerified && config.modelSeries.trim().length > 0;

        if (isUsableActiveConfig && !acc[config.purpose]) {
          acc[config.purpose] = config;
        }

        return acc;
      }, {}),
    [userConfigsQuery.data?.configs]
  );
  const activeScriptConfig = activeConfigByPurpose.script;
  const activeImageConfig = activeConfigByPurpose.image;
  const activeVideoConfig = activeConfigByPurpose.video;
  const hasUsableScriptConfig = Boolean(activeScriptConfig);

  const parseProjectMutation = useMutation({
    mutationFn: (params: { projectId: string; script: string; model?: string }) =>
      parseProjectAction(params.projectId, {
        script: params.script,
        model: params.model,
      }),
    onMutate: ({ projectId }) => {
      setStatusMessage(null);
      setProjectStatus(projectId, "parsing");
    },
    onSuccess: (response) => {
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

  const generateProjectMutation = useMutation({
    mutationFn: (params: { projectId: string; model?: string }) =>
      generateProjectAction(params.projectId, { model: params.model }),
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
      updateProjectFields(variables.projectId, {
        originalScript: response.optimizedScript,
        status: "idle",
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
    mutationFn: (params: { projectId: string; model?: string }) =>
      generateVideoAction(params.projectId, { model: params.model }),
    onMutate: ({ projectId }) => {
      setStatusMessage(null);
      updateProjectFields(projectId, {
        status: "video_generating",
        videoStatus: "generating",
        videoProgress: 0,
      });
    },
    onSuccess: () => {
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
      removeProject(projectId);
      setStatusMessage(t("home.status.projectDeleted"));
    },
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, t("home.status.deleteFailed")));
    },
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
    if (!projectTemplatesQuery.data?.projects) {
      return;
    }

    initializeProjects(projectTemplatesQuery.data.projects);
  }, [initializeProjects, projectTemplatesQuery.data?.projects]);

  useEffect(() => {
    if (!hydrated || !token || !selectedProjectId) {
      return;
    }

    const wsURL = `${wsBaseURL}/ws/projects/${selectedProjectId}?token=${encodeURIComponent(token)}`;
    const socket = new WebSocket(wsURL);
    wsRef.current = socket;

    socket.onopen = () => {
      setWsConnected(true);
    };

    socket.onclose = () => {
      setWsConnected(false);
    };

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
          if (Object.keys(patch).length > 0) {
            updateProjectFields(payload.projectId, patch);
          }

          if (typeof warning === "string" && warning.trim()) {
            setStatusMessage(warning);
          }

          if (status === "done") {
            setStatusMessage(t("home.status.generationDone"));
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
      setWsConnected(false);
    };
  }, [
    hydrated,
    token,
    selectedProjectId,
    applySceneStreamUpdate,
    setProjectStatus,
    updateProjectFields,
    removeProject,
    t,
  ]);

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) {
      return;
    }

    reorderScenes(String(active.id), String(over.id));
  };

  if (!hydrated) {
    return <main className="flex min-h-screen items-center justify-center">{t("common.initializing")}</main>;
  }

  if (!token) {
    return <main className="flex min-h-screen items-center justify-center">{t("common.redirectingToLogin")}</main>;
  }

  if (!currentProject && !projectTemplatesQuery.isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <Button onClick={createProject}>{t("common.createFirstProject")}</Button>
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

            <Button className="w-full justify-start" onClick={createProject}>
              <Plus className="mr-2 size-4" />
              {t("home.newProject")}
            </Button>
          </div>

          <div className="space-y-1 px-3 pb-3">
            <p className="px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("home.menu")}</p>
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-md bg-muted px-2 py-2 text-left text-sm"
            >
              <LayoutDashboard className="size-4" />
              {t("home.workspace")}
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm text-muted-foreground"
            >
              <FolderKanban className="size-4" />
              {t("home.assets")}
            </button>
          </div>

          <Separator />

          <div className="flex-1 space-y-2 overflow-y-auto px-3 py-4">
            <p className="px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("home.projectList")}</p>

            {projectTemplatesQuery.isLoading && projects.length === 0 ? (
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
                  onClick={() => selectProject(project.id)}
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
                    username: meQuery.isLoading ? t("common.loading") : user?.username ?? t("common.unknownUser"),
                  })}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <Badge variant="outline" className="hidden sm:inline-flex">
                  WS: {wsConnected ? t("common.wsConnected") : t("common.wsDisconnected")}
                </Badge>

                <PreferencesSwitcher />

                <Button variant="outline" size="icon" onClick={() => setSettingsOpen(true)}>
                  <Settings2 className="size-4" />
                </Button>

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
                <div className="grid gap-2 rounded-lg border border-border/80 bg-muted/30 p-3 text-xs text-muted-foreground sm:grid-cols-3">
                  <p>
                    {t("home.scriptConfigSummary", {
                      value: summarizeActiveConfig(activeScriptConfig, t("settings.unconfigured")),
                    })}
                  </p>
                  <p>
                    {t("home.imageConfigSummary", {
                      value: summarizeActiveConfig(activeImageConfig, t("settings.unconfigured")),
                    })}
                  </p>
                  <p>
                    {t("home.videoConfigSummary", {
                      value: summarizeActiveConfig(activeVideoConfig, t("settings.unconfigured")),
                    })}
                  </p>
                </div>

                <Textarea
                  value={currentProject?.originalScript ?? ""}
                  onChange={(event) => updateCurrentScript(event.target.value)}
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
                        });
                      }}
                      disabled={!currentProject || !hasUsableScriptConfig || currentProject.status === "parsing"}
                    >
                      <WandSparkles className="mr-2 size-4" />
                      {currentProject?.status === "parsing" ? t("home.parsingScenes") : t("home.parseScenes")}
                    </Button>

                    <Button
                      onClick={() => {
                        if (!currentProject) {
                          return;
                        }

                        generateProjectMutation.mutate({
                          projectId: currentProject.id,
                          model: activeImageConfig?.modelSeries,
                        });
                      }}
                      disabled={
                        !currentProject ||
                        !hasUsableScriptConfig ||
                        currentProject.status === "parsing" ||
                        currentProject.status === "generating" ||
                        currentProject.scenes.length === 0
                      }
                    >
                      <Sparkles className="mr-2 size-4" />
                      {currentProject?.status === "generating" ? t("home.generatingAll") : t("home.generateAll")}
                    </Button>

                    <Button
                      onClick={() => {
                        if (!currentProject) {
                          return;
                        }

                        generateVideoMutation.mutate({
                          projectId: currentProject.id,
                          model: activeVideoConfig?.modelSeries,
                        });
                      }}
                      disabled={
                        !currentProject ||
                        generateVideoMutation.isPending ||
                        currentProject.status === "parsing" ||
                        currentProject.status === "generating" ||
                        currentProject.status === "video_generating" ||
                        currentProject.scenes.length === 0
                      }
                    >
                      <Film className="mr-2 size-4" />
                      {currentProject?.status === "video_generating"
                        ? t("home.generatingVideo")
                        : t("home.generateVideo")}
                    </Button>

                    <Button
                      variant="outline"
                      onClick={() => {
                        if (!currentProject || deleteProjectMutation.isPending) {
                          return;
                        }
                        if (!window.confirm(t("home.deleteProjectConfirm", { title: currentProject.title }))) {
                          return;
                        }
                        deleteProjectMutation.mutate(currentProject.id);
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

            <Card className="min-h-[500px] border-border/80">
              <CardHeader>
                <CardTitle className="text-base">{t("home.sceneFlowTitle")}</CardTitle>
              </CardHeader>
              <CardContent>
                {!currentProject ? (
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
                              onNarrationChange={(value) =>
                                updateScene(scene.id, {
                                  narration: value,
                                })
                              }
                              onPromptChange={(value) =>
                                updateScene(scene.id, {
                                  visualPrompt: value,
                                })
                              }
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

      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </main>
  );
}
