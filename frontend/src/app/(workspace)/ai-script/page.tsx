"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Clapperboard, FolderPlus, RotateCcw, Search } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { createProjectAction, listProjectsAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useProjectStore } from "@/store/project-store";
import type { Project, ProjectStatus } from "@/types/project";

function projectCover(project: Project) {
  return project.scenes.find((scene) => scene.image.url)?.image.url ?? null;
}

export default function AiScriptPage() {
  const router = useRouter();
  const { t, formatDateTime } = useI18n();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | ProjectStatus>("all");
  const [message, setMessage] = useState<string | null>(null);
  const projects = useProjectStore((state) => state.projects);
  const initialized = useProjectStore((state) => state.initialized);
  const initializeProjects = useProjectStore((state) => state.initializeProjects);
  const createProject = useProjectStore((state) => state.createProject);
  const selectProject = useProjectStore((state) => state.selectProject);

  const statusLabels: Record<ProjectStatus, string> = {
    idle: t("home.projectStatus.idle"),
    parsing: t("home.projectStatus.parsing"),
    generating: t("home.projectStatus.generating"),
    video_generating: t("home.projectStatus.video_generating"),
    done: t("home.projectStatus.done"),
  };
  const statusItems = [
    { value: "all", label: t("home.projectStatusAll") },
    ...Object.entries(statusLabels).map(([value, label]) => ({ value, label })),
  ];
  const filtersActive = Boolean(query.trim()) || statusFilter !== "all";

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: listProjectsAction,
    enabled: !initialized,
    staleTime: 300_000,
  });

  const createProjectMutation = useMutation({
    mutationFn: () => createProjectAction({ title: `${t("home.newProject")} ${projects.length + 1}` }),
    onSuccess: (response) => {
      createProject(response.project);
      router.push(`/projects/${response.project.id}`);
    },
    onError: (error) => setMessage(resolveRequestError(error, t("home.createProjectFailed"))),
  });

  useEffect(() => {
    if (projectsQuery.data?.projects) initializeProjects(projectsQuery.data.projects);
  }, [initializeProjects, projectsQuery.data?.projects]);

  const filteredProjects = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return projects.filter((project) => {
      const matchesQuery =
        !keyword || project.title.toLowerCase().includes(keyword) || project.originalScript.toLowerCase().includes(keyword);
      return matchesQuery && (statusFilter === "all" || project.status === statusFilter);
    });
  }, [projects, query, statusFilter]);

  const openProject = (project: Project) => {
    selectProject(project.id);
    router.push(`/projects/${project.id}`);
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
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
            <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("home.searchProjects")} className="pl-8" />
          </div>
          <Select
            items={statusItems}
            value={statusFilter}
            onValueChange={(value) => setStatusFilter((value ?? "all") as "all" | ProjectStatus)}
          >
            <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
            <SelectContent><SelectGroup>{statusItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup></SelectContent>
          </Select>
          {filtersActive ? (
            <Button variant="outline" onClick={() => { setQuery(""); setStatusFilter("all"); }}>
              <RotateCcw data-icon="inline-start" />
              {t("common.clearFilters")}
            </Button>
          ) : null}
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
  );
}
