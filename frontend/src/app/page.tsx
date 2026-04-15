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
import { SettingsDialog } from "@/components/settings-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { SceneCard } from "@/components/workbench/scene-card";
import { resolveRequestError } from "@/lib/http/errors";
import { cn } from "@/lib/utils";
import { useProjectStore } from "@/store/project-store";
import { useUserStore } from "@/store/user-store";
import type { ModelOption } from "@/types/auth";
import type { ProjectStatus, SceneTaskStatus, SceneUpdatePayload } from "@/types/project";

const formatter = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const wsBaseURL =
  (process.env.NEXT_PUBLIC_WS_BASE_URL?.trim() || "ws://127.0.0.1:8080").replace(/\/$/, "");

function isTaskStatus(value: unknown): value is SceneTaskStatus | "idle" {
  return (
    value === "idle" || value === "generating" || value === "success" || value === "error"
  );
}

export default function HomePage() {
  const router = useRouter();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));
  const wsRef = useRef<WebSocket | null>(null);

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

  const hydrated = useUserStore((state) => state.hydrated);
  const token = useUserStore((state) => state.token);
  const user = useUserStore((state) => state.user);
  const selectedModel = useUserStore((state) => state.selectedModel);
  const setUser = useUserStore((state) => state.setUser);
  const setSelectedModel = useUserStore((state) => state.setSelectedModel);
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

  const activeScriptConfigs = useMemo(
    () =>
      (userConfigsQuery.data?.configs ?? []).filter(
        (config) =>
          config.isActive &&
          config.isVerified &&
          config.purpose === "script" &&
          config.modelSeries.trim().length > 0
      ),
    [userConfigsQuery.data?.configs]
  );
  const hasUsableScriptConfig = activeScriptConfigs.length > 0;
  const selectableModels = useMemo(
    () =>
      Array.from(new Set(activeScriptConfigs.map((config) => config.modelSeries.trim()).filter(Boolean))),
    [activeScriptConfigs]
  );

  const parseProjectMutation = useMutation({
    mutationFn: (params: { projectId: string; script: string; model: string }) =>
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
        setStatusMessage("分镜解析完成（LLM）");
      } else {
        setStatusMessage("分镜解析完成（Fallback）");
      }
    },
    onError: (error, variables) => {
      setProjectStatus(variables.projectId, "idle");
      setStatusMessage(resolveRequestError(error, "分镜解析失败，请检查模型配置或稍后重试"));
    },
  });

  const generateProjectMutation = useMutation({
    mutationFn: (params: { projectId: string; model: string }) =>
      generateProjectAction(params.projectId, { model: params.model }),
    onMutate: ({ projectId }) => {
      setStatusMessage(null);
      setProjectStatus(projectId, "generating");
    },
    onSuccess: () => {
      setStatusMessage("已启动并发生成，正在接收实时进度...");
    },
    onError: (error, variables) => {
      setProjectStatus(variables.projectId, "idle");
      setStatusMessage(resolveRequestError(error, "一键生成启动失败，请稍后重试"));
    },
  });

  const optimizeProjectMutation = useMutation({
    mutationFn: (params: { projectId: string; script: string; model: string }) =>
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
        setStatusMessage(`剧本优化完成（${response.source}）: ${response.warning}`);
      } else {
        setStatusMessage(`剧本优化完成（${response.source.toUpperCase()}）`);
      }
    },
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, "剧本优化失败，请检查脚本和配置"));
    },
  });

  const generateVideoMutation = useMutation({
    mutationFn: (params: { projectId: string; model: string }) =>
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
      setStatusMessage("视频生成任务已启动（Seedance 2.0）");
    },
    onError: (error, variables) => {
      updateProjectFields(variables.projectId, {
        status: "idle",
        videoStatus: "idle",
        videoProgress: 0,
      });
      setStatusMessage(resolveRequestError(error, "视频生成启动失败，请检查 Seedance 配置"));
    },
  });

  const deleteProjectMutation = useMutation({
    mutationFn: (projectId: string) => deleteProjectAction(projectId),
    onMutate: () => {
      setStatusMessage(null);
    },
    onSuccess: (_, projectId) => {
      removeProject(projectId);
      setStatusMessage("项目已删除");
    },
    onError: (error) => {
      setStatusMessage(resolveRequestError(error, "删除项目失败，请稍后重试"));
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
    if (!hasUsableScriptConfig || selectableModels.length === 0) {
      return;
    }

    if (!selectableModels.includes(selectedModel)) {
      setSelectedModel(selectableModels[0]);
    }
  }, [hasUsableScriptConfig, selectableModels, selectedModel, setSelectedModel]);

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
            setStatusMessage("并发生成完成");
          }

          if (videoStatus === "success") {
            setStatusMessage("视频生成完成");
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
          setStatusMessage("当前项目已删除");
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
  ]);

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) {
      return;
    }

    reorderScenes(String(active.id), String(over.id));
  };

  if (!hydrated) {
    return <main className="flex min-h-screen items-center justify-center">初始化中...</main>;
  }

  if (!token) {
    return <main className="flex min-h-screen items-center justify-center">跳转登录...</main>;
  }

  if (!currentProject && !projectTemplatesQuery.isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <Button onClick={createProject}>创建你的第一个项目</Button>
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
                <p className="text-xs text-muted-foreground">AI 漫剧可视化工作台</p>
              </div>
            </div>

            <Button className="w-full justify-start" onClick={createProject}>
              <Plus className="mr-2 size-4" />
              新建项目
            </Button>
          </div>

          <div className="space-y-1 px-3 pb-3">
            <p className="px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">菜单</p>
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-md bg-muted px-2 py-2 text-left text-sm"
            >
              <LayoutDashboard className="size-4" />
              工作台
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm text-muted-foreground"
            >
              <FolderKanban className="size-4" />
              项目资产
            </button>
          </div>

          <Separator />

          <div className="flex-1 space-y-2 overflow-y-auto px-3 py-4">
            <p className="px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">项目列表</p>

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
                    {project.scenes.length} scenes · {formatter.format(new Date(project.updatedAt))}
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
                <p className="text-base font-semibold">{currentProject?.title ?? "加载项目中..."}</p>
                <p className="text-xs text-muted-foreground">
                  当前用户：{meQuery.isLoading ? "加载中..." : user?.username ?? "未知用户"}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <Badge variant="outline" className="hidden sm:inline-flex">
                  WS: {wsConnected ? "已连接" : "未连接"}
                </Badge>

                <Select
                  value={selectedModel}
                  disabled={!hasUsableScriptConfig}
                  onValueChange={(value) => {
                    if (value) {
                      setSelectedModel(value as ModelOption);
                    }
                  }}
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue
                      placeholder={hasUsableScriptConfig ? "选择模型" : "先在设置中校验并激活 script 模型"}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {selectableModels.map((model) => (
                      <SelectItem key={model} value={model}>
                        {model}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

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
                  退出
                </Button>
              </div>
            </div>
          </header>

          <div className="grid flex-1 gap-6 p-4 md:p-6 xl:grid-cols-[360px_minmax(0,1fr)]">
            <Card className="h-fit border-border/80">
              <CardHeader>
                <CardTitle className="text-base">剧本输入</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Textarea
                  value={currentProject?.originalScript ?? ""}
                  onChange={(event) => updateCurrentScript(event.target.value)}
                  placeholder="输入你的故事剧本，每一段建议一行..."
                  className="min-h-[300px]"
                  disabled={!currentProject}
                />

                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Badge variant="secondary">状态: {currentProject?.status ?? "loading"}</Badge>

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
                          model: selectedModel,
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
                      {optimizeProjectMutation.isPending ? "优化中..." : "优化剧本"}
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
                          model: selectedModel,
                        });
                      }}
                      disabled={!currentProject || !hasUsableScriptConfig || currentProject.status === "parsing"}
                    >
                      <WandSparkles className="mr-2 size-4" />
                      {currentProject?.status === "parsing" ? "分镜解析中..." : "智能分镜"}
                    </Button>

                    <Button
                      onClick={() => {
                        if (!currentProject) {
                          return;
                        }

                        generateProjectMutation.mutate({
                          projectId: currentProject.id,
                          model: selectedModel,
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
                      {currentProject?.status === "generating" ? "并发生成中..." : "一键生成"}
                    </Button>

                    <Button
                      onClick={() => {
                        if (!currentProject) {
                          return;
                        }

                        generateVideoMutation.mutate({
                          projectId: currentProject.id,
                          model: "seedance-2.0",
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
                      {currentProject?.status === "video_generating" ? "视频生成中..." : "生成视频"}
                    </Button>

                    <Button
                      variant="outline"
                      onClick={() => {
                        if (!currentProject || deleteProjectMutation.isPending) {
                          return;
                        }
                        if (!window.confirm(`确认删除项目「${currentProject.title}」吗？`)) {
                          return;
                        }
                        deleteProjectMutation.mutate(currentProject.id);
                      }}
                      disabled={!currentProject || deleteProjectMutation.isPending}
                    >
                      <Trash2 className="mr-2 size-4" />
                      {deleteProjectMutation.isPending ? "删除中..." : "删除项目"}
                    </Button>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">视频状态: {currentProject?.videoStatus ?? "idle"}</Badge>
                  <Badge variant="outline">视频进度: {currentProject?.videoProgress ?? 0}%</Badge>
                </div>

                {currentProject?.videoUrl ? (
                  <a
                    href={currentProject.videoUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center text-xs text-primary underline-offset-4 hover:underline"
                  >
                    打开生成视频链接
                  </a>
                ) : null}

                {!hasUsableScriptConfig ? (
                  <p className="text-xs text-amber-600">
                    请先在设置中完成 script 模型的可用性校验并保存激活后，再进行优化剧本和智能分镜。
                  </p>
                ) : null}

                {statusMessage ? <p className="text-xs text-muted-foreground">{statusMessage}</p> : null}
              </CardContent>
            </Card>

            <Card className="min-h-[500px] border-border/80">
              <CardHeader>
                <CardTitle className="text-base">分镜卡片流（可拖拽排序）</CardTitle>
              </CardHeader>
              <CardContent>
                {!currentProject ? (
                  <div className="space-y-3">
                    <Skeleton className="h-40 w-full" />
                    <Skeleton className="h-40 w-full" />
                  </div>
                ) : currentProject.scenes.length === 0 ? (
                  <p className="py-14 text-center text-sm text-muted-foreground">暂无分镜，先点击智能分镜生成。</p>
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
