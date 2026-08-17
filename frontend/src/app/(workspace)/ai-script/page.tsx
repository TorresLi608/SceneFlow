"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { FolderPlus, Loader2, Pencil, RotateCcw, Search, Trash2, X } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { deleteProjectAction, listProjectsAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useProjectStore } from "@/store/project-store";
import type { Project, ProjectStatus } from "@/types/project";

import { ProjectFormDialog } from "./_components/project-form-dialog";

/** Shown when a project has no cover of its own; both are optional by design. */
const FALLBACK_COVER = "/project-cover-fallback.svg";

export default function AiScriptPage() {
  const router = useRouter();
  const { t, formatDateTime } = useI18n();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | ProjectStatus>("all");
  const [message, setMessage] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Project | null>(null);
  const projects = useProjectStore((state) => state.projects);
  const initialized = useProjectStore((state) => state.initialized);
  const initializeProjects = useProjectStore((state) => state.initializeProjects);
  const createProject = useProjectStore((state) => state.createProject);
  const updateProjectFields = useProjectStore((state) => state.updateProjectFields);
  const removeProject = useProjectStore((state) => state.removeProject);
  const selectProject = useProjectStore((state) => state.selectProject);

  const statusLabels: Record<ProjectStatus, string> = {
    idle: t("home.projectStatus.idle"),
    parsing: t("home.projectStatus.parsing"),
    generating: t("home.projectStatus.generating"),
    video_generating: t("home.projectStatus.video_generating"),
    done: t("home.projectStatus.done"),
    partial: t("home.projectStatus.partial"),
    failed: t("home.projectStatus.failed"),
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

  const deleteMutation = useMutation({
    mutationFn: (projectId: string) => deleteProjectAction(projectId),
    onSuccess: (_data, projectId) => {
      removeProject(projectId);
      setPendingDelete(null);
    },
    onError: (error) => setMessage(resolveRequestError(error, t("home.deleteProjectFailed"))),
  });

  useEffect(() => {
    if (projectsQuery.data?.projects) initializeProjects(projectsQuery.data.projects);
  }, [initializeProjects, projectsQuery.data?.projects]);

  const filteredProjects = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return projects.filter((project) => {
      const matchesQuery =
        !keyword ||
        project.title.toLowerCase().includes(keyword) ||
        project.description.toLowerCase().includes(keyword) ||
        project.originalScript.toLowerCase().includes(keyword);
      return matchesQuery && (statusFilter === "all" || project.status === statusFilter);
    });
  }, [projects, query, statusFilter]);

  const openProject = (project: Project) => {
    selectProject(project.id);
    router.push(`/projects/${project.id}`);
  };

  const handleSaved = (saved: Project) => {
    // A create lands a whole project in the store; an edit only touches what the dialog owns.
    if (editing) {
      updateProjectFields(saved.id, {
        title: saved.title,
        description: saved.description,
        coverImageUrl: saved.coverImageUrl,
      });
    } else {
      createProject(saved);
    }
    setMessage(null);
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
          <Button
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            <FolderPlus data-icon="inline-start" />
            {t("home.newProject")}
          </Button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {projectsQuery.isLoading && projects.length === 0
          ? Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-64 rounded-lg" />)
          : null}

        {!projectsQuery.isLoading && filteredProjects.length === 0 ? (
          <div className="col-span-full flex min-h-56 items-center justify-center rounded-lg border border-dashed border-border/70 text-sm text-muted-foreground">
            {t("home.emptyProjects")}
          </div>
        ) : null}

        {filteredProjects.map((project, index) => (
          <article
            key={project.id}
            className={cn(
              "group relative flex flex-col overflow-hidden rounded-lg border border-border/70 bg-card/70 transition duration-200 hover:border-primary/40",
              "animate-in fade-in-0 slide-in-from-bottom-1"
            )}
            style={{ animationDelay: `${index * 40}ms` }}
          >
            <span className="relative block aspect-video w-full overflow-hidden bg-muted">
              <Image
                src={project.coverImageUrl ?? FALLBACK_COVER}
                alt=""
                fill
                unoptimized
                sizes="(min-width: 1280px) 25vw, (min-width: 768px) 50vw, 100vw"
                className="object-cover transition duration-200 group-hover:scale-[1.02]"
              />
            </span>

            <div className="flex min-h-0 flex-1 flex-col gap-1 p-4">
              {/* Stretched-link pattern: the whole card opens the project, but the action
                  buttons below stay clickable because they sit above it in z-order. */}
              <button
                type="button"
                onClick={() => openProject(project)}
                className="text-left text-sm font-semibold after:absolute after:inset-0 after:content-['']"
              >
                {project.title}
              </button>
              <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">
                {project.description || t("home.emptyProjectDescription")}
              </p>
              <div className="mt-auto flex flex-wrap items-center gap-2 pt-3 text-xs text-muted-foreground">
                <span className="rounded-md bg-muted px-2 py-1">{statusLabels[project.status]}</span>
                <span>{t("home.sceneCount", { count: project.scenes.length })}</span>
                <span>{formatDateTime(project.updatedAt)}</span>
              </div>
            </div>

            <div className="relative z-10 flex justify-end gap-1 border-t border-border/60 px-2 py-1.5">
              <Button
                variant="ghost"
                size="sm"
                aria-label={t("home.editProject")}
                onClick={() => {
                  setEditing(project);
                  setFormOpen(true);
                }}
              >
                <Pencil data-icon="inline-start" />
                {t("common.edit")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                aria-label={t("home.deleteProject")}
                onClick={() => setPendingDelete(project)}
              >
                <Trash2 data-icon="inline-start" />
                {t("common.delete")}
              </Button>
            </div>
          </article>
        ))}
      </div>

      {message ? <p className="mt-4 text-sm text-amber-600">{message}</p> : null}

      <ProjectFormDialog open={formOpen} onOpenChange={setFormOpen} project={editing} onSaved={handleSaved} />

      <Dialog open={Boolean(pendingDelete)} onOpenChange={(open) => (open ? null : setPendingDelete(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("home.deleteProjectTitle")}</DialogTitle>
            <DialogDescription>
              {t("home.deleteProjectDescription", { title: pendingDelete?.title ?? "" })}
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="outline" disabled={deleteMutation.isPending} onClick={() => setPendingDelete(null)}>
              <X data-icon="inline-start" />
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => pendingDelete && deleteMutation.mutate(pendingDelete.id)}
            >
              {deleteMutation.isPending ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : (
                <Trash2 data-icon="inline-start" />
              )}
              {t("common.delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
