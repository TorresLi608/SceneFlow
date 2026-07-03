"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Clapperboard,
  FolderPlus,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Search,
  Settings2,
  Shield,
  SlidersHorizontal,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { createProjectAction, listProjectsAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { getMeAction } from "@/actions/user-actions";
import { listUserConfigsAction } from "@/actions/settings-actions";
import { ChatPanel } from "@/components/chat/chat-panel";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { SettingsDialog } from "@/components/settings-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n";
import { resolveRequestError } from "@/lib/http/errors";
import { cn } from "@/lib/utils";
import { useProjectStore } from "@/store/project-store";
import { useUserStore } from "@/store/user-store";
import type { Project, ProjectStatus } from "@/types/project";

const statusLabels: Record<ProjectStatus, string> = {
  idle: "草稿",
  parsing: "分镜中",
  generating: "生成中",
  video_generating: "视频中",
  done: "已完成",
};

function projectCover(project: Project) {
  return project.scenes.find((scene) => scene.image.url)?.image.url ?? null;
}

export default function HomePage() {
  const router = useRouter();
  const { t, formatDateTime } = useI18n();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activeMenu, setActiveMenu] = useState<"chat" | "ai-script">("chat");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | ProjectStatus>("all");
  const [message, setMessage] = useState<string | null>(null);

  const hydrated = useUserStore((state) => state.hydrated);
  const token = useUserStore((state) => state.token);
  const user = useUserStore((state) => state.user);
  const setUser = useUserStore((state) => state.setUser);
  const logout = useUserStore((state) => state.logout);

  const projects = useProjectStore((state) => state.projects);
  const initialized = useProjectStore((state) => state.initialized);
  const initializeProjects = useProjectStore((state) => state.initializeProjects);
  const createProject = useProjectStore((state) => state.createProject);
  const selectProject = useProjectStore((state) => state.selectProject);

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

  const createProjectMutation = useMutation({
    mutationFn: () => createProjectAction({ title: `新项目 ${projects.length + 1}` }),
    onSuccess: (response) => {
      createProject(response.project);
      router.push(`/projects/${response.project.id}`);
    },
    onError: (error) => {
      setMessage(resolveRequestError(error, "新建项目失败，请稍后重试"));
    },
  });

  useEffect(() => {
    if (meQuery.data?.user) {
      setUser(meQuery.data.user);
    }
  }, [meQuery.data?.user, setUser]);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    if (!token) {
      router.replace("/login");
      return;
    }
    if (meQuery.isError) {
      logout();
      router.replace("/login");
    }
  }, [hydrated, token, meQuery.isError, logout, router]);

  useEffect(() => {
    if (projectsQuery.data?.projects) {
      initializeProjects(projectsQuery.data.projects);
    }
  }, [initializeProjects, projectsQuery.data?.projects]);

  const filteredProjects = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return projects.filter((project) => {
      const matchesQuery =
        !keyword ||
        project.title.toLowerCase().includes(keyword) ||
        project.originalScript.toLowerCase().includes(keyword);
      const matchesStatus = statusFilter === "all" || project.status === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [projects, query, statusFilter]);

  const openProject = (project: Project) => {
    selectProject(project.id);
    router.push(`/projects/${project.id}`);
  };

  if (!hydrated) {
    return <main className="flex min-h-screen items-center justify-center">{t("common.initializing")}</main>;
  }

  if (!token) {
    return <main className="flex min-h-screen items-center justify-center">{t("common.redirectingToLogin")}</main>;
  }

  return (
    <main className="flex h-screen overflow-hidden bg-background text-foreground">
      <aside className="flex w-[248px] shrink-0 flex-col border-r border-border/70 bg-card/50">
        <div className="p-4">
          <p className="text-sm font-semibold">SceneFlow</p>
          <p className="mt-1 text-xs text-muted-foreground">{t("home.brandSubtitle")}</p>
        </div>

        <nav className="space-y-1 px-3">
          <button
            type="button"
            onClick={() => setActiveMenu("chat")}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm",
              activeMenu === "chat" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
            )}
          >
            <MessageSquare className="size-4" />
            {t("home.chat")}
          </button>
          <button
            type="button"
            onClick={() => setActiveMenu("ai-script")}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm",
              activeMenu === "ai-script" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
            )}
          >
            <LayoutDashboard className="size-4" />
            {t("home.aiScript")}
          </button>
        </nav>

      </aside>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="border-b border-border/70 bg-card/60">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 md:px-6">
            <div>
              <p className="text-base font-semibold">
                {activeMenu === "chat" ? t("home.chat") : t("home.aiScript")}
              </p>
              <p className="text-xs text-muted-foreground">
                {t("common.currentUser", {
                  username: meQuery.isLoading ? t("common.loading") : user?.username ?? t("common.unknownUser"),
                })}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <PreferencesSwitcher />

              {user?.role === "superAdmin" ? (
                <Button variant="outline" size="icon" onClick={() => router.push("/admin")}>
                  <Shield className="size-4" />
                </Button>
              ) : null}

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

        {activeMenu === "chat" ? (
          <ChatPanel
            configs={userConfigsQuery.data?.configs ?? []}
            officialConfigs={userConfigsQuery.data?.officialConfigs ?? []}
            formatDateTime={formatDateTime}
          />
        ) : (
          <div className="min-h-0 overflow-y-auto px-4 py-5 md:px-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">{t("home.aiScript")}</h1>
                <p className="mt-1 text-xs text-muted-foreground">
                  {filteredProjects.length} / {projects.length} 个项目
                </p>
              </div>

              <div className="flex w-full flex-wrap items-center gap-2 md:w-auto">
                <div className="relative min-w-0 flex-1 md:w-64 md:flex-none">
                  <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="搜索项目"
                    className="pl-8"
                  />
                </div>
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value as "all" | ProjectStatus)}
                  className="h-9 rounded-lg border border-input bg-background px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  <option value="all">项目状态 全部</option>
                  {Object.entries(statusLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <Button variant="outline">
                  <SlidersHorizontal className="mr-2 size-4" />
                  高级筛选
                </Button>
                <Button onClick={() => createProjectMutation.mutate()} disabled={createProjectMutation.isPending}>
                  <FolderPlus className="mr-2 size-4" />
                  {createProjectMutation.isPending ? "创建中..." : t("home.newProject")}
                </Button>
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {projectsQuery.isLoading && projects.length === 0
                ? Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-36 rounded-lg" />)
                : null}

              {!projectsQuery.isLoading && filteredProjects.length === 0 ? (
                <div className="col-span-full flex min-h-56 items-center justify-center rounded-lg border border-dashed border-border/70 text-sm text-muted-foreground">
                  暂无项目，先新建一个 AI 生剧项目。
                </div>
              ) : null}

              {filteredProjects.map((project, index) => {
                const cover = projectCover(project);

                return (
                  <button
                    key={project.id}
                    type="button"
                    onClick={() => openProject(project)}
                    className={cn(
                      "group grid h-36 grid-cols-[minmax(0,1fr)_72px] gap-3 rounded-lg border border-border/70 bg-card/70 p-4 text-left transition duration-200 hover:border-primary/40 hover:bg-muted/40",
                      "animate-in fade-in-0 slide-in-from-bottom-1"
                    )}
                    style={{ animationDelay: `${index * 40}ms` }}
                  >
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate text-sm font-semibold">{project.title}</span>
                      <span className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
                        {project.originalScript || "还没有写入剧本内容。"}
                      </span>
                      <span className="mt-auto flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span className="rounded-md bg-muted px-2 py-1">{statusLabels[project.status]}</span>
                        <span>{project.scenes.length} 个分镜</span>
                        <span>{formatDateTime(project.updatedAt)}</span>
                      </span>
                    </span>

                    <span className="flex size-[72px] items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-muted">
                      {cover ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={cover} alt="" className="size-full object-cover" />
                      ) : (
                        <Clapperboard className="size-7 text-muted-foreground transition group-hover:text-primary" />
                      )}
                    </span>
                  </button>
                );
              })}
            </div>

            {message ? <p className="mt-4 text-sm text-amber-600">{message}</p> : null}
          </div>
        )}
      </section>

      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </main>
  );
}
