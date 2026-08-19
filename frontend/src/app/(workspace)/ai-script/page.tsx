"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Clapperboard,
  FolderPlus,
  Layers,
  Loader2,
  Pencil,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { deleteProjectAction, listProjectsAction } from "@/actions/projects-actions";
import { queryKeys } from "@/actions/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { resolveRequestError } from "@/lib/http/errors";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useProjectStore } from "@/store/project-store";
import type { Project, ProjectStatus } from "@/types/project";

import { ProjectFormDialog } from "./_components/project-form-dialog";

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

  const statusBadgeVariant = (status: ProjectStatus) => {
    switch (status) {
      case "done":
        return "default";
      case "generating":
      case "video_generating":
      case "parsing":
        return "secondary";
      case "failed":
        return "destructive";
      default:
        return "outline";
    }
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
      {/* 顶部标题与过滤器 */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
              {t("home.aiScript")}
            </h1>
            <Badge variant="secondary" className="text-xs">
              {t("home.projectsCount", {
                filtered: filteredProjects.length,
                total: projects.length,
              })}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            管理您的短剧与漫剧剧本、角色资产与分镜时间线
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="relative min-w-[200px] flex-1 sm:w-60 sm:flex-none">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("home.searchProjects")}
              className="h-9 pl-8 text-xs"
            />
          </div>
          <Select
            items={statusItems}
            value={statusFilter}
            onValueChange={(value) => setStatusFilter((value ?? "all") as "all" | ProjectStatus)}
          >
            <SelectTrigger className="h-9 w-36 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {statusItems.map((item) => (
                  <SelectItem key={item.value} value={item.value} className="text-xs">
                    {item.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>

          {filtersActive ? (
            <Button
              variant="outline"
              size="sm"
              className="h-9 text-xs cursor-pointer"
              onClick={() => {
                setQuery("");
                setStatusFilter("all");
              }}
            >
              <RotateCcw data-icon="inline-start" className="size-3.5" />
              {t("common.clearFilters")}
            </Button>
          ) : null}

          <Button
            size="sm"
            className="h-9 gap-1.5 font-semibold shadow-xs cursor-pointer"
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            <FolderPlus data-icon="inline-start" className="size-4" />
            {t("home.newProject")}
          </Button>
        </div>
      </div>

      {/* 项目网格 */}
      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {projectsQuery.isLoading && projects.length === 0
          ? Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-64 rounded-2xl" />
            ))
          : null}

        {!projectsQuery.isLoading && filteredProjects.length === 0 ? (
          <div className="col-span-full flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-border/80 bg-card/30 p-8 text-center backdrop-blur-sm">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Clapperboard className="size-6" />
            </div>
            <p className="mt-3 text-sm font-semibold text-foreground">{t("home.emptyProjects")}</p>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground">
              输入剧情大纲或剧本台词，AI 将自动拆解镜头与生成角色设定
            </p>
            <Button
              size="sm"
              className="mt-4 gap-1.5 cursor-pointer font-semibold shadow-xs"
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              <FolderPlus className="size-4" />
              {t("home.newProject")}
            </Button>
          </div>
        ) : null}

        {filteredProjects.map((project, index) => {
          const isBusy =
            project.status === "generating" ||
            project.status === "video_generating" ||
            project.status === "parsing";

          return (
            <article
              key={project.id}
              className={cn(
                "group relative flex flex-col overflow-hidden rounded-2xl border border-border/80 bg-card/60 shadow-xs backdrop-blur-md transition-all duration-200 hover:-translate-y-1 hover:border-primary/40 hover:shadow-xl dark:border-white/10 dark:hover:border-primary/50",
                "animate-in fade-in-0 slide-in-from-bottom-2"
              )}
              style={{ animationDelay: `${index * 30}ms` }}
            >
              {/* 封面图片区 */}
              <div className="relative aspect-video w-full overflow-hidden bg-muted/60">
                <Image
                  src={project.coverImageUrl ?? FALLBACK_COVER}
                  alt=""
                  fill
                  unoptimized
                  sizes="(min-width: 1280px) 25vw, (min-width: 768px) 50vw, 100vw"
                  className="object-cover transition-transform duration-300 group-hover:scale-105"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent opacity-60 transition-opacity group-hover:opacity-40" />

                {/* 状态徽章 */}
                <div className="absolute top-2.5 left-2.5 z-10">
                  <Badge
                    variant={statusBadgeVariant(project.status)}
                    className={cn(
                      "text-[10px] backdrop-blur-md shadow-xs",
                      isBusy && "animate-pulse"
                    )}
                  >
                    {isBusy ? <Sparkles className="size-3 mr-1 inline animate-spin" /> : null}
                    {statusLabels[project.status]}
                  </Badge>
                </div>
              </div>

              {/* 内容信息区 */}
              <div className="flex min-h-0 flex-1 flex-col gap-1.5 p-4">
                <button
                  type="button"
                  onClick={() => openProject(project)}
                  className="text-left text-sm font-bold tracking-tight text-foreground transition-colors hover:text-primary cursor-pointer after:absolute after:inset-0 after:content-['']"
                >
                  {project.title}
                </button>
                <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                  {project.description || t("home.emptyProjectDescription")}
                </p>

                <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-3 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Layers className="size-3 text-primary" />
                    {t("home.sceneCount", { count: project.scenes.length })}
                  </span>
                  <span>{formatDateTime(project.updatedAt)}</span>
                </div>
              </div>

              {/* 底部操作条 */}
              <div className="relative z-10 flex justify-end gap-1 border-t border-border/60 bg-muted/20 px-3 py-1.5">
                <Button
                  variant="ghost"
                  size="xs"
                  className="rounded-md text-xs hover:bg-muted/80 cursor-pointer"
                  aria-label={t("home.editProject")}
                  onClick={() => {
                    setEditing(project);
                    setFormOpen(true);
                  }}
                >
                  <Pencil className="size-3" />
                  {t("common.edit")}
                </Button>
                <Button
                  variant="ghost"
                  size="xs"
                  className="rounded-md text-xs text-destructive hover:bg-destructive/10 hover:text-destructive cursor-pointer"
                  aria-label={t("home.deleteProject")}
                  onClick={() => setPendingDelete(project)}
                >
                  <Trash2 className="size-3" />
                  {t("common.delete")}
                </Button>
              </div>
            </article>
          );
        })}
      </div>

      {message ? (
        <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-600">
          {message}
        </div>
      ) : null}

      <ProjectFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        project={editing}
        onSaved={handleSaved}
      />

      {/* 删除确认弹窗 */}
      <Dialog
        open={Boolean(pendingDelete)}
        onOpenChange={(open) => (open ? null : setPendingDelete(null))}
      >
        <DialogContent className="max-w-sm rounded-2xl">
          <DialogHeader>
            <DialogTitle>{t("home.deleteProjectTitle")}</DialogTitle>
            <DialogDescription>
              {t("home.deleteProjectDescription", { title: pendingDelete?.title ?? "" })}
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={deleteMutation.isPending}
              onClick={() => setPendingDelete(null)}
              className="cursor-pointer"
            >
              <X className="size-3.5" />
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={deleteMutation.isPending}
              onClick={() => pendingDelete && deleteMutation.mutate(pendingDelete.id)}
              className="cursor-pointer"
            >
              {deleteMutation.isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Trash2 className="size-3.5" />
              )}
              {t("common.delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
