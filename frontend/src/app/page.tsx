"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Clapperboard,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Plus,
  Settings2,
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

import { getProjectTemplatesAction, parseProjectAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { getMeAction } from "@/actions/user-actions";
import { SceneCard } from "@/components/workbench/scene-card";
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
import { resolveRequestError } from "@/lib/http/errors";
import { cn } from "@/lib/utils";
import { useProjectStore } from "@/store/project-store";
import { useUserStore } from "@/store/user-store";
import type { ModelOption } from "@/types/auth";

const formatter = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export default function HomePage() {
  const router = useRouter();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [parseMessage, setParseMessage] = useState<string | null>(null);

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
  const setProjectStatus = useProjectStore((state) => state.setProjectStatus);
  const applyParsedScenes = useProjectStore((state) => state.applyParsedScenes);
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

  const parseProjectMutation = useMutation({
    mutationFn: (params: { projectId: string; script: string; model: string }) =>
      parseProjectAction(params.projectId, {
        script: params.script,
        model: params.model,
      }),
    onMutate: ({ projectId }) => {
      setParseMessage(null);
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
        setParseMessage(response.warning);
      } else if (response.source === "llm") {
        setParseMessage("分镜解析完成（LLM）");
      } else {
        setParseMessage("分镜解析完成（Fallback）");
      }
    },
    onError: (error, variables) => {
      setProjectStatus(variables.projectId, "idle");
      setParseMessage(resolveRequestError(error, "分镜解析失败，请检查模型配置或稍后重试"));
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
                <Select
                  value={selectedModel}
                  onValueChange={(value) => {
                    if (value) {
                      setSelectedModel(value as ModelOption);
                    }
                  }}
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="选择模型" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="gpt-4o">GPT-4o</SelectItem>
                    <SelectItem value="deepseek-v3">DeepSeek-V3</SelectItem>
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

                <div className="flex items-center justify-between gap-2">
                  <Badge variant="secondary">状态: {currentProject?.status ?? "loading"}</Badge>
                  <Button
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
                    disabled={!currentProject || currentProject.status === "parsing"}
                  >
                    <WandSparkles className="mr-2 size-4" />
                    {currentProject?.status === "parsing" ? "分镜解析中..." : "智能分镜"}
                  </Button>
                </div>

                {parseMessage ? <p className="text-xs text-muted-foreground">{parseMessage}</p> : null}
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
