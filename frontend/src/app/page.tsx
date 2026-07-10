"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Clapperboard,
  FolderPlus,
  ImageIcon,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Search,
  Shield,
  SlidersHorizontal,
} from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { createProjectAction, listProjectsAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { getMeAction } from "@/actions/user-actions";
import { listUserConfigsAction } from "@/actions/settings-actions";
import { AdminUsersManager } from "@/app/admin/_components/admin-users-manager";
import { ModelConfigManager } from "@/app/admin/_components/model-config-manager";
import { ChatPanel } from "@/app/chat/_components/chat-panel";
import { ImageGenerationPanel } from "@/app/images/_components/image-generation-panel";
import { PreferencesSwitcher } from "@/components/preferences-switcher";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n";
import { resolveRequestError } from "@/lib/http/errors";
import { cn } from "@/lib/utils";
import { useProjectStore } from "@/store/project-store";
import { useUserStore } from "@/store/user-store";
import type { Project, ProjectStatus } from "@/types/project";

export type HomeMenu = "chat" | "images" | "ai-script";
export type HomeView = HomeMenu | "admin-configs" | "admin-users";

const menuRoutes: Record<HomeMenu, string> = {
  chat: "/chat",
  images: "/images",
  "ai-script": "/ai-script",
};

function projectCover(project: Project) {
  return project.scenes.find((scene) => scene.image.url)?.image.url ?? null;
}

interface HomePageProps {
  activeMenu?: HomeMenu;
  activeView?: HomeView;
}

export function HomePage({ activeMenu = "chat", activeView: requestedView }: HomePageProps = {}) {
  const initialView = requestedView ?? activeMenu;
  const router = useRouter();
  const { t, formatDateTime } = useI18n();
  const statusLabels: Record<ProjectStatus, string> = {
    idle: t("home.projectStatus.idle"),
    parsing: t("home.projectStatus.parsing"),
    generating: t("home.projectStatus.generating"),
    video_generating: t("home.projectStatus.video_generating"),
    done: t("home.projectStatus.done"),
  };
  const [activeView, setActiveView] = useState<HomeView>(initialView);
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
    mutationFn: () => createProjectAction({ title: `${t("home.newProject")} ${projects.length + 1}` }),
    onSuccess: (response) => {
      createProject(response.project);
      router.push(`/projects/${response.project.id}`);
    },
    onError: (error) => {
      setMessage(resolveRequestError(error, t("home.createProjectFailed")));
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

  const pageTitle =
    activeView === "chat"
      ? t("home.chat")
      : activeView === "images"
        ? t("home.images")
        : activeView === "ai-script"
          ? t("home.aiScript")
          : activeView === "admin-configs"
            ? t("home.modelManagement")
            : t("home.userManagement");

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
          <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("home.businessCenter")}</p>
          <button
            type="button"
            onClick={() => {
              setActiveView("chat");
              router.push(menuRoutes.chat);
            }}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm",
              activeView === "chat" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
            )}
          >
            <MessageSquare className="size-4" />
            {t("home.chat")}
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveView("images");
              router.push(menuRoutes.images);
            }}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm",
              activeView === "images" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
            )}
          >
            <ImageIcon className="size-4" />
            {t("home.images")}
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveView("ai-script");
              router.push(menuRoutes["ai-script"]);
            }}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm",
              activeView === "ai-script" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
            )}
          >
            <LayoutDashboard className="size-4" />
            {t("home.aiScript")}
          </button>

          <div className="pt-4">
            <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("home.adminCenter")}</p>
            <button
              type="button"
              onClick={() => {
                setActiveView("admin-configs");
                router.push("/admin/models");
              }}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm",
                activeView === "admin-configs" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
              )}
            >
              <SlidersHorizontal className="size-4" />
              {t("home.modelManagement")}
            </button>
            {user?.role === "superAdmin" ? (
              <button
                type="button"
                onClick={() => {
                  setActiveView("admin-users");
                  router.push("/admin/users");
                }}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm",
                  activeView === "admin-users" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60"
                )}
              >
                <Shield className="size-4" />
                {t("home.userManagement")}
              </button>
            ) : null}
          </div>
        </nav>

      </aside>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="border-b border-border/70 bg-card/60">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 md:px-6">
            <div>
              <p className="text-base font-semibold">
                {pageTitle}
              </p>
              <p className="text-xs text-muted-foreground">
                {t("common.currentUser", {
                  username: meQuery.isLoading ? t("common.loading") : user?.username ?? t("common.unknownUser"),
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

        {activeView === "chat" ? (
          <ChatPanel
            configs={userConfigsQuery.data?.configs ?? []}
            officialConfigs={userConfigsQuery.data?.officialConfigs ?? []}
            formatDateTime={formatDateTime}
          />
        ) : activeView === "images" ? (
          <ImageGenerationPanel
            configs={userConfigsQuery.data?.configs ?? []}
            officialConfigs={userConfigsQuery.data?.officialConfigs ?? []}
          />
        ) : activeView === "admin-configs" ? (
          <div className="min-h-0 overflow-y-auto px-4 py-5 md:px-6">
            <ModelConfigManager />
          </div>
        ) : activeView === "admin-users" ? (
          <div className="min-h-0 overflow-y-auto px-4 py-5 md:px-6">
            {user?.role === "superAdmin" ? <AdminUsersManager /> : <p className="text-sm text-muted-foreground">{t("home.noUserManagementPermission")}</p>}
          </div>
        ) : (
          <div className="min-h-0 overflow-y-auto px-4 py-5 md:px-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">{t("home.aiScript")}</h1>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("home.projectsCount", { filtered: filteredProjects.length, total: projects.length })}
                </p>
              </div>

              <div className="flex w-full flex-wrap items-center gap-2 md:w-auto">
                <div className="relative min-w-0 flex-1 md:w-64 md:flex-none">
                  <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder={t("home.searchProjects")}
                    className="pl-8"
                  />
                </div>
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value as "all" | ProjectStatus)}
                  className="h-9 rounded-lg border border-input bg-background px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  <option value="all">{t("home.projectStatusAll")}</option>
                  {Object.entries(statusLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <Button variant="outline">
                  <SlidersHorizontal className="mr-2 size-4" />
                  {t("home.advancedFilters")}
                </Button>
                <Button onClick={() => createProjectMutation.mutate()} disabled={createProjectMutation.isPending}>
                  <FolderPlus className="mr-2 size-4" />
                  {createProjectMutation.isPending ? t("home.creatingProject") : t("home.newProject")}
                </Button>
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {projectsQuery.isLoading && projects.length === 0
                ? Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-36 rounded-lg" />)
                : null}

              {!projectsQuery.isLoading && filteredProjects.length === 0 ? (
                <div className="col-span-full flex min-h-56 items-center justify-center rounded-lg border border-dashed border-border/70 text-sm text-muted-foreground">
                  {t("home.emptyProjects")}
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
                        {project.originalScript || t("home.emptyProjectScript")}
                      </span>
                      <span className="mt-auto flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span className="rounded-md bg-muted px-2 py-1">{statusLabels[project.status]}</span>
                        <span>{t("home.sceneCount", { count: project.scenes.length })}</span>
                        <span>{formatDateTime(project.updatedAt)}</span>
                      </span>
                    </span>

                    <span className="relative flex size-[72px] items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-muted">
                      {cover ? (
                        <Image src={cover} alt="" fill unoptimized sizes="72px" className="object-cover" />
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
    </main>
  );
}

export default function RootPage() {
  return <HomePage activeMenu="chat" />;
}
